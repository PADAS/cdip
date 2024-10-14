import datetime
import logging
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Protocol

import pytz

from django.db import ProgrammingError, connection


class PARTITION_INTERVALS(Enum):
    MONTHLY = "monthly"


class PartitionTableToolProtocol(Protocol):
    def _create_parent_table(self) -> None:
        raise NotImplementedError


@dataclass
class IndexData:
    name: str
    columns: List[str]


@dataclass
class ConstraintData:
    name: str
    columns: List[str]


@dataclass
class ForeignKeyData:
    name: str
    foreign_column: str
    references: str


@dataclass
class TriggerData:
    name: str
    sql: str


@dataclass
class TableData:
    primary_key_columns: Optional[List[str]] = None
    indexes: Optional[List[IndexData]] = None
    unique_constraints: Optional[List[ConstraintData]] = None
    foreign_keys: Optional[List[ForeignKeyData]] = None
    triggers: Optional[List[TriggerData]] = None


class PartitionTableTool(PartitionTableToolProtocol):
    logger = logging.getLogger(__name__)

    def __init__(
        self,
        original_table_name: str,
        partition_column: str,
        partition_interval: str,
        table_data: TableData,
        migrate_batch_size_per_interval: int,
        partitions_in_the_future: int = 5,
        subpartition_column: str = None,
        subpartition_list: list = None,
    ) -> None:
        self.partition_column = partition_column
        self.partition_interval = partition_interval
        self.subpartition_column = subpartition_column
        self.subpartition_list = subpartition_list
        self.original_table_name = original_table_name
        self.partitioned_table_name = f"{original_table_name}_partitioned"
        self.template_table_name = f"{original_table_name}_template"
        self.table_data = table_data
        self.migrate_batch_size = migrate_batch_size_per_interval
        self.partitions_in_the_future = partitions_in_the_future
        self.log_data = {
            "current_step": 0,
            "last_migrated_date": None,
            "start_time": None,
        }

    def partition_table(self) -> None:
        self._set_partition_log_data()
        self.logger.info(f"Partitioning process start at {self.log_data['start_time']}")
        self._pre_requirements_check()
        self._validate_table_partititon_state()

        steps_commands = [
            "_create_parent_table",
            "_make_template_table",
            "_store_subpartitioning_function",
            "_create_subpartition_trigger",
            "_partition_setup",
            "_set_partition_schema_with_existing_tables",
            "_process_data_partition",
        ]

        for index in range(self.log_data["current_step"], len(steps_commands)):
            getattr(self, steps_commands[index])()

        self.logger.info(f"Partitioning for {self.original_table_name} table is completed.")
        self.logger.info(f"Process takes {(datetime.datetime.now(pytz.utc)) - self.log_data['start_time']}")

    def rollback(self) -> None:
        start_time = datetime.datetime.now(pytz.utc)
        temp_table_name = f"{self.original_table_name}_temp"

        self.logger.info(f"Rollback process is started at {start_time}")
        self._duplicate_original_table(source_table_name=self.original_table_name, target_table_name=temp_table_name)

        undo_partitions_sql = f"""
        CALL partman.undo_partition_proc('public.{self.original_table_name}',
                                        p_interval := '15 days',
                                        p_keep_table := FALSE,
                                        p_drop_cascade := TRUE,
                                        p_wait := 3,
                                        p_target_table := 'public.{temp_table_name}'
            );
        """
        self._execute_sql_command(command=undo_partitions_sql)
        try:
            self._execute_sql_command(command="BEGIN;")
            self.logger.info("Undoing partitions process start.")
            rename_tables_sql = f"""
                LOCK TABLE public.{self.original_table_name} IN ACCESS EXCLUSIVE MODE;

                DROP TABLE {self.original_table_name};

                ALTER TABLE public.{temp_table_name}
                    RENAME TO {self.original_table_name};
            """
            self._execute_sql_command(command=rename_tables_sql)
            self._execute_sql_command(command="COMMIT;")
            self.logger.info("Undoing partitions process is completed.")
        except Exception:
            self._execute_sql_command(command="ROLLBACK;")
            self.logger.exception("Failed at rollback process")
            exit(1)

        self.logger.info(f"Rollback process is completed in {(datetime.datetime.now(pytz.utc)) - start_time}")

    def _make_template_table(self) -> None:
        self._duplicate_original_table(
            source_table_name=self.original_table_name, target_table_name=self.template_table_name
        )
        self._set_current_step(step=2)
        self.logger.info(f"Make template '{self.template_table_name}' completed.")

    def _store_subpartitioning_function(self) -> None:
        if self.subpartition_column:
            self.logger.info(f"Creating Sub-partitioning function 'create_list_subpartitions()'...")
            sql = f"""
            CREATE OR REPLACE FUNCTION create_list_subpartitions()
            RETURNS void AS $$
            DECLARE
                parent_partition_name text;
            BEGIN
                -- Get the name of the last partition created by pg_partman
                SELECT partition_name INTO parent_partition_name
                FROM partman.part_config 
                WHERE parent_table = '{self.partitioned_table_name}'
                ORDER BY partition_creation_date DESC
                LIMIT 1;
            
                -- Dynamically create list sub-partitions for values list
                EXECUTE format('
                    CREATE TABLE %I_{self.subpartition_list[0]} PARTITION OF %I FOR VALUES IN (''{self.subpartition_list[0]}'') IF NOT EXISTS;
                    CREATE TABLE %I_{self.subpartition_list[1]} PARTITION OF %I FOR VALUES IN (''{self.subpartition_list[1]}'') IF NOT EXISTS;',
                    parent_partition_name, parent_partition_name,
                    parent_partition_name, parent_partition_name
                );
            END;
            $$ LANGUAGE plpgsql;   
            """
            # ToDo: make this work with more than two values in subpartition_list
            self._execute_sql_command(command=sql)
            self.logger.info(f"Sub-partitioning function 'create_list_subpartitions()' created.")

        self._set_current_step(step=3)

    def _create_subpartition_trigger(self) -> None:
        if self.subpartition_column:
            self.logger.info(f"Creating Sub-partitioning trigger on table '{self.partitioned_table_name}'...")
            sql = f"""
            CREATE OR REPLACE FUNCTION trigger_on_partition_creation()
            RETURNS trigger AS $$
            BEGIN
                -- Call the function to create the list sub-partitions
                PERFORM create_list_subpartitions();
                RETURN NULL;
            END;
            $$ LANGUAGE plpgsql;
            """
            self._execute_sql_command(command=sql)
            # Attach the trigger to the partman table
            sql = f"""
            DO $$
            BEGIN
               IF NOT EXISTS (
                   SELECT 1 FROM pg_trigger 
                   WHERE tgname = 'after_partition_creation') THEN
                   CREATE TRIGGER after_partition_creation 
                    AFTER INSERT ON partman.part_config
                    FOR EACH ROW
                    WHEN (NEW.parent_table = '{self.partitioned_table_name}')
                    EXECUTE FUNCTION trigger_on_partition_creation();
               END IF;
            END $$;
            """
            self._execute_sql_command(command=sql)
            self.logger.info(f"Sub-partitioning trigger on table '{self.partitioned_table_name}' created.")

        self._set_current_step(step=4)

    def _partition_setup(self) -> None:
        self.logger.info(
            f"Applying partition setup for {self.partitioned_table_name} table using {self.template_table_name}..."
        )
        sql = f"""
            SELECT partman.create_parent(
               p_parent_table := 'public.{self.partitioned_table_name}',
               p_control := '{self.partition_column}',
               p_type := 'native',
               p_interval := '{self.partition_interval}',
               p_template_table := 'public.{self.template_table_name}',
               p_premake := 1
               );
        """
        self._execute_sql_command(command=sql)

        sql = f"DROP TABLE public.{self.partitioned_table_name}_default;"
        self._execute_sql_command(command=sql)

        drop_default_partitions_sql = f"""
            DO $$
            DECLARE
                partition_table TEXT;
            BEGIN
                FOR partition_table IN
                    SELECT partman.show_partitions('public.{self.partitioned_table_name}')
                LOOP
                    EXECUTE 'DROP TABLE IF EXISTS ' || REGEXP_REPLACE(partition_table::TEXT, '\\(.*?,(.*)\\)', '\\1');
                END LOOP;
            END $$;
            """
        self._execute_sql_command(command=drop_default_partitions_sql)

        sql = f"""
        UPDATE partman.part_config
        SET parent_table = 'public.{self.original_table_name}'
        WHERE parent_table = 'public.{self.partitioned_table_name}';
        """
        self._execute_sql_command(command=sql)
        self._set_current_step(step=5)
        self.logger.info(
            f"Partition setup for {self.partitioned_table_name} table using {self.template_table_name} is completed."
        )

    def _set_partition_schema_with_existing_tables(self) -> None:
        self.logger.info(f"Setting Partition schema with existent tables...")
        try:
            self.logger.info(f"Locking tables...")
            self._execute_sql_command(command="BEGIN;")
            lock_tables_sql = f"""
            LOCK TABLE public.{self.original_table_name} IN ACCESS EXCLUSIVE MODE;
            LOCK TABLE public.{self.partitioned_table_name} IN ACCESS EXCLUSIVE MODE;
            """
            self._execute_sql_command(command=lock_tables_sql)
            self.logger.info(f"Tables locked.")
            self.logger.info(f"Renaming tables...")
            rename_tables_sql = f"""
            ALTER TABLE public.{self.original_table_name}
                RENAME TO {self.original_table_name}_default;

            ALTER TABLE public.{self.partitioned_table_name}
                RENAME TO {self.original_table_name};
            """
            self._execute_sql_command(command=rename_tables_sql)
            self.logger.info(f"Tables renamed.")

            self.logger.info(f"Setting default partition...")
            attach_sql = f"""
            ALTER TABLE public.{self.original_table_name}
                ATTACH PARTITION public.{self.original_table_name}_default DEFAULT;
            """
            self._execute_sql_command(command=attach_sql)

            create_default_partition_sql = f"""
            SELECT partman.create_partition_time(
                'public.{self.original_table_name}',
                p_partition_times := ARRAY [ '2015-01-01 00:00:00'::timestamptz ]);
            """
            self._execute_sql_command(command=create_default_partition_sql)
            self.logger.info(f"Default partition set.")
            self._execute_sql_command(command="COMMIT;")
            self.logger.info(f"Setting Partition schema with existent tables completed.")

        except Exception:
            self._execute_sql_command(command="ROLLBACK;")
            self.logger.exception("Failed to migrate batch data")
            exit(1)

        self._set_current_step(step=6)

    def _process_data_partition(self) -> None:
        self.logger.info("Moving existent data to partititons...")
        migrate_sql = f"""
            CALL partman.partition_data_proc(
            'public.{self.original_table_name}',
            p_wait:= 2,
            p_batch := {self.migrate_batch_size}
            );
        """

        self._execute_sql_command(command=migrate_sql)
        self.logger.info("Moving existent data to partititons...completed")

        create_default_partition_sql = f"""
            DO $$
                DECLARE
                    i INT;
                    partition_start_date DATE;
                    partition_end_date DATE;
                BEGIN
                    FOR i IN 1..{self.partitions_in_the_future} LOOP
                        partition_start_date := date_trunc('month', current_date) + interval '1 month' * i;
                        partition_end_date := partition_start_date + interval '1 month';

                        PERFORM partman.create_partition_time(
                            'public.{self.original_table_name}',
                            p_partition_times := ARRAY[partition_start_date]
                        );
                    END LOOP;
                END;
                $$;
            """
        self._execute_sql_command(command=create_default_partition_sql)

        self._execute_sql_command(command=f"VACUUM ANALYZE public.{self.original_table_name};")
        self._execute_sql_command(command="VACUUM;")

        self.logger.info("VACUUM ANALYZE is completed.")
        for trigger in self.table_data.triggers if self.table_data.triggers else []:
            self._drop_trigger(table_name=f"{self.original_table_name}_default", trigger_data=trigger)
            self._create_trigger(table_name=self.original_table_name, trigger_data=trigger)

        self._create_index(
            table_name=self.original_table_name,
            index_data=IndexData(name="unique", columns=self.table_data.primary_key_columns),
            is_unique=True,
        )
        for unique_constraint in self.table_data.unique_constraints if self.table_data.unique_constraints else []:
            self._create_unique_constraint(table_name=self.original_table_name, constraint_data=unique_constraint)
        self.logger.info("Triggers restored")
        self._set_current_step(step=7)

    def _validate_data(self) -> None:
        self.logger.info("Validating data...")
        create_function_to_validate_sql = f"""
            CREATE FUNCTION find_missing_records()
                RETURNS TABLE
                        (
                            id            UUID,
                            {self.partition_column}   TIMESTAMP WITH TIME ZONE,
                            das_tenant_id UUID
                        )
            AS
            $$
            DECLARE
                start_date    DATE;
                end_date      DATE;
                current_start DATE;
                current_end   DATE;
            BEGIN
                SELECT MIN(o.{self.partition_column}), MAX(o.{self.partition_column})
                INTO start_date, end_date
                FROM {self.original_table_name}_backup o;

                current_start := start_date;

                WHILE current_start <= end_date
                    LOOP
                        current_end := current_start + INTERVAL '1 week' - INTERVAL '1 day';

                        RETURN QUERY
                            SELECT o.id,
                                o.{self.partition_column}::TIMESTAMP WITH TIME ZONE,
                                o.das_tenant_id
                            FROM {self.original_table_name}_backup o
                                    LEFT JOIN {self.original_table_name} b
                                            ON o.id = b.id
                                                AND o.{self.partition_column} = b.{self.partition_column}
                                                AND o.das_tenant_id = b.das_tenant_id
                            WHERE b.id IS NULL
                            AND o.{self.partition_column} BETWEEN current_start AND current_end;

                        current_start := current_start + INTERVAL '1 week';
                    END LOOP;

                RETURN;
            END
            $$ LANGUAGE plpgsql;

        """
        self._execute_sql_command(command=create_function_to_validate_sql)
        result = self._execute_sql_command(command="SELECT * FROM find_missing_records();", fetch=True)

        self._execute_sql_command(command="DROP FUNCTION find_missing_records;")

        if result and result[0] == 0:
            self.logger.info("Data isn't validate. Procced to rollback.")
            exit(1)
        self._set_current_step(step=7)
        self.logger.info("Data was validated successfully.")

    def _pre_requirements_check(self) -> None:
        result = self._execute_sql_command(
            command="SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name = 'partman';",
            fetch=True,
        )
        if result and result[0] == 0:
            self.logger.info("creating partman schema")
            self._execute_sql_command(command="CREATE SCHEMA partman;")

        result = self._execute_sql_command(
            "SELECT COUNT(*) FROM pg_extension WHERE extname = 'pg_partman';", fetch=True
        )
        if result and result[0] == 0:
            self.logger.info("creating pg_partman extension")
            self._execute_sql_command("CREATE EXTENSION pg_partman SCHEMA partman;")

    def _validate_table_partititon_state(self) -> None:
        sql = f"""SELECT COUNT(c.oid)
                FROM pg_class AS c
                WHERE EXISTS (SELECT 1
                            FROM pg_inherits AS i
                            WHERE i.inhrelid = c.oid)
                AND c.relkind IN ('r', 'p')
                AND c.relname LIKE '{self.original_table_name}%';"""

        result = self._execute_sql_command(command=sql, fetch=True)
        if result and result[0] > 0 and self.log_data["current_step"] >= 7:
            self.logger.error(f"{self.original_table_name} table is already partitioned.")
            exit(1)

    def _duplicate_original_table(self, source_table_name: str, target_table_name: str) -> None:
        create_table_sql = f"""
            CREATE TABLE IF NOT EXISTS public.{target_table_name}
            (
                LIKE public.{source_table_name}
            );
        """
        self._execute_sql_command(command=create_table_sql)
        self.logger.info(f"Table: {target_table_name} created successfully.")
        add_primary_key_sql = f"""
                ALTER TABLE public.{target_table_name}
                ADD PRIMARY KEY ({', '.join(self.table_data.primary_key_columns)});
            """
        self._execute_sql_command(command=add_primary_key_sql)
        self.logger.info(f"Primary key for {target_table_name} table is created successfully.")

        for index in self.table_data.indexes if self.table_data.indexes else []:
            self._create_index(table_name=target_table_name, index_data=index)

        for constraint in self.table_data.unique_constraints if self.table_data.unique_constraints else []:
            self._create_unique_constraint(table_name=target_table_name, constraint_data=constraint)

        for foreign_key in self.table_data.foreign_keys if self.table_data.foreign_keys else []:
            self._create_foreign_key(table_name=target_table_name, foreign_key_data=foreign_key)

        self.logger.info(f"Duplicate table: {target_table_name} is ready.")

    def _create_index(self, table_name: str, index_data: IndexData, is_unique: bool = False) -> None:
        if is_unique:
            sql = f"""
                CREATE UNIQUE INDEX IF NOT EXISTS {index_data.name}
                ON {table_name}
                ({', '.join(index_data.columns)});
            """
        else:
            sql = f"""
            CREATE INDEX IF NOT EXISTS {index_data.name}
            ON {table_name}
            USING btree
            ({', '.join(index_data.columns)});
            """

        self._execute_sql_command(command=sql)
        self.logger.info(f"Index: {index_data.name} created successfully.")

    def _create_unique_constraint(self, table_name: str, constraint_data: ConstraintData) -> None:
        sql = f"""
            ALTER TABLE {table_name}
            ADD CONSTRAINT {table_name}_{constraint_data.name}
            UNIQUE ({', '.join(constraint_data.columns)});
        """
        self._execute_sql_command(command=sql)
        self.logger.info(f"Constraint: {constraint_data.name} created successfully.")

    def _create_foreign_key(self, table_name: str, foreign_key_data: ForeignKeyData) -> None:
        sql = f"""
            ALTER TABLE public.{table_name}
            ADD CONSTRAINT {foreign_key_data.name}
                FOREIGN KEY ({foreign_key_data.foreign_column}) REFERENCES {foreign_key_data.references}
                    DEFERRABLE INITIALLY DEFERRED;
            """
        self._execute_sql_command(command=sql)
        self.logger.info(f"Foreign key: {foreign_key_data.name} created successfully.")

    def _create_trigger(self, table_name: str, trigger_data: TriggerData) -> None:
        sql = trigger_data.sql.format(table_name=table_name)
        self._execute_sql_command(command=sql)
        self.logger.info(f"Trigger: {trigger_data.name} created successfully.")

    def _drop_trigger(self, table_name: str, trigger_data: TriggerData) -> None:
        sql = f"DROP TRIGGER IF EXISTS {trigger_data.name} on {table_name};"
        self._execute_sql_command(command=sql)
        self.logger.info(f"Trigger: {trigger_data.name} deleted on {table_name}.")

    def _backup_original_table(self) -> None:
        create_backup_table_sql = f"""
            CREATE TABLE IF NOT EXISTS public.{self.original_table_name}_backup
            (
                LIKE public.{self.original_table_name} INCLUDING ALL
            );
        """
        self._execute_sql_command(command=create_backup_table_sql)

        min_value, max_value = self._get_min_max_partition_column()
        batch_size_days = 15
        batch_start = min_value if not self.log_data["last_migrated_date"] else self.log_data["last_migrated_date"]
        batch_end = None

        self.logger.info(f"Start the backup process from {batch_start} to {max_value}")

        while batch_start < max_value:
            try:
                batch_end = batch_start + datetime.timedelta(days=batch_size_days)
                if batch_end >= max_value:
                    batch_end = max_value

                self._execute_sql_command(command="BEGIN;")

                insert_sql = f"""
                    INSERT INTO {self.original_table_name}_backup
                    SELECT * FROM {self.original_table_name}
                    WHERE {self.partition_column} >= '{batch_start}'
                    AND {self.partition_column} <= '{batch_end}'
                    AND EXISTS (
                        SELECT 1
                        FROM {self.original_table_name}
                        WHERE {self.partition_column} >= '{batch_start}'
                        AND {self.partition_column} <= '{batch_end}'
                    )
                    ORDER BY {self.partition_column}
                    ON CONFLICT DO NOTHING;
                """
                self._execute_sql_command(command=insert_sql)

                update_last_migrated_date_sql = f"""
                    UPDATE {self.original_table_name}_partition_log
                    SET last_migrated_date = '{batch_end}'
                    WHERE id = 1;
                """
                self._execute_sql_command(command=update_last_migrated_date_sql)

                self._execute_sql_command(command="COMMIT;")
                batch_start = batch_end
            except Exception:
                self._execute_sql_command(command="ROLLBACK;")
                self.logger.exception(f"Failed to migrate batch from {batch_start} to {batch_end}")

        self._set_current_step(step=4)
        self.logger.info("Backup process is completed.")

    def _get_min_max_partition_column(self):
        sql = f"""
            SELECT MIN({self.partition_column}), MAX({self.partition_column})
            FROM {self.original_table_name};
        """
        result = self._execute_sql_command(command=sql, fetch=True)
        min_value = result[0]
        if not min_value:
            timezone = pytz.UTC
            min_value = timezone.localize(self.partition_start)
        max_value = result[1] or self.log_data["start_time"]
        return min_value, max_value

    def _set_partition_log_data(self) -> None:
        log_table_name = f"{self.original_table_name}_partition_log"
        sql_create_log_table = f"""
            CREATE TABLE IF NOT EXISTS {log_table_name}
            (
                id                   INTEGER     DEFAULT 1     NOT NULL PRIMARY KEY,
                current_step         INTEGER     DEFAULT 0     NOT NULL,
                last_migrated_date   timestamp WITH TIME ZONE DEFAULT NULL,
                start_time           TIMESTAMP WITH TIME ZONE  NOT NULL
            );
        """
        self._execute_sql_command(command=sql_create_log_table)
        self._execute_sql_command(
            command=f"""
                INSERT INTO {log_table_name} (id, current_step, last_migrated_date, start_time)
                VALUES (1, 0, NULL, NOW())
                ON CONFLICT (id) DO NOTHING;
            """
        )
        for column in ("current_step", "last_migrated_date", "start_time"):
            result = self._execute_sql_command(
                command=f"""
                SELECT {column}
                FROM {log_table_name}
                WHERE id = 1;
            """,
                fetch=True,
            )
            if result[0] and result[0]:
                self.log_data[column] = result[0]
        self.logger.info(f"Partition log data is set: {self.log_data}")

    def _set_current_step(self, step: int) -> None:
        self._execute_sql_command(
            command=f"""
                UPDATE {self.original_table_name}_partition_log
                SET current_step = '{step}'
                WHERE id = 1;
            """
        )

    def _execute_sql_command(self, command: str, fetch: bool = False) -> Optional[str]:
        result = None
        with connection.cursor() as cursor:
            try:
                cursor.execute(command)
            except ProgrammingError as e:
                self.logger.error(e)
                self.logger.exception("Exiting due to error")
                exit(1)
            if fetch:
                result = cursor.fetchone()
        return result

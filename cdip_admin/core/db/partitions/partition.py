import datetime
import logging
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Protocol

import pytz

from django.db import ProgrammingError, connection


class PARTITION_INTERVALS(Enum):
    MONTHLY = "monthly"


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


class TablePartitionerBase:
    logger = logging.getLogger(__name__)
    steps_commands = [
        "_create_parent_table",
        "_make_template_table",
        "_partition_setup",
        "_set_partition_schema_with_existing_tables",
        "_process_data_partition",
        "_set_retention_policy",
        #"_partman_run_maintenance",
    ]

    def __init__(
        self,
        original_table_name: str,
        partition_column: str,
        table_data: TableData,
    ) -> None:
        self.partition_column = partition_column
        self.original_table_name = original_table_name
        self.partitioned_table_name = f"{original_table_name}_partitioned"
        self.template_table_name = f"{original_table_name}_template"
        self.table_data = table_data
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

        for index in range(self.log_data["current_step"], len(self.steps_commands)):
            getattr(self, self.steps_commands[index])()

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

    # def _partman_run_maintenance(self) -> None:
    #     self.logger.info(
    #         f"Running partman.run_maintenance_proc() ..."
    #     )
    #     sql = f"""
    #         SELECT partman.run_maintenance('{self.original_table_name}');
    #     """
    #     self._execute_sql_command(command=sql)
    #     self._set_current_step(step=5)
    #     self.logger.info(
    #         f"partman.run_maintenance() completed."
    #     )

    def _process_data_partition(self) -> None:
        self.logger.warning("_process_data_partition() is not implemented. Existent data won't be moved to partititons.")
        self._set_current_step(step=5)

    def _set_retention_policy(self) -> None:
        self.logger.warning("_set_retention_policy() is not implemented. Retention policy won't be set.")
        self._set_current_step(step=6)

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
                self.logger.debug(f"Executing SQL: {command} ...")
                cursor.execute(command)
            except ProgrammingError as e:
                self.logger.error(e)
                self.logger.exception("Exiting due to error")
                exit(1)
            if fetch:
                result = cursor.fetchone()
        return result

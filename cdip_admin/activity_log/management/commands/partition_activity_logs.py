from typing import List

from django.core.management import BaseCommand

from activity_log.models import ActivityLog
from core.db.partitions import (
    ForeignKeyData,
    IndexData,
    TableData,
    TablePartitionerBase, PARTITION_INTERVALS,
)


class ActivityLogsPartitioner(TablePartitionerBase):
    def __init__(
        self,
        original_table_name: str,
        table_data: TableData,
        partition_column: str = "log_type",
        subpartition_column: str = "created_at",
        subpartition_start: str = "2023-11-01 00:00:00",
        subpartitions_in_the_future: int = 5,
        subpartition_interval: str = PARTITION_INTERVALS.MONTHLY.value,
        migrate_batch_size: int = 10000,
    ) -> None:
        super().__init__(
            partition_column=partition_column,
            original_table_name=original_table_name,
            table_data=table_data,
        )
        self.subpartition_column = subpartition_column
        self.migrate_batch_size = migrate_batch_size
        self.subpartition_start = subpartition_start
        self.subpartition_interval = subpartition_interval
        self.subpartitions_in_the_future = subpartitions_in_the_future


    def _create_parent_table(self) -> None:
        sql = f"""
        -- Create the parent table with partitioning
        CREATE TABLE IF NOT EXISTS {self.partitioned_table_name}
        (
          created_at timestamp with time zone NOT NULL,
          updated_at timestamp with time zone NOT NULL,
          id uuid NOT NULL,
          log_level integer NOT NULL,
          log_type character varying(5) NOT NULL,
          origin character varying(5) NOT NULL,
          value character varying(40) NOT NULL,
          title character varying(200) NOT NULL,
          details jsonb NOT NULL,
          is_reversible boolean NOT NULL,
          revert_data jsonb NOT NULL,
          created_by_id integer,
          integration_id uuid,
          FOREIGN KEY (integration_id)
              REFERENCES public.integrations_integration (id) DEFERRABLE INITIALLY DEFERRED,
          FOREIGN KEY (created_by_id)
              REFERENCES public.auth_user (id) DEFERRABLE INITIALLY DEFERRED
        ) PARTITION BY LIST ({self.partition_column});
        """
        self._execute_sql_command(command=sql)
        self._set_current_step(step=1)
        self.logger.info(f"Parent table: {self.partitioned_table_name} created successfully.")

    def _partition_setup(self) -> None:
        self.logger.info(
            f"Applying partition setup for {self.partitioned_table_name} table using {self.template_table_name}..."
        )
        # Create one partition for each value
        self.logger.info(f"Creating partition for 'cdc' logs...")
        sql = f"""
        CREATE TABLE {self.original_table_name}_cdc PARTITION OF public.{self.partitioned_table_name}
        FOR VALUES IN ('cdc')
        """
        self._execute_sql_command(command=sql)
        self.logger.info(f"Partition for 'cdc' logs created.")

        self.logger.info(f"Creating partition for 'ev' logs...")
        events_table_name = f"{self.original_table_name}_ev"
        sql = f"""
        CREATE TABLE {events_table_name} PARTITION OF public.{self.partitioned_table_name}
        FOR VALUES IN ('ev')
        PARTITION BY RANGE ({self.subpartition_column});
        """
        self._execute_sql_command(command=sql)
        self.logger.info(f"Partition for 'ev' logs created.")

        self.logger.info(
            f"Registering {events_table_name} parent table in partman..."
        )
        sql = f"""
            SELECT partman.create_parent(
               p_parent_table := 'public.{events_table_name}',
               p_control := '{self.subpartition_column}',
               p_type := 'native',
               p_start_partition := '{self.subpartition_start}',
               p_interval := '{self.subpartition_interval}',
               p_template_table := 'public.{self.template_table_name}',
               p_premake := {self.subpartitions_in_the_future}
               );
        """
        self._execute_sql_command(command=sql)
        self.logger.info(f"{events_table_name} parent table registered.")

        self._set_current_step(step=3)
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
            # Original table is saved as backup
            rename_tables_sql = f"""
            ALTER TABLE public.{self.original_table_name}
                RENAME TO {self.original_table_name}_original;

            ALTER TABLE public.{self.partitioned_table_name}
                RENAME TO {self.original_table_name};
            """
            self._execute_sql_command(command=rename_tables_sql)
            self.logger.info(f"Tables renamed.")
            self.logger.info(f"Creating default partition...")
            create_default_part_sql = f"""
            CREATE TABLE IF NOT EXISTS {self.original_table_name}_default
            PARTITION OF {self.original_table_name} DEFAULT;
            """
            self._execute_sql_command(command=create_default_part_sql)
            self.logger.info(f"Default partition created.")
            self._execute_sql_command(command="COMMIT;")
            self.logger.info(f"Setting Partition schema with existent tables completed.")

        except Exception:
            self._execute_sql_command(command="ROLLBACK;")
            self.logger.exception("Failed to switch to partitioned table")
            exit(1)

        self._set_current_step(step=4)

    def _process_data_partition(self) -> None:
        self.logger.info("Moving existent data to partititons...")
        self._execute_sql_command(command="BEGIN;")
        # ToDo: Copy data in batches
        migrate_sql = f"""
        INSERT INTO {self.original_table_name}
        SELECT * FROM public.{self.original_table_name}_original;
        """
        self._execute_sql_command(command=migrate_sql)
        self._execute_sql_command(command="COMMIT;")
        self.logger.info("Moving existent data to partitions...completed")

        self.logger.info("Running VACUUM ANALYZE...")
        self._execute_sql_command(command=f"VACUUM ANALYZE public.{self.original_table_name};")
        self._execute_sql_command(command="VACUUM;")
        self.logger.info("VACUUM ANALYZE is completed.")

        self.logger.info("Restoring triggers...")
        for trigger in self.table_data.triggers if self.table_data.triggers else []:
            self._drop_trigger(table_name=f"{self.original_table_name}_original", trigger_data=trigger)
            self._create_trigger(table_name=self.original_table_name, trigger_data=trigger)
        self.logger.info("Triggers restored")

        self.logger.info(f"Creating unique index on PK {self.table_data.primary_key_columns}...")
        pk_unique_idx_name = f"{'_'.join(self.table_data.primary_key_columns)}_unique_idx"
        self._create_index(
            table_name=self.original_table_name,
            index_data=IndexData(name=pk_unique_idx_name, columns=self.table_data.primary_key_columns),
            is_unique=True,
        )
        self.logger.info("Unique index on PK created.")

        self.logger.info("Restoring unique constraints...")
        for unique_constraint in self.table_data.unique_constraints if self.table_data.unique_constraints else []:
            self._create_unique_constraint(table_name=self.original_table_name, constraint_data=unique_constraint)
        self.logger.info("Unique constraints restored.")

        self._set_current_step(step=5)


    def _set_retention_policy(self) -> None:
        # Set retention policy to detach event partitions older than one month
        self.logger.info("Setting retention policy in partman...")
        retention_sql = f"""
        UPDATE partman.part_config 
        SET retention = '1 mon', retention_keep_table = true 
        WHERE parent_table = '{self.original_table_name}_ev';
        """
        self._execute_sql_command(command=retention_sql)
        self.logger.info("Retention policy set.")
        self._set_current_step(step=6)


class Command(BaseCommand):
    help = "using pg_partman, partition the activity_logs table."

    def add_arguments(self, parser):
        parser.add_argument(
            "-r",
            "--rollback",
            dest="rollback",
            action="store",
            default=False,
            help="Rollback the partitioning of the table.",
        )

    def handle(self, *args, **options):
        should_rollback = bool(options["rollback"])

        self.stdout.write(self.style.SUCCESS(f"Running in [{'rollback' if should_rollback else 'normal'}] mode."))

        indexes = [
            IndexData(name="activity_lo_created_14fffc_idx", columns=["created_at DESC"]),
            IndexData(name="activity_log_activitylog_created_by_id_74d051c2", columns=['created_by_id']),
            IndexData(name="activity_log_activitylog_integration_id_29977686", columns=['integration_id']),
            IndexData(name="activity_log_activitylog_log_level_11077a1d", columns=['log_level']),
            IndexData(name="activity_log_activitylog_log_type_2418a58c", columns=['log_type COLLATE pg_catalog."default"']),
            IndexData(name="activity_log_activitylog_log_type_2418a58c_like", columns=['log_type COLLATE pg_catalog."default" varchar_pattern_ops']),
            IndexData(name="activity_log_activitylog_origin_18b464a1", columns=['origin COLLATE pg_catalog."default"']),
            IndexData(name="activity_log_activitylog_origin_18b464a1_like", columns=['origin COLLATE pg_catalog."default" varchar_pattern_ops']),
            IndexData(name="activity_log_activitylog_value_4bb3fe2a", columns=['value COLLATE pg_catalog."default"']),
            IndexData(name="activity_log_activitylog_value_4bb3fe2a_like", columns=['value COLLATE pg_catalog."default" varchar_pattern_ops']),
        ]

        foreign_keys = [
            ForeignKeyData(
                name="activity_log_activit_integration_id_29977686_fk_integrati",
                foreign_column="integration_id",
                references="integrations_integration",
            ),
            ForeignKeyData(
                name="activity_log_activitylog_created_by_id_74d051c2_fk_auth_user_id",
                foreign_column="created_by_id",
                references="auth_user",
            )
        ]

        table_data = TableData(
            primary_key_columns=["id", "log_type", "created_at"],
            indexes=indexes,
            foreign_keys=foreign_keys
        )

        # Partition by log type
        logs_partitioner = ActivityLogsPartitioner(
            original_table_name="activity_log_activitylog",
            table_data=table_data,
        )
        if not should_rollback:
            self.stdout.write(self.style.SUCCESS("Partitioning activity logs by type."))
            logs_partitioner.partition_table()
        else:
            self.stdout.write(self.style.SUCCESS("Starting rollback process."))
            logs_partitioner.rollback()
        self.stdout.write(self.style.SUCCESS(f"Process [{'rollback' if should_rollback else 'partition'}] finish."))

import datetime
import pytz
from django.core.management import BaseCommand
from django_celery_beat.models import CrontabSchedule, PeriodicTask
from core.db.partitions import (
    ForeignKeyData,
    IndexData,
    TableData,
    TablePartitionerBase,
    PARTITION_INTERVALS,
)


class ActivityLogsPartitioner(TablePartitionerBase):
    steps_commands = [
        "_create_parent_table",
        "_make_template_table",
        "_partition_setup",
        "_set_partition_schema_with_existing_tables",
        "_define_batch_copy_function",
        "_migrate_data_change_logs",
        "_migrate_event_logs",
        "_set_retention_policy",
        "_partman_run_maintenance",
        "_schedule_periodic_maintenance",
    ]
    def __init__(
        self,
        original_table_name: str,
        table_data: TableData,
        partition_column: str = "log_type",
        subpartition_column: str = "created_at",
        subpartition_start: str = "2023-11-01 00:00:00",  # Activity logs where implemented this month
        subpartitions_in_the_future: int = 24,
        subpartition_interval: str = PARTITION_INTERVALS.WEEKLY.value,
        migrate_batch_size: int = 10000,
        migrate_start_offset: int = None,
        migrate_events_since: str = "2024-09-29 00:00:00",
        migrate_max_batches: int = None
    ) -> None:
        super().__init__(
            partition_column=partition_column,
            original_table_name=original_table_name,
            table_data=table_data,
        )
        self.subpartition_column = subpartition_column
        self.migrate_batch_size = migrate_batch_size
        self.migrate_start_offset = migrate_start_offset
        self.migrate_max_batches = migrate_max_batches
        self.subpartition_start = subpartition_start
        self.subpartition_interval = subpartition_interval
        self.subpartitions_in_the_future = subpartitions_in_the_future
        self.migrate_events_since = migrate_events_since
        self.log_data = {
            "current_step": 0,
            "last_migrated_date": None,
            "start_time": None,
            "last_migrated_cdc_offset": 0,
            "last_migrated_ev_offset": 0
        }


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

    def _define_batch_copy_function(self) -> None:
        self.logger.info("Creating insert_activity_log_batch() function...")
        copy_batch_function_sql = f"""
        CREATE OR REPLACE FUNCTION insert_activity_log_batch(
            p_start_offset INTEGER,
            p_batch_size INTEGER,
            p_log_type TEXT,
            p_since_date TIMESTAMP
        ) RETURNS BIGINT AS $$
        DECLARE
            v_rows_moved BIGINT;  -- To capture the number of rows moved
        BEGIN
            -- Insert a batch of rows into the partition, ignoring conflicts
            INSERT INTO {self.original_table_name}
            SELECT * FROM public.{self.original_table_name}_original
            WHERE log_type = p_log_type
            AND created_at >= p_since_date
            LIMIT p_batch_size OFFSET p_start_offset
            ON CONFLICT DO NOTHING;
        
            -- Get the number of rows moved
            GET DIAGNOSTICS v_rows_moved = ROW_COUNT;
        
            -- Return the number of rows copied
            RETURN v_rows_moved;
        END;
        $$ LANGUAGE plpgsql;
        """
        self._execute_sql_command(command=copy_batch_function_sql)
        self.logger.info("insert_activity_log_batch() function created.")
        self._set_current_step(step=5)
        
    def _migrate_data_change_logs(self) -> None:
        # Resume from the last commited offset or as commanded
        start_offset = self.migrate_start_offset or self.log_data["last_migrated_cdc_offset"]
        since_date = self.subpartition_start
        self.logger.info(f"Moving data change logs in batches, start offset: {start_offset}...")
        # Copy data in batches
        batch_num = 0
        is_all_data_copied = False
        while True:
            self.logger.info(f"Copying batch {batch_num}, offset {start_offset}...")
            migrate_cdc_sql = f"""SELECT insert_activity_log_batch({start_offset}, {self.migrate_batch_size}, 'cdc', '{since_date}');"""
            result = self._execute_sql_command(command=migrate_cdc_sql, fetch=True)
            self.logger.info(f"Batch copied: {result[0]} rows")
            start_offset += self.migrate_batch_size
            update_logs_offset_sql = f"""
            -- Save last commited offset
            UPDATE {self.original_table_name}_partition_log
            SET last_migrated_cdc_offset = {start_offset}
            WHERE id = 1;
            """
            self._execute_sql_command(command=update_logs_offset_sql)
            self.logger.info(f"Batch {batch_num} copied, offset moved to {start_offset}.")
            batch_num += 1
            # if batch_num % 10 == 0:  # Run VACUUM ANALYZE every 10 batches
            #     self.logger.info("Running VACUUM ANALYZE...")
            #     self._execute_sql_command(command=f"VACUUM ANALYZE public.{self.original_table_name};")
            #     self._execute_sql_command(command="VACUUM;")
            #     self.logger.info("VACUUM ANALYZE is completed.")
            if result and result[0] == 0:
                self.logger.info(f"No more data to copy.")
                is_all_data_copied = True
                break
            if self.migrate_max_batches and batch_num > self.migrate_max_batches:
                self.logger.info(f"Maximum number of batches reached.")
                break
            if result and result[0] == 0:
                self.logger.info(f"No more data to copy.")
                break

        if is_all_data_copied:
            self.logger.info("Data change logs migration complete.")
            # self.logger.info("Running VACUUM ANALYZE...")
            # self._execute_sql_command(command=f"VACUUM ANALYZE public.{self.original_table_name};")
            # self._execute_sql_command(command="VACUUM;")
            # self.logger.info("VACUUM ANALYZE is completed.")
            self._set_current_step(step=6)

    def _migrate_event_logs(self) -> None:
        # Resume from the last commited offset or as commanded
        start_offset = self.migrate_start_offset or self.log_data["last_migrated_ev_offset"]
        self.logger.info(f"Moving event logs in batches, start offset: {start_offset}...")
        # Copy data in batches
        batch_num = 0
        is_all_data_copied = False
        while True:
            self.logger.info(f"Copying batch {batch_num}, offset {start_offset}...")
            migrate_events_sql = f"""SELECT insert_activity_log_batch({start_offset}, {self.migrate_batch_size}, 'ev', '{self.migrate_events_since}');"""
            result = self._execute_sql_command(command=migrate_events_sql, fetch=True)
            self.logger.info(f"Batch copied: {result[0]} rows")
            start_offset += self.migrate_batch_size
            update_logs_offset_sql = f"""
            -- Save last commited offset
            UPDATE {self.original_table_name}_partition_log
            SET last_migrated_ev_offset = {start_offset}
            WHERE id = 1;
            """
            self._execute_sql_command(command=update_logs_offset_sql)
            self.logger.info(f"Batch {batch_num} copied, offset moved to {start_offset}.")
            batch_num += 1
            # if batch_num % 10 == 0:  # Run VACUUM ANALYZE every 10 batches
            #     self.logger.info("Running VACUUM ANALYZE...")
            #     self._execute_sql_command(command=f"VACUUM ANALYZE public.{self.original_table_name};")
            #     self._execute_sql_command(command="VACUUM;")
            #     self.logger.info("VACUUM ANALYZE is completed.")
            if result and result[0] == 0:
                self.logger.info(f"No more data to copy.")
                is_all_data_copied = True
                break
            if self.migrate_max_batches and batch_num > self.migrate_max_batches:
                self.logger.info(f"Maximum number of batches reached.")
                break

        if not is_all_data_copied:
            self.logger.info("Event logs migration complete.")
            self.logger.info("Moving existent data to partitions...completed.")

            # self.logger.info("Running VACUUM ANALYZE...")
            # self._execute_sql_command(command=f"VACUUM ANALYZE public.{self.original_table_name};")
            # self._execute_sql_command(command="VACUUM;")
            # self.logger.info("VACUUM ANALYZE is completed.")

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
            self._set_current_step(step=7)


    def _set_retention_policy(self) -> None:
        # Set retention policy for partman, to detach old event partitions
        self.logger.info("Setting retention policy in partman...")
        retention_sql = f"""
        UPDATE partman.part_config 
        SET retention = '3 weeks', retention_keep_table = true 
        WHERE parent_table = 'public.{self.original_table_name}_ev';
        """
        self._execute_sql_command(command=retention_sql)
        self.logger.info("Retention policy set.")
        self._set_current_step(step=8)

    def _schedule_periodic_maintenance(self) -> None:
        # Get or create periodic task to run every week
        self.logger.info("Scheduling weekly maintenance...")
        schedule, created = CrontabSchedule.objects.get_or_create(
            minute="0",
            hour="0",
            day_of_week="1"  # Monday
        )
        PeriodicTask.objects.get_or_create(
            task="activity_log.tasks.run_partitions_maintenance",
            defaults={
                "crontab": schedule,
                "name": "Run psql partitions maintenance"
            }
        )
        self.logger.info("Weekly maintenance scheduled.")
        self._set_current_step(step=10)

    def _set_partition_log_data(self) -> None:
        log_table_name = f"{self.original_table_name}_partition_log"
        sql_create_log_table = f"""
            CREATE TABLE IF NOT EXISTS {log_table_name}
            (
                id                          INTEGER     DEFAULT 1     NOT NULL PRIMARY KEY,
                current_step                INTEGER     DEFAULT 0     NOT NULL,
                last_migrated_date          TIMESTAMP WITH TIME ZONE DEFAULT NULL,
                start_time                  TIMESTAMP WITH TIME ZONE  NOT NULL,
                last_migrated_cdc_offset    INTEGER     DEFAULT 0     NOT NULL,
                last_migrated_ev_offset     INTEGER     DEFAULT 0     NOT NULL
            );
        """
        self._execute_sql_command(command=sql_create_log_table)
        self._execute_sql_command(
            command=f"""
                INSERT INTO {log_table_name} (id, current_step, last_migrated_date, start_time, last_migrated_cdc_offset, last_migrated_ev_offset)
                VALUES (1, 0, NULL, NOW(), 0, 0)
                ON CONFLICT (id) DO NOTHING;
            """
        )
        for column in ("current_step", "last_migrated_date", "start_time", "last_migrated_cdc_offset", "last_migrated_ev_offset"):
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

    def _set_last_migrated_cdc_offset(self, offset: int) -> None:
        self._execute_sql_command(
            command=f"""
                UPDATE {self.original_table_name}_partition_log
                SET last_migrated_cdc_offset = '{offset}'
                WHERE id = 1;
            """
        )

    def _set_last_migrated_ev_offset(self, offset: int) -> None:
        self._execute_sql_command(
            command=f"""
                UPDATE {self.original_table_name}_partition_log
                SET last_migrated_ev_offset = '{offset}'
                WHERE id = 1;
            """
        )

    def rollback(self) -> None:
        start_time = datetime.datetime.now(pytz.utc)
        original_table_bkp = f"{self.original_table_name}_original"

        self.logger.info(f"Rollback process is started at {start_time}")
        try:
            self._execute_sql_command(command="BEGIN;")
            self.logger.info("Undoing partitions process...")

            self.logger.info("Restoring original activity logs table...")
            unregister_from_partman_sql = f"""
                LOCK TABLE public.{self.original_table_name} IN ACCESS EXCLUSIVE MODE;

                DROP TABLE {self.original_table_name};

                ALTER TABLE public.{original_table_bkp}
                    RENAME TO {self.original_table_name};
            """
            self._execute_sql_command(command=unregister_from_partman_sql)
            self.logger.info("Original activity logs table restored.")

            self.logger.info("Unregistering events table from partman...")
            unregister_from_partman_sql = f"""
            DELETE FROM partman.part_config WHERE parent_table = 'public.{self.original_table_name}_ev';
            """
            self._execute_sql_command(command=unregister_from_partman_sql)
            self.logger.info("Events table unregistered from partman.")

            self.logger.info("Cleaning up tables...")
            drop_tables_sql = f"""
            DROP TABLE IF EXISTS activity_log_activitylog_default;
            DROP TABLE IF EXISTS activity_log_activitylog_partition_log;
            DROP TABLE IF EXISTS activity_log_activitylog_partitioned;
            DROP TABLE IF EXISTS activity_log_activitylog_template; 
            DROP TABLE IF EXISTS activity_log_activitylog_cdc;
            DROP TABLE IF EXISTS activity_log_activitylog_ev;
            DROP TABLE IF EXISTS activity_log_activitylog_ev_default;
            DROP TABLE IF EXISTS activity_log_activitylog_ev_partition_log;
            DROP TABLE IF EXISTS activity_log_activitylog_ev_partitioned;
            DROP TABLE IF EXISTS activity_log_activitylog_ev_template; 
            DROP TABLE IF EXISTS activity_log_activitylog_ev_template;
            """
            self._execute_sql_command(command=drop_tables_sql)
            drop_event_partitions_sql = f"""
            DO $$
            DECLARE
                tables_to_drop TEXT;
            BEGIN
                SELECT string_agg(table_name, ', ')
                INTO tables_to_drop
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name LIKE '{self.original_table_name}_ev_p%';
            
                IF tables_to_drop IS NOT NULL THEN
                    EXECUTE 'DROP TABLE IF EXISTS ' || tables_to_drop || ' CASCADE;';
                END IF;
            END $$;
            """
            self._execute_sql_command(command=drop_event_partitions_sql)
            self.logger.info("Tables cleanup complete.")

            self._execute_sql_command(command="COMMIT;")
            self.logger.info("Undoing partitions process is completed.")
        except Exception:
            self._execute_sql_command(command="ROLLBACK;")
            self.logger.exception("Failed at rollback process")
            exit(1)

        self.logger.info(f"Rollback process is completed in {(datetime.datetime.now(pytz.utc)) - start_time}")


class Command(BaseCommand):
    help = "using pg_partman, partition the activity_logs table."

    def add_arguments(self, parser):
        parser.add_argument(
            "-r",
            "--rollback",
            dest="rollback",
            action="store_true",
            default=False,
            help="Rollback the partitioning of the table.",
        )
        parser.add_argument(
            "-m",
            "--max-batches",
            dest="max_batches",
            type=int,
            default=None,
            help="Maximum number of batches to migrate.",
        )

    def handle(self, *args, **options):
        should_rollback = options["rollback"]
        max_batches = options["max_batches"]

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
            migrate_max_batches=max_batches
        )
        if not should_rollback:
            self.stdout.write(self.style.SUCCESS("Partitioning activity logs ..."))
            logs_partitioner.partition_table()
        else:
            self.stdout.write(self.style.SUCCESS("Starting rollback process."))
            logs_partitioner.rollback()
        self.stdout.write(self.style.SUCCESS(f"Process [{'rollback' if should_rollback else 'partition'}] finish."))

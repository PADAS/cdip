from django.core.management import BaseCommand

from activity_log.models import ActivityLog
from core.db.partitions import (
    ForeignKeyData,
    IndexData,
    TableData,
    ValuesListTablePartitioner,
)


class LogTypeActivityLogsPartitioner(ValuesListTablePartitioner):

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
            primary_key_columns=["id", "log_type"],
            indexes=indexes,
            foreign_keys=foreign_keys
        )

        # Partition by log type
        logs_partitioner = LogTypeActivityLogsPartitioner(
            original_table_name="activity_log_activitylog",
            partition_column="log_type",
            partition_values=[t.value for t in ActivityLog.LogTypes],
            table_data=table_data,
        )
        if not should_rollback:
            self.stdout.write(self.style.SUCCESS("Partitioning activity logs by type."))
            logs_partitioner.partition_table()
        else:
            self.stdout.write(self.style.SUCCESS("Starting rollback process."))
            logs_partitioner.rollback()
        self.stdout.write(self.style.SUCCESS(f"Process [{'rollback' if should_rollback else 'partition'}] finish."))

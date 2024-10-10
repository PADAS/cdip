from django.core.management import BaseCommand

from activity_log.models import ActivityLog
from core.db.partitions import (
    PARTITION_INTERVALS,
    ForeignKeyData,
    IndexData,
    PartitionTableTool,
    TableData,
)


class PartitionActivityLogsTable(PartitionTableTool):

    def _create_parent_table(self) -> None:
        sql = f"""
        -- Create the parent table with partitioning
        CREATE TABLE {self.partitioned_table_name}
        (
          created_at timestamp with time zone NOT NULL,
          updated_at timestamp with time zone NOT NULL,
          id uuid NOT NULL,
          log_level integer NOT NULL,
          log_type character varying(5) NOT NULL CHECK (log_type IN ({','.join(self.subpartition_list)})),
          origin character varying(5) NOT NULL,
          value character varying(40) NOT NULL,
          title character varying(200) NOT NULL,
          details jsonb NOT NULL,
          is_reversible boolean NOT NULL,
          revert_data jsonb NOT NULL,
          created_by_id integer,
          integration_id uuid,
          PRIMARY KEY (id, {self.partition_column}, {self.subpartition_column}),
          FOREIGN KEY (integration_id)
              REFERENCES public.integrations_integration (id) DEFERRABLE INITIALLY DEFERRED,
          FOREIGN KEY (created_by_id)
              REFERENCES public.auth_user (id) DEFERRABLE INITIALLY DEFERRED
        ) PARTITION BY RANGE ({self.partition_column}) 
        PARTITION BY LIST ({self.subpartition_list});
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
            primary_key_columns=["id"],
            indexes=indexes,
            foreign_keys=foreign_keys
        )
        if not should_rollback:
            table_data.primary_key_columns.append("created_at")

        tool = PartitionActivityLogsTable(
            original_table_name="activity_log_activitylog",
            partition_column="created_at",
            partition_interval=PARTITION_INTERVALS.MONTHLY.value,
            subpartition_column="log_type",
            subpartition_list=[t.value for t in ActivityLog.LogTypes],
            table_data=table_data,
            migrate_batch_size_per_interval=10000,
        )
        if not should_rollback:
            self.stdout.write(self.style.SUCCESS("Starting partitioning process."))
            tool.partition_table()
        else:
            self.stdout.write(self.style.SUCCESS("Starting rollback process."))
            tool.rollback()
        self.stdout.write(self.style.SUCCESS(f"Process [{'rollback' if should_rollback else 'partition'}] finish."))

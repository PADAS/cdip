from django.db import models
from django.db.models import Q

from activity_log.models import ActivityLog


class ThroughputRollup(models.Model):
    """
    Hourly count of items moving through Gundi, per data provider, destination
    and data type. Only non-zero counts are stored.

    Integrations are referenced by id without a database constraint, so
    deleting an integration neither deletes nor blocks its history.
    """

    class Metric(models.TextChoices):
        RECEIVED = "received", "Received"
        DELIVERED = "delivered", "Delivered"
        DISCARDED = "discarded", "Discarded"
        DUPLICATE = "duplicate", "Duplicate"

    bucket = models.DateTimeField(help_text="Start of the hour (UTC).")
    data_provider_id = models.UUIDField()
    # Set for delivered counts only; received, duplicate and discarded counts
    # belong to the data provider alone.
    destination_id = models.UUIDField(null=True, blank=True)
    object_type = models.CharField(max_length=20, blank=True)
    metric = models.CharField(max_length=10, choices=Metric.choices)
    count = models.PositiveBigIntegerField()

    class Meta:
        ordering = ("-bucket",)
        # PostgreSQL treats NULLs as distinct, so one constraint cannot cover
        # rows with and without a destination. Both lead with the bucket, which
        # also serves the time-range scans of the read side.
        constraints = [
            models.UniqueConstraint(
                fields=["bucket", "data_provider_id", "destination_id", "object_type", "metric"],
                condition=Q(destination_id__isnull=False),
                name="stats_throughput_uniq_dest",
            ),
            models.UniqueConstraint(
                fields=["bucket", "data_provider_id", "object_type", "metric"],
                condition=Q(destination_id__isnull=True),
                name="stats_throughput_uniq_no_dest",
            ),
        ]

    def __str__(self):
        return f"{self.bucket:%Y-%m-%d %H:%M} {self.metric}={self.count}"


class ErrorRollup(models.Model):
    """
    Hourly count of failure entries in the activity log, per integration,
    origin, log value and level. A count is a number of logged failures, not a
    number of distinct failed items.
    """

    bucket = models.DateTimeField(help_text="Start of the hour (UTC).")
    integration_id = models.UUIDField(null=True, blank=True)
    origin = models.CharField(max_length=5, choices=ActivityLog.Origin.choices)
    value = models.CharField(max_length=40)
    log_level = models.IntegerField(choices=ActivityLog.LogLevels.choices)
    count = models.PositiveBigIntegerField()

    class Meta:
        ordering = ("-bucket",)
        constraints = [
            models.UniqueConstraint(
                fields=["bucket", "integration_id", "origin", "value", "log_level"],
                condition=Q(integration_id__isnull=False),
                name="stats_error_uniq_integration",
            ),
            models.UniqueConstraint(
                fields=["bucket", "origin", "value", "log_level"],
                condition=Q(integration_id__isnull=True),
                name="stats_error_uniq_no_integration",
            ),
        ]

    def __str__(self):
        return f"{self.bucket:%Y-%m-%d %H:%M} {self.value}={self.count}"


class RollupRunState(models.Model):
    """
    Single row holding when each rollup task last finished successfully.
    The stats endpoints report these times as the freshness of their data.
    """

    SINGLETON_PK = 1

    frequent_run_completed_at = models.DateTimeField(null=True, blank=True)
    daily_run_completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Rollup run state"
        verbose_name_plural = "Rollup run state"

    def save(self, *args, **kwargs):
        self.pk = self.SINGLETON_PK
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        state, _ = cls.objects.get_or_create(pk=cls.SINGLETON_PK)
        return state

    def __str__(self):
        return "Rollup run state"

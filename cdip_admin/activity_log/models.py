from django.db import models
from django.contrib.auth import get_user_model
from core.models import UUIDAbstractModel, TimestampedModel


User = get_user_model()


class ActivityLog(UUIDAbstractModel, TimestampedModel):

    class LogLevels(models.IntegerChoices):
        DEBUG = 0, "Debug"  # Value, Display
        INFO = 1, "Info"
        WARNING = 2, "Warning"
        ERROR = 3, "Error"

    class LogTypes(models.TextChoices):
        DATA_CHANGE = "cdc", "Data Change"
        EVENT = "ev", "Event"

    class Origin(models.TextChoices):
        PORTAL = "port", "Portal"
        INTEGRATION = "inte", "Integration"
        TRANSFORMER = "tran", "Transformer"
        DISPATCHER = "disp", "Dispatcher"

    log_level = models.IntegerField(
        choices=LogLevels.choices,
        default=LogLevels.INFO,
        db_index=True
    )
    log_type = models.CharField(
        max_length=5,
        choices=LogTypes.choices,
        db_index=True
    )
    origin = models.CharField(
        max_length=5,
        choices=Origin.choices,
        db_index=True
    )
    integration = models.ForeignKey(
        "integrations.Integration",
        on_delete=models.CASCADE,
        related_name="logs_by_integration",
        blank=True,
        null=True
    )
    value = models.SlugField(
        max_length=40,
        db_index=True,
        verbose_name="Value (Identifier)"
    )
    title = models.CharField(max_length=200)
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="logs_by_user",
        null=True,
        blank=True
    )
    details = models.JSONField(
        blank=True,
        default=dict,
        verbose_name="JSON Details"
    )
    is_reversible = models.BooleanField(default=False)
    revert_data = models.JSONField(
        blank=True,
        default=dict,
        verbose_name="JSON Revert Details"
    )

    class Meta:
        ordering = ("-created_at", )

    def __str__(self):
        return f"[{self.created_at}] {self.title}"

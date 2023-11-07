from django.db import models
from django.contrib.auth import get_user_model
from django.apps import apps
from core.models import UUIDAbstractModel, TimestampedModel
from .core import ActivityActions


User = get_user_model()


class ActivityLog(UUIDAbstractModel, TimestampedModel):

    class LogLevels(models.IntegerChoices):
        DEBUG = 10, "Debug"  # Value, Display
        INFO = 20, "Info"
        WARNING = 30, "Warning"
        ERROR = 40, "Error"

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
        indexes = [
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self):
        return f"[{self.created_at}] {self.title}"

    def revert(self):
        if not self.is_reversible:
            return
        action = self.details.get("action")
        model_name = self.revert_data.get("model_name")
        Model = apps.get_model(app_label="integrations", model_name=model_name)
        instance_pk = self.revert_data.get("instance_pk")
        instance = Model.objects.get(pk=instance_pk)
        if action == ActivityActions.CREATED.value:
            instance.delete()
        elif action == ActivityActions.UPDATED.value:
            original_values = self.revert_data.get("original_values")
            for field, value in original_values.items():
                setattr(instance, field, value)
            instance.save()

import datetime

from django.db import models
from django.contrib.auth import get_user_model
from django.apps import apps
from core.models import UUIDAbstractModel, TimestampedModel
import gundi_core.events as system_events
from .core import ActivityActions
from .tasks import publish_configuration_event


User = get_user_model()


class ActivityLogManager(models.Manager):
    def get_queryset(self):
        # Avoid scanning future partitions when querying activity logs
        return super().get_queryset().filter(created_at__lte=datetime.datetime.now(datetime.timezone.utc))


system_events_by_log = {
    "integration_created": {
        "event_model": system_events.IntegrationCreated,
        "payload_model": system_events.IntegrationSummary,
    },
    "integration_updated": {
        "event_model": system_events.IntegrationUpdated,
        "payload_model": system_events.ConfigChanges,
        "exclude_fields": ["created_at", "updated_at"]
    },
    "integration_deleted": {
        "event_model": system_events.IntegrationDeleted,
        "payload_model": system_events.IntegrationSummary,
    },
    "integrationconfiguration_created": {
        "event_model": system_events.ActionConfigCreated,
        "payload_model": system_events.IntegrationActionConfiguration,
    },
    "integrationconfiguration_updated": {
        "event_model": system_events.ActionConfigUpdated,
        "payload_model": system_events.ConfigChanges,
        "exclude_fields": ["created_at", "updated_at", "periodic_task_id"]
    },
    "integrationconfiguration_deleted": {
        "event_model": system_events.ActionConfigDeleted,
        "payload_model": system_events.IntegrationActionConfiguration,
    }
}


def should_publish_event(log):
    if log.log_type == log.LogTypes.DATA_CHANGE and log.value in system_events_by_log:
        if log.value not in system_events_by_log[log.value].get("exclude_fields", []):
            return True
    return False


def build_event_from_log(log):
    if system_event := system_events_by_log.get(log.value):
        # ToDo: Handle parse errors
        data = log.details.get("changes", {})
        payload = system_event["payload_model"](**data)
        event = system_event["event_model"](
            payload=payload
        )
        return event
    return None


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
        on_delete=models.SET_NULL,
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

    objects = ActivityLogManager()

    class Meta:
        ordering = ("-created_at", )
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["integration", "-created_at"]),
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

    def _pre_save(self, *args, **kwargs):
        pass

    def _post_save(self, *args, **kwargs):
        if should_publish_event(log=self) and (event := build_event_from_log(log=self)):
            # Publish events to notify other services about the config changes
            publish_configuration_event.delay(event_data=event.dict())

    def save(self, *args, **kwargs):
        self._pre_save(self, *args, **kwargs)
        super().save(*args, **kwargs)
        self._post_save(self, *args, **kwargs)

import datetime

from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.contrib.auth import get_user_model
from django.apps import apps
from core.models import UUIDAbstractModel, TimestampedModel
import gundi_core.events as gundi_core_events
import gundi_core.schemas.v2 as gundi_core_schemas

from .core import ActivityActions
from .tasks import publish_configuration_event


User = get_user_model()


class ActivityLogManager(models.Manager):
    def get_queryset(self):
        # Avoid scanning future partitions when querying activity logs
        return super().get_queryset().filter(created_at__lte=datetime.datetime.now(datetime.timezone.utc))


system_events_by_log = {
    "integration_created": gundi_core_events.IntegrationCreated,
    "integration_updated": gundi_core_events.IntegrationUpdated,
    "integration_deleted": gundi_core_events.IntegrationDeleted,
    "integrationconfiguration_created": gundi_core_events.ActionConfigCreated,
    "integrationconfiguration_updated": gundi_core_events.ActionConfigUpdated,
    "integrationconfiguration_deleted": gundi_core_events.ActionConfigDeleted,
}


def build_event_from_log(log):
    if log.log_type != log.LogTypes.DATA_CHANGE:
        return None
    log_slug = log.value
    if SystemEvent := system_events_by_log.get(log_slug):
        config_changes = log.details.get("changes", {})
        integration_type = log.integration_type
        # Build the payload accordingly to each event type
        if log_slug == "integration_created":
            integration = log.integration
            integration_summary_type = gundi_core_schemas.IntegrationType(
                id=str(integration_type.id),
                name=integration_type.name,
                value=integration_type.value,
                description=integration_type.description,
                actions=[
                    gundi_core_schemas.IntegrationAction(
                        id=str(action.id),
                        type=str(action.type),
                        name=action.name,
                        value=str(action.value),
                        description=action.description,
                        schema=action.schema,
                        ui_schema=action.ui_schema,
                    )
                    for action in integration_type.actions.all()
                ],
            )
            try:  # Add webhook configs if any
                webhook = integration_type.webhook
            except ObjectDoesNotExist:
                pass
            else:
                integration_summary_type.webhook = gundi_core_schemas.IntegrationWebhook(
                    id=str(webhook.id),
                    name=webhook.name,
                    value=webhook.value,
                    description=webhook.description,
                    webhook_schema=webhook.schema,
                    ui_schema=webhook.ui_schema,
                )
            # Build the event payload
            payload = gundi_core_events.IntegrationSummary(
                id=config_changes.get("id"),
                name=config_changes.get("name"),
                type=integration_summary_type,
                base_url=integration.base_url,
                enabled=integration.enabled,
                owner=gundi_core_schemas.Organization(
                    id=str(integration.owner.id),
                    name=integration.owner.name,
                    description=integration.owner.description
                ),
                default_route=gundi_core_schemas.ConnectionRoute(
                    id=str(integration.default_route.id),
                    name=integration.default_route.name,
                ) if integration.default_route else None,
                additional=integration.additional
            )
        elif log_slug == "integrationconfiguration_created":
            action_id = config_changes.get("action_id")
            action = integration_type.actions.get(id=action_id)
            payload = gundi_core_events.IntegrationActionConfiguration(
                id=config_changes.get("id"),
                integration=config_changes.get("integration_id"),
                action=gundi_core_schemas.IntegrationActionSummary(
                    id=action_id,
                    type=str(action.type),
                    name=action.name,
                    value=str(action.value),
                ),
                data=config_changes.get("data", {})
            )
        elif log_slug == "integration_updated":
            from integrations.models import IntegrationConfiguration

            # Skip publishing events when nothing meaningful for other services has changed
            data_changes = config_changes.get("data", {})
            if (not config_changes and not data_changes) or (
                    len(data_changes) == 1 and data_changes.keys()[0] in ["created_at", "updated_at"]):
                return None
            payload = gundi_core_schemas.IntegrationConfigChanges(
                id=log.details.get("instance_pk"),
                alt_id=log.details.get("alt_id"),
                changes=config_changes
            )
        elif log_slug == "integrationconfiguration_updated":
            # Skip publishing events when nothing meaningful for other services has changed
            data_changes = config_changes.get("data", {})
            if (not config_changes and not data_changes) or (
                    len(data_changes) == 1 and data_changes.keys()[0] in ["periodic_task_id", "created_at",
                                                                          "updated_at"]):
                return None
            integration_id = str(log.integration.id)
            payload = gundi_core_schemas.ActionConfigChanges(
                id=log.details.get("instance_pk"),
                integration_id=integration_id,
                alt_id=log.details.get("alt_id"),
                changes=config_changes
            )
        elif log_slug in ["integration_deleted", "integrationconfiguration_deleted"]:
            payload = gundi_core_schemas.DeletionDetails(
                id=log.details.get("instance_pk"),
                alt_id=log.details.get("alt_id"),
            )
        else:  # Other logs won't produce any system event
            return None
        return SystemEvent(payload=payload)
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

    @property
    def integration_type(self):
        if self.integration:
            return self.integration.type
        return None

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
        # Publish events to notify other services about the config changes as needed
        if event := build_event_from_log(log=self):
            publish_configuration_event.delay(
                event_data=event.dict(),
                attributes={  # Attributes can be used for filtering in subscriptions
                    "gundi_version": "v2",
                    "event_type": event.event_type,
                    "integration_type": self.integration_type.value,
                },
            )

    def save(self, *args, **kwargs):
        self._pre_save(self, *args, **kwargs)
        super().save(*args, **kwargs)
        self._post_save(self, *args, **kwargs)

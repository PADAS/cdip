import json
import uuid
from functools import cached_property
import jsonschema
from core.models import UUIDAbstractModel, TimestampedModel
from django_celery_beat.models import IntervalSchedule, PeriodicTask
from django.db import models, transaction
from django.db.models import Subquery
from django.conf import settings
from django.contrib.auth import get_user_model
from integrations.utils import get_api_key, does_movebank_permissions_config_changed, get_dispatcher_topic_default_name
from model_utils import FieldTracker
from integrations.tasks import recreate_and_send_movebank_permissions_csv_file
from deployments.models import DispatcherDeployment
from deployments.utils import get_dispatcher_defaults_from_gcp_secrets, get_default_dispatcher_name
from activity_log.mixins import ChangeLogMixin


User = get_user_model()


class IntegrationType(UUIDAbstractModel, TimestampedModel):
    name = models.CharField(max_length=200)
    value = models.SlugField(
        max_length=200,
        unique=True,
        verbose_name="Value (Identifier)"
    )
    description = models.TextField(blank=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return f"{self.name}"


class IntegrationAction(UUIDAbstractModel, TimestampedModel):

    class ActionTypes(models.TextChoices):
        AUTHENTICATION = "auth", "Authentication"  # Value, Display
        PULL_DATA = "pull", "Pull Data"
        PUSH_DATA = "push", "Push Data"
        GENERIC = "generic", "Generic Action"

    type = models.CharField(
        max_length=20,
        choices=ActionTypes.choices,
        default=ActionTypes.GENERIC
    )
    name = models.CharField(max_length=200)
    value = models.SlugField(
        max_length=200,
        verbose_name="Value (Identifier)"
    )
    description = models.TextField(
        blank=True,
    )
    schema = models.JSONField(
        blank=True,
        default=dict,
        verbose_name="JSON Schema"
    )
    integration_type = models.ForeignKey(
        "integrations.IntegrationType",
        on_delete=models.CASCADE,
        related_name="actions",
        verbose_name="Integration Type"
    )
    is_periodic_action = models.BooleanField(default=False)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return f"{self.integration_type} - {self.name}"

    def validate_configuration(self, configuration: dict):
        # Helper method to validate a configuration against the Action's schema
        jsonschema.validate(instance=configuration, schema=self.schema)


class Integration(ChangeLogMixin, UUIDAbstractModel, TimestampedModel):
    type = models.ForeignKey(
        "integrations.IntegrationType",
        on_delete=models.CASCADE,
        related_name="integrations_by_type",
        verbose_name="Integration Type",
    )
    owner = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="integrations_by_owner",
        verbose_name="Organization"
    )
    name = models.CharField(max_length=200, blank=True)
    base_url = models.URLField(
        blank=True,
        verbose_name="Base URL"
    )
    enabled = models.BooleanField(default=True)
    default_route = models.ForeignKey(
        "integrations.Route",
        blank=True,
        null=True,
        on_delete=models.PROTECT,
        related_name="integrations_by_rule",
        verbose_name="Default Routing Rule",
    )
    additional = models.JSONField(
        blank=True,
        default=dict,
        verbose_name="Additional JSON Configuration"
    )

    tracker = FieldTracker()

    class Meta:
        ordering = ("owner", "name", )

    def __str__(self):
        return f"{self.owner.name} - {self.name} - {self.type.name}"

    def _pre_save(self, *args, **kwargs):
        # Use pubsub for ER and MoveBank Sites
        # ToDo. We will use PubSub for all the sites in the future, once me migrate SMART and WPSWatch dispatchers
        if self._state.adding and (self.is_er_site or self.is_mb_site):
            if "topic" not in self.additional:
                self.additional.update({"topic": get_dispatcher_topic_default_name(integration=self)})
            if "broker" not in self.additional:
                self.additional.update({"broker": "gcp_pubsub"})

    def _post_save(self, *args, **kwargs):
        created = kwargs.get("created", False)
        # Deploy serverless dispatcher for ER Sites only
        if created and self.is_er_site and settings.GCP_ENVIRONMENT_ENABLED:
            DispatcherDeployment.objects.create(
                name=get_default_dispatcher_name(integration=self),
                integration=self,
                configuration=get_dispatcher_defaults_from_gcp_secrets()
            )

    def save(self, *args, **kwargs):
        with self.tracker:
            self._pre_save(self, *args, **kwargs)
            created = self._state.adding
            super().save(*args, **kwargs)
            kwargs["created"] = created
            self._post_save(self, *args, **kwargs)

    @property
    def configurations(self):
        return self.configurations_by_integration.all()

    @property
    def routing_rules(self):
        return self.routing_rules_by_provider.all()

    @property
    def destinations(self):
        destinations = self.routing_rules.values("destinations").distinct()
        return Integration.objects.filter(id__in=Subquery(destinations))

    @cached_property
    def api_key(self):
        return get_api_key(integration=self)

    @property
    def is_er_site(self):
        return self.type.value.lower().strip().replace("_", "") == "earthranger"

    @property
    def is_mb_site(self):
        return self.type.value.lower().strip().replace("_", "") == "movebank"

    def create_missing_configurations(self):
        for action in self.type.actions.all():
            if not self.configurations.filter(action=action).exists():
                IntegrationConfiguration.objects.create(
                    integration=self,
                    action=action,
                    data={}  # Empty configuration by default
                )


class IntegrationConfiguration(ChangeLogMixin, UUIDAbstractModel, TimestampedModel):
    integration = models.ForeignKey(
        "integrations.Integration",
        on_delete=models.CASCADE,
        related_name="configurations_by_integration"
    )
    action = models.ForeignKey(
        "integrations.IntegrationAction",
        on_delete=models.CASCADE,
        related_name="configurations_by_action"
    )
    data = models.JSONField(
        blank=True,
        default=dict,
        verbose_name="JSON Configuration"
    )

    tracker = FieldTracker()

    class Meta:
        ordering = ("-updated_at", )

    def __str__(self):
        return f"{self.data}"

    def _pre_save(self, *args, **kwargs):
        pass

    def _post_save(self, *args, **kwargs):
        if does_movebank_permissions_config_changed(self, "v2"):
            # Movebank permissions file needs to be recreated
            transaction.on_commit(
                lambda: recreate_and_send_movebank_permissions_csv_file.delay()
            )

        if self.action.is_periodic_action:
            # Get or create interval and periodic task for this config
            schedule, created = IntervalSchedule.objects.get_or_create(
                every=10,
                period=IntervalSchedule.MINUTES,
            )

            PeriodicTask.objects.get_or_create(
                interval=schedule,
                name=f"Action: '{self.action.value}' schedule (Integration: '{self.integration}')",
                task="integrations.tasks.run_integration",
                kwargs=json.dumps(
                    {
                        "integration_id": str(self.integration_id),
                        "action_id": self.action.value,
                        "pubsub_topic": f"{self.integration.type.value}-actions-topic"
                    }
                ),
            )

    def save(self, *args, **kwargs):
        with self.tracker:
            self._pre_save(self, *args, **kwargs)
            super().save(*args, **kwargs)
            self._post_save(self, *args, **kwargs)


class IntegrationState(ChangeLogMixin, UUIDAbstractModel, TimestampedModel):
    integration = models.OneToOneField(
        "integrations.Integration",
        on_delete=models.CASCADE,
        related_name="state"
    )
    data = models.JSONField(
        blank=True,
        default=dict,
        verbose_name="JSON State"
    )

    class Meta:
        ordering = ("id",)

    def __str__(self):
        return f"{self.data}"


class RouteConfiguration(ChangeLogMixin, UUIDAbstractModel, TimestampedModel):
    name = models.CharField(max_length=200, blank=True)
    data = models.JSONField(
        blank=True,
        default=dict,
        verbose_name="JSON Configuration"
    )
    integration_field = "first_route_provider"

    @property
    def first_route_provider(self):
        return self.routing_rules_by_configuration.first().data_providers.first()

    class Meta:
        ordering = ("name", )

    def __str__(self):
        return f"{self.name}"


class RouteProvider(ChangeLogMixin, models.Model):
    integration = models.ForeignKey("integrations.Integration", on_delete=models.CASCADE)
    route = models.ForeignKey("integrations.Route", on_delete=models.CASCADE)


class RouteDestination(ChangeLogMixin, models.Model):
    integration = models.ForeignKey("integrations.Integration", on_delete=models.CASCADE)
    route = models.ForeignKey("integrations.Route", on_delete=models.CASCADE)


class Route(ChangeLogMixin, UUIDAbstractModel, TimestampedModel):
    name = models.CharField(max_length=200)
    owner = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="routing_rules_by_owner",
        verbose_name="Owner"
    )
    data_providers = models.ManyToManyField(
        "integrations.Integration",
        related_name="routing_rules_by_provider",
        blank=True,
        verbose_name="Data Providers",
        through="integrations.RouteProvider"
    )
    destinations = models.ManyToManyField(
        "integrations.Integration",
        related_name="routing_rules_by_destination",
        blank=True,
        verbose_name="Destinations",
        through="integrations.RouteDestination"
    )
    configuration = models.ForeignKey(
        "integrations.RouteConfiguration",
        on_delete=models.SET_NULL,
        related_name="routing_rules_by_configuration",
        verbose_name="Route Configuration",
        blank=True,
        null=True
    )
    # extra settings such as subject_type or provider_key maybe set here
    additional = models.JSONField(
        blank=True,
        default=dict,
        verbose_name="Additional JSON Configuration"
    )
    integration_field = "first_provider"

    @property
    def first_provider(self):
        return self.data_providers.first()

    class Meta:
        ordering = ("owner", "name", )

    def __str__(self):
        return f"{self.owner}: {self.name}"


class SourceFilter(ChangeLogMixin, UUIDAbstractModel, TimestampedModel):

    class SourceFilterTypes(models.TextChoices):
        SOURCE_LIST = "list", "Select Sources By ID"  # Value, Display
        GEO_BOUNDARY = "geoboundary", "GEO Boundary"
        TIME = "time", "Timeframe"

    type = models.CharField(
        max_length=20,
        choices=SourceFilterTypes.choices,
        default=SourceFilterTypes.SOURCE_LIST
    )
    order_number = models.PositiveIntegerField(default=0, db_index=True)
    name = models.CharField(max_length=200, blank=True)
    description = models.TextField(
        blank=True,
    )
    selector = models.JSONField(
        blank=True,
        default=dict,
        verbose_name="JSON Selector"
    )
    routing_rule = models.ForeignKey(
        "integrations.Route",
        on_delete=models.CASCADE,
        related_name="source_filters",
        verbose_name="Routing Rule"
    )
    integration_field = "routing_rule__first_provider"

    class Meta:
        ordering = ("routing_rule", "order_number",)

    def __str__(self):
        return f"{self.name} {self.type}"


class SourceConfiguration(ChangeLogMixin, UUIDAbstractModel, TimestampedModel):
    name = models.CharField(max_length=200, blank=True)
    data = models.JSONField(
        blank=True,
        default=dict,
        verbose_name="JSON Configuration"
    )

    class Meta:
        ordering = ("name", )

    def __str__(self):
        return f"{self.name}"


class Source(ChangeLogMixin, UUIDAbstractModel, TimestampedModel):
    name = models.CharField(max_length=200, blank=True)
    external_id = models.CharField(
        max_length=200,
        verbose_name="External Source ID",
        db_index=True
    )
    integration = models.ForeignKey(
        "integrations.Integration",
        on_delete=models.CASCADE,
        related_name="sources_by_integration"
    )
    configuration = models.ForeignKey(
        "integrations.SourceConfiguration",
        on_delete=models.SET_NULL,
        related_name="sources_by_configuration",
        verbose_name="Source Configuration",
        blank=True,
        null=True
    )
    additional = models.JSONField(
        blank=True,
        default=dict,
        verbose_name="Additional JSON Configuration",
    )

    def __str__(self):
        return f"{self.external_id} - {self.integration.type.name}"

    class Meta:
        ordering = ("integration", "external_id")
        unique_together = ("integration", "external_id")
        indexes = [
            models.Index(fields=["integration", "external_id"]),
        ]


class SourceState(ChangeLogMixin, UUIDAbstractModel, TimestampedModel):
    source = models.OneToOneField(
        "integrations.Source",
        on_delete=models.CASCADE,
        related_name="state"
    )
    data = models.JSONField(
        blank=True,
        default=dict,
        verbose_name="JSON State"
    )
    integration_field = "source__integration"

    @property
    def owner(self):
        return self.source.integration.owner

    class Meta:
        indexes = [
            models.Index(fields=["source", "created_at"]),
        ]
        ordering = ("source", "-created_at")

    def __str__(self):
        return f"{self.data}"


class GundiTrace(UUIDAbstractModel, TimestampedModel):
    object_id = models.UUIDField(db_index=True, default=uuid.uuid4, editable=False)
    object_type = models.CharField(max_length=20, db_index=True, blank=True)
    related_to = models.UUIDField(db_index=True, null=True, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="objects_by_user",
        null=True,
        blank=True
    )
    # Gundi 2.x uses the new Integration model
    data_provider = models.ForeignKey(
        "integrations.Integration",
        on_delete=models.CASCADE,
        related_name="objects_by_provider",
    )
    destination = models.ForeignKey(
        "integrations.Integration",
        on_delete=models.CASCADE,
        related_name="objects_by_destination",
        null=True,
        blank=True
    )
    delivered_at = models.DateTimeField(blank=True, null=True, db_index=True)
    external_id = models.CharField(max_length=250, db_index=True, null=True, blank=True)  # Object ID in the destination system
    has_error = models.BooleanField(default=False)
    error = models.CharField(max_length=500, null=True, blank=True, default="")
    is_duplicate = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["updated_at"]),
        ]
        ordering = ("-created_at", )

    def __str__(self):
        return f"{self.object_id}"

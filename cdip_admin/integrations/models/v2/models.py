import json
import logging
import uuid

from functools import cached_property
import jsonschema
import psycopg2
import requests
import google.oauth2.id_token
from urllib.parse import urljoin, urlparse
from core.models import UUIDAbstractModel, TimestampedModel
from django_celery_beat.models import IntervalSchedule, PeriodicTask
from django.db import models, transaction, IntegrityError
from django.db.models import Subquery
from django.conf import settings
from django.contrib.auth import get_user_model

from integrations.utils import get_api_key, does_movebank_permissions_config_changed, get_dispatcher_topic_default_name
from model_utils import FieldTracker
from integrations.tasks import (
    update_mb_permissions_for_group,
    recreate_and_send_movebank_permissions_csv_file,
    calculate_integration_statuses
)
from deployments.models import DispatcherDeployment
from deployments.utils import get_dispatcher_defaults_from_gcp_secrets, get_default_dispatcher_name
from activity_log.mixins import ChangeLogMixin


logger = logging.getLogger(__name__)


User = get_user_model()


class IntegrationType(UUIDAbstractModel, TimestampedModel):
    name = models.CharField(max_length=200)
    value = models.SlugField(
        max_length=200,
        unique=True,
        verbose_name="Value (Identifier)"
    )
    description = models.TextField(blank=True)
    service_url = models.URLField(blank=True, null=True, default="")
    help_center_url = models.URLField(blank=True, null=True, default="")

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
    ui_schema = models.JSONField(
        blank=True,
        default=dict,
        verbose_name="UI Schema"
    )
    integration_type = models.ForeignKey(
        "integrations.IntegrationType",
        on_delete=models.CASCADE,
        related_name="actions",
        verbose_name="Integration Type"
    )
    is_periodic_action = models.BooleanField(default=False)
    crontab_schedule = models.ForeignKey(
        "django_celery_beat.CrontabSchedule",
        on_delete=models.SET_NULL,
        related_name="actions_by_crontab_schedule",
        blank=True,
        null=True
    )

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return f"{self.integration_type} - {self.name}"

    def validate_configuration(self, configuration: dict):
        # Helper method to validate a configuration against the Action's schema
        jsonschema.validate(instance=configuration, schema=self.schema)

    def execute(self, integration, config_overrides=None, run_in_background=False):
        service_url = integration.type.service_url
        if not service_url:
            raise ValueError(f"Integration Type '{integration.type}' does not have a service endpoint configured")

        # Build the URL for the action runner endpoint
        actions_execute_path = "v1/actions/execute"
        actions_execute_url = urljoin(service_url, actions_execute_path)

        # Make an authorized request to the action runner endpoint using google.oauth2.id_token
        auth_req = google.auth.transport.requests.Request()
        id_token = google.oauth2.id_token.fetch_id_token(auth_req, service_url)
        auth_headers = {"Authorization": f"Bearer {id_token}"}
        response = requests.post(
            url=actions_execute_url,
            headers=auth_headers,
            json={
                "integration_id": str(integration.id),
                "action_id": self.value,
                "run_in_background": run_in_background,
                "config_overrides": config_overrides,
            }
        )
        response.raise_for_status()
        return response.json()


class IntegrationWebhook(UUIDAbstractModel, TimestampedModel):
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
    ui_schema = models.JSONField(
        blank=True,
        default=dict,
        verbose_name="UI Schema"
    )
    integration_type = models.OneToOneField(
        "integrations.IntegrationType",
        on_delete=models.CASCADE,
        related_name="webhook",
        verbose_name="Integration Type"
    )

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return f"{self.integration_type} - {self.name}"

    def validate_configuration(self, configuration: dict):
        # Helper method to validate a configuration against the webhook schema
        jsonschema.validate(instance=configuration, schema=self.schema)


class ProvidersManager(models.Manager):
    def get_queryset(self):
        # Return integrations being used as a provider in any connection
        return super().get_queryset().filter(
            routing_rules_by_provider__isnull=False
        ).distinct()


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
        on_delete=models.SET_NULL,
        related_name="integrations_by_rule",
        verbose_name="Default Routing Rule",
    )
    additional = models.JSONField(
        blank=True,
        default=dict,
        verbose_name="Additional JSON Configuration"
    )

    objects = models.Manager()
    providers = ProvidersManager()
    tracker = FieldTracker()

    class Meta:
        ordering = ("owner", "name", )

    def __str__(self):
        return f"{self.owner.name} - {self.name} - {self.type.name}"

    def _pre_save(self, *args, **kwargs):
        # Setup topic and broker for destination sites
        if self._state.adding and any(
                [self.is_er_site, self.is_smart_site, self.is_mb_site, self.is_wpswatch_site, self.is_traptagger_site]
        ):
            if "topic" not in self.additional:
                self.additional.update({"topic": get_dispatcher_topic_default_name(integration=self)})
            self.additional.setdefault('broker', 'gcp_pubsub')

        if self.is_er_site:
            # Cleanup
            url_parse = urlparse(self.base_url, "https")
            netloc = url_parse.netloc or url_parse.path

            scheme = url_parse.scheme
            if scheme == "http":
                scheme = "https"

            self.base_url = f"{scheme}://{netloc}/"

    def _post_save(self, *args, **kwargs):
        created = kwargs.get("created", False)
        # Reflect the enabled status in the health status asap
        if created or self.tracker.has_changed("enabled"):
            calculate_integration_statuses([str(self.id)])
        if created:
            # Deploy serverless dispatchers for destinations
            if settings.GCP_ENVIRONMENT_ENABLED and any(
                    [self.is_er_site, self.is_smart_site, self.is_wpswatch_site, self.is_traptagger_site]
            ):
                if self.is_smart_site:
                    secret_id = settings.DISPATCHER_DEFAULTS_SECRET_SMART
                elif self.is_wpswatch_site:
                    secret_id = settings.DISPATCHER_DEFAULTS_SECRET_WPSWATCH
                elif self.is_traptagger_site:
                    secret_id = settings.DISPATCHER_DEFAULTS_SECRET_TRAPTAGGER
                else:
                    secret_id = settings.DISPATCHER_DEFAULTS_SECRET
                DispatcherDeployment.objects.create(
                    name=get_default_dispatcher_name(integration=self),
                    integration=self,
                    configuration=get_dispatcher_defaults_from_gcp_secrets(secret_id=secret_id)
                )

            # Create default healthcheck settings and status
            IntegrationStatus.objects.get_or_create(integration=self)
            HealthCheckSettings.objects.get_or_create(integration=self)
        else:  # Updated
            if self.tracker.has_changed("enabled"):
                # Disable/Enable related periodic tasks for pull actions
                for config in self.configurations.filter(action__type=IntegrationAction.ActionTypes.PULL_DATA):
                    if config.action.is_periodic_action and config.periodic_task:
                        config.periodic_task.enabled = self.enabled
                        config.periodic_task.save()

    def save(self, *args, **kwargs):
        with self.tracker:
            self._pre_save(self, *args, **kwargs)
            created = self._state.adding
            super().save(*args, **kwargs)
            kwargs["created"] = created
            self._post_save(self, *args, **kwargs)

    def delete(self, *args, **kwargs):
        try:  # Delete the integration
            super().delete(*args, **kwargs)
        except IntegrityError as e:  # handle detached partitions referencing the integration
            cause = getattr(e, "__cause__", None)
            if not cause:
                logger.warning(f"Couldn't determine the cause of the IntegrityError deleting integration {self.id}: __cause__: {cause}")
                raise e
            if isinstance(cause, psycopg2.errors.ForeignKeyViolation) and "activity_log_activitylog" in str(e):
                logger.debug(f"Cleaning activity log references found found detached partitions")
                # Clean activity log references
                self._clean_detached_activity_log_references()
                # Try again
                super().delete(*args, **kwargs)
            else:
                raise e

    @property
    def configurations(self):
        return self.configurations_by_integration.all()

    @property
    def webhook_configuration(self):
        return self.webhook_config_by_integration

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

    @property
    def is_smart_site(self):
        return self.type.value.lower().strip().replace("_", "") == "smartconnect"

    @property
    def is_wpswatch_site(self):
        return self.type.value.lower().strip().replace("_", "") == "wpswatch"

    @property
    def is_traptagger_site(self):
        return self.type.value.lower().strip().replace("_", "") == "traptagger"

    def create_missing_configurations(self):
        for action in self.type.actions.all():
            if not self.configurations.filter(action=action).exists():
                IntegrationConfiguration.objects.create(
                    integration=self,
                    action=action,
                    data={}  # Empty configuration by default
                )

    def _clean_detached_activity_log_references(self):
        from django.db import connection

        with connection.cursor() as cursor:
            # Clean references in the backup table
            self._set_fk_references_null(cursor, table_name="activity_log_activitylog_original")
            # Clean references in the detached subpartitions partitions
            get_subpartitions_sql = """
                SELECT relname
                FROM pg_class
                WHERE relname LIKE 'activity_log_activitylog_ev_p%' 
                  AND relkind = 'r';
            """
            cursor.execute(get_subpartitions_sql)
            sub_partitions = [row[0] for row in cursor.fetchall()]
            for partition in sub_partitions:
                self._set_fk_references_null(cursor=cursor, table_name=partition)

    def _set_fk_references_null(self, cursor, table_name):
        update_sql = f"""
            UPDATE {table_name}
            SET integration_id = NULL
            WHERE integration_id = '{str(self.id)}';
        """
        cursor.execute(update_sql)


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
    periodic_task = models.OneToOneField(
        "django_celery_beat.PeriodicTask",
        on_delete=models.SET_NULL,
        related_name="configurations_by_periodic_task",
        blank=True,
        null=True
    )

    logs_id_field = "action_value"

    tracker = FieldTracker()

    class Meta:
        ordering = ("-updated_at", )

    def __str__(self):
        return f"{self.data}"

    @cached_property
    def action_value(self):
        return self.action.value

    def _pre_save(self, *args, **kwargs):
        pass

    def _post_save(self, *args, **kwargs):
        if does_movebank_permissions_config_changed(self, "v2"):
            # Movebank permissions file needs to be recreated
            transaction.on_commit(
                lambda: recreate_and_send_movebank_permissions_csv_file.delay()
            )

        if self.action.is_periodic_action and not self.periodic_task:
            task_name = f"Run '{self.action.name}' on '{self.integration.name}'"[:200]
            periodic_task_params = {
                "name": task_name,
                "task": "integrations.tasks.run_integration",
                "kwargs": json.dumps({
                    "integration_id": str(self.integration_id),
                    "action_id": self.action.value,
                    "pubsub_topic": f"{self.integration.type.value}-actions-topic"
                })
            }
            # Check for custom crontab schedule
            if self.action.crontab_schedule:
                periodic_task_params["crontab"] = self.action.crontab_schedule
            else:  # Use a default interval
                schedule, created = IntervalSchedule.objects.get_or_create(
                    every=10,
                    period=IntervalSchedule.MINUTES,
                )
                periodic_task_params["interval"] = schedule

            self.periodic_task = PeriodicTask.objects.create(**periodic_task_params)
            self.save(update_fields=["periodic_task"], execute_post_save=False)

    def save(self, *args, **kwargs):
        with self.tracker:
            execute_post_save = kwargs.pop("execute_post_save", True)
            self._pre_save(self, *args, **kwargs)
            super().save(*args, **kwargs)
            if execute_post_save:
                self._post_save(self, *args, **kwargs)


class WebhookConfiguration(ChangeLogMixin, UUIDAbstractModel, TimestampedModel):
    integration = models.OneToOneField(
        "integrations.Integration",
        on_delete=models.CASCADE,
        related_name="webhook_config_by_integration"
    )
    webhook = models.ForeignKey(
        "integrations.IntegrationWebhook",
        on_delete=models.CASCADE,
        related_name="webhook_config_by_webhook"
    )
    data = models.JSONField(
        blank=True,
        default=dict,
        verbose_name="JSON Configuration"
    )

    class Meta:
        ordering = ("-updated_at", )

    def __str__(self):
        return f"{self.webhook.name} - Configuration for {self.integration.name}"


class IntegrationState(ChangeLogMixin, UUIDAbstractModel, TimestampedModel):
    # State is persistent information used by the integration in different executions
    # ToDo: This may be moved from the portal to the integrations db as part of the EDA
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


class IntegrationStatus(UUIDAbstractModel, TimestampedModel):
    # Status contains information about the health of the integration and other metrics

    class Status(models.TextChoices):
        HEALTHY = "healthy", "Healthy"  # Value, Display
        UNHEALTHY = "unhealthy", "Unhealthy"
        DISABLED = "disabled", "Disabled"

    integration = models.OneToOneField(
        "integrations.Integration",
        on_delete=models.CASCADE,
        related_name="status"
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.HEALTHY,
        db_index=True
    )
    status_details = models.CharField(max_length=200, blank=True, default="")
    last_delivery = models.DateTimeField(blank=True, null=True, db_index=True)

    class Meta:
        ordering = ("-updated_at",)
        verbose_name_plural = "Integration statuses"

    def __str__(self):
        return f"{self.status}"


class HealthCheckSettings(UUIDAbstractModel, TimestampedModel):
    # Settings for the health check of the integration
    integration = models.OneToOneField(
        "integrations.Integration",
        on_delete=models.CASCADE,
        related_name="health_check_settings"
    )
    error_count_threshold = models.PositiveIntegerField(default=3)
    time_window_minutes = models.PositiveIntegerField(default=60)

    class Meta:
        ordering = ("-updated_at",)
        verbose_name_plural = "Integration health check settings"

    def __str__(self):
        return f"Health check settings for integration {self.integration_id}"


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

    logs_id_field = "external_id"

    def __str__(self):
        return f"{self.external_id} - {self.integration.type.name}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Check if Movebank is within destinations
        if any([a.is_mb_site for a in self.integration.destinations.all()]):
            # Handle devices for MB destinations
            transaction.on_commit(
                lambda: update_mb_permissions_for_group.delay(
                    instance_pk=self.pk,
                    gundi_version="v2"
                )
            )

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
    source = models.ForeignKey(
        "integrations.Source",
        on_delete=models.CASCADE,
        related_name="objects_by_source",
        null=True,
        blank=True
    )
    delivered_at = models.DateTimeField(blank=True, null=True, db_index=True)
    object_updated_at = models.DateTimeField(blank=True, null=True, db_index=True)
    last_update_delivered_at = models.DateTimeField(blank=True, null=True, db_index=True)
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


class IntegrationMetrics(UUIDAbstractModel, TimestampedModel):
    integration = models.ForeignKey(
        "integrations.Integration",
        on_delete=models.CASCADE,
        related_name="metrics"
    )
    data_frequency_minutes = models.PositiveIntegerField(default=0)
    data_frequency_minutes_min = models.PositiveIntegerField(default=0)
    data_frequency_minutes_max = models.PositiveIntegerField(default=0)


    class Meta:
        ordering = ("-created_at", )

    def __str__(self):
        return f"{self.integration.name} - Data Frequency: {self.data_frequency_minutes} minutes"

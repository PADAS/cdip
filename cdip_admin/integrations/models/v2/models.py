from core.models import UUIDAbstractModel, TimestampedModel
from django.db import models


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

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return f"{self.name}"


class Integration(UUIDAbstractModel, TimestampedModel):
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
    default_routing_rule = models.ForeignKey(
        "integrations.RoutingRule",
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

    class Meta:
        ordering = ("owner", "name", )

    def __str__(self):
        return f"{self.owner.name} - {self.name} - {self.type.name}"

    @property
    def configurations(self):
        return self.configurations_by_integration.all()


class IntegrationConfiguration(UUIDAbstractModel, TimestampedModel):
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

    class Meta:
        ordering = ("id", )

    def __str__(self):
        return f"{self.data}"


class IntegrationState(UUIDAbstractModel, TimestampedModel):
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


class RoutingRuleType(UUIDAbstractModel, TimestampedModel):
    name = models.CharField(max_length=200)
    slug = models.SlugField(
        max_length=200,
        unique=True
    )
    description = models.TextField(blank=True)
    schema = models.JSONField(
        blank=True,
        default=dict,
        verbose_name="JSON Schema"
    )

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return f"{self.name}"


class RoutingRule(UUIDAbstractModel, TimestampedModel):
    type = models.ForeignKey(
        "integrations.RoutingRuleType",
        on_delete=models.CASCADE,
        related_name="routing_rules_by_type",
        verbose_name="Type",
        help_text="The type of routing rule.",
    )
    name = models.CharField(max_length=200)
    owner = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="routing_rules_by_owner",
        help_text="Organization that owns the data.",
    )
    data_providers = models.ManyToManyField(
        "integrations.Integration",
        related_name="routing_rules_by_provider",
        blank=True,
        help_text="Source Integrations where the data is extracted from",
    )
    destinations = models.ManyToManyField(
        "integrations.Integration",
        related_name="routing_rules_by_destination",
        blank=True,
        help_text="Destination Integrations where the data will be delivered.",
    )
    source_filter = models.JSONField(
        blank=True,
        default=dict,
        verbose_name="JSON Selector"
    )
    # extra settings such as subject_type or provider_key maybe set here
    additional = models.JSONField(
        blank=True,
        default=dict,
        verbose_name="Additional JSON Configuration"
    )

    class Meta:
        ordering = ("owner", "name", )

    def __str__(self):
        return f"{self.type.name}: {self.name}"


class Source(UUIDAbstractModel, TimestampedModel):
    name = models.CharField(max_length=200, blank=True)
    external_id = models.CharField(
        max_length=200, help_text="Id sent by the data provider"
    )
    integration = models.ForeignKey(
        "integrations.Integration",
        on_delete=models.CASCADE,
        related_name="sources_by_integration"
    )
    configuration = models.ForeignKey(
        "integrations.Source",
        on_delete=models.CASCADE,
        related_name="sources_by_configuration",
        blank=True,
        null=True
    )
    additional = models.JSONField(
        blank=True,
        default=dict,
        help_text="Additional config(s)",
    )

    def __str__(self):
        return f"{self.external_id} - {self.integration.type.name}"

    def _pre_save(self, *args, **kwargs):
        pass

    def _post_save(self, *args, **kwargs):
        # Ensure the device is added to the default group after creation
        default_routing_rule = self.integration.default_routing_rule
        default_routing_rule.devices.add(self)

    def save(self, *args, **kwargs):
        self._pre_save(self, *args, **kwargs)
        super().save(*args, **kwargs)
        self._post_save(self, *args, **kwargs)

    class Meta:
        ordering = ("integration", "external_id")
        unique_together = ("integration", "external_id")


class SourceConfiguration(UUIDAbstractModel, TimestampedModel):
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


class SourceState(UUIDAbstractModel, TimestampedModel):
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

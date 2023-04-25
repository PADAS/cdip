from core.models import UUIDAbstractModel, TimestampedModel
from django.db import models


class IntegrationType(UUIDAbstractModel, TimestampedModel):
    name = models.CharField(max_length=200)
    slug = models.SlugField(
        max_length=200,
        unique=True,
        verbose_name="Slug Identifier"
    )
    description = models.TextField(blank=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return f"{self.name}"


class IntegrationAction(UUIDAbstractModel, TimestampedModel):
    name = models.CharField(max_length=200, verbose_name="Type")
    slug = models.SlugField(
        max_length=200,
        unique=True,
        verbose_name="Slug Identifier"
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
    destinations = models.ManyToManyField(
        "integrations.Integration",
        related_name="routing_rules",
        blank=True,
        help_text="Destination Integrations where the data will be delivered.",
    )
    source_selector = models.JSONField(
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





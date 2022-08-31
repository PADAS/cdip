import uuid
from django.db import models, transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from fernet_fields import EncryptedCharField

from cdip_admin import celery
from core.models import TimestampedModel
from core.fields import APIConsumerField
from organizations.models import Organization, OrganizationGroup

from simple_history.models import HistoricalRecords


# This is where the general information for a configuration will be stored
# This could be an inbound or outbound type
# Example Inbound Integrations: Savannah Tracking Collars, Garmin Inreach
class InboundIntegrationType(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=200, verbose_name="Type")
    slug = models.SlugField(
        max_length=200,
        unique=True,
        help_text="Identifier using lowercase letters and no spaces."
    )
    description = models.TextField(
        blank=True,
        help_text="Optional field - description of the Technology or Service."
    )
    history = HistoricalRecords()

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return f"{self.name}"


# This is where the general information for a configuration will be stored
# This could be an inbound or outbound type
# Example Outbound Integrations: EarthRanger, SMART, WpsWatch
class OutboundIntegrationType(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=200)
    slug = models.SlugField(
        max_length=200,
        unique=True,
        help_text="Identifier using lowercase letters and no spaces.")
    description = models.TextField(
        blank=True,
        help_text="Optional - general description of the destination system.")
    use_endpoint = models.BooleanField(default=False)
    use_login = models.BooleanField(default=False)
    use_password = models.BooleanField(default=False)
    use_token = models.BooleanField(default=False)
    history = HistoricalRecords()

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return f"{self.name}"


class BridgeIntegrationType(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=200, verbose_name="Type")
    slug = models.SlugField(max_length=200, unique=True)
    description = models.TextField(blank=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return f"{self.name}"


# This is the information for a given configuration this will include a specific organizations account information
# Or organization specific information
class OutboundIntegrationConfiguration(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    type = models.ForeignKey(
        OutboundIntegrationType,
        on_delete=models.CASCADE,
        verbose_name="Type",
        help_text="Destination system"
    )
    owner = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        help_text="Destination system configured as an Outbound Type"
    )
    name = models.CharField(max_length=200, blank=True)
    state = models.JSONField(
        blank=True,
        null=True,
        help_text="Additional configuration(s).")
    endpoint = models.URLField(blank=True)
    login = models.CharField(max_length=200, blank=True)
    password = EncryptedCharField(max_length=200, blank=True)
    token = EncryptedCharField(max_length=200, blank=True)
    additional = models.JSONField(default=dict, blank=True)
    enabled = models.BooleanField(default=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return f"{self.type.name} - {self.owner.name} - {self.name}"


# This is the information for a given configuration this will include a specific organizations account information
# Or organization specific information
class InboundIntegrationConfiguration(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    type = models.ForeignKey(
        InboundIntegrationType,
        on_delete=models.CASCADE,
        help_text="Data Provider configured as an Inbound Type.",
        verbose_name="Type"
    )
    owner = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        help_text="EarthRanger site or destination system that owns the data.",
        verbose_name="Owner"
    )
    name = models.CharField(max_length=200, blank=True)
    endpoint = models.URLField(blank=True)
    state = models.JSONField(
        blank=True,
        null=True,
        help_text="Additional integration configuration(s).",
        verbose_name="State",
    )
    login = models.CharField(max_length=200, blank=True)
    password = EncryptedCharField(max_length=200, blank=True)
    token = EncryptedCharField(max_length=200, blank=True)
    provider = models.CharField(
        verbose_name="Provider_key",
        max_length=200,
        blank=True,
        help_text="This value will be used as the 'provider_key' when sending data to EarthRanger.",
    )
    enabled = models.BooleanField(default=True)
    history = HistoricalRecords(excluded_fields=['state'])

    default_devicegroup = models.ForeignKey(
        "DeviceGroup",
        blank=True,
        null=True,
        on_delete=models.PROTECT,
        related_name="inbound_integration_configuration",
        related_query_name="inbound_integration_configurations",
        verbose_name="Default Device Group",
        help_text="Device group that will be used unless a different group is specified by the data provider or integration."
    )

    consumer_id = models.CharField(max_length=200, blank=True)

    # api_consumer = APIConsumerField(verbose_name='API Key', null=True, blank=True)

    def __str__(self):
        return f"Type:{self.type.name} Owner:{self.owner.name} Name:{self.name}"

    def save(self, *args, **kwargs):
        if not self.provider:
            self.provider = self.type.slug.lower()
        else:
            self.provider = self.provider.lower()
        super().save(*args, **kwargs)


class GFWInboundConfigurationManager(models.Manager):
    history = HistoricalRecords()

    def get_queryset(self):
        return super().get_queryset().filter(type__slug="gfw")


class GFWInboundConfiguration(InboundIntegrationConfiguration):
    history = HistoricalRecords()

    class Meta:
        proxy = True

    objects = GFWInboundConfigurationManager()


# This is the information for a given configuration this will include a specific organizations account information
# Or organization specific information


class BridgeIntegration(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    type = models.ForeignKey(BridgeIntegrationType, on_delete=models.CASCADE)
    owner = models.ForeignKey(Organization, on_delete=models.CASCADE)
    name = models.CharField(max_length=200, blank=True)
    state = models.JSONField(blank=True, null=True)
    additional = models.JSONField(default=dict, blank=True)
    enabled = models.BooleanField(default=True)
    consumer_id = models.CharField(max_length=200, blank=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ("name",)


class SubjectType(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    value = models.SlugField(max_length=200, unique=True)
    display_name = models.CharField(max_length=200)
    history = HistoricalRecords()

    def __str__(self):
        return f"{self.display_name}"


# This is where the information is stored for a specific device
class Device(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    inbound_configuration = models.ForeignKey(
        InboundIntegrationConfiguration, on_delete=models.CASCADE
    )
    name = models.CharField(max_length=200, blank=True)
    external_id = models.CharField(
        max_length=200,
        help_text="Id sent by the data provider"
    )
    subject_type = models.ForeignKey(
        SubjectType,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        help_text="Default subject type. Can be overriden by the integration or data provider"
    )
    additional = models.JSONField(
        blank=True,
        default=dict,
        help_text="Additional config(s)",

    )
    history = HistoricalRecords()

    @property
    def owner(self):
        return self.inbound_configuration.owner

    def __str__(self):
        return f"{self.external_id} - {self.inbound_configuration.type.name}"

    class Meta:
        ordering = ("inbound_configuration", "external_id")
        unique_together = ("inbound_configuration", "external_id")


# This is where the information is stored for a specific device
class DeviceState(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    device = models.ForeignKey(Device, on_delete=models.CASCADE)
    # TODO: Update end_state as Json
    end_state = models.CharField(max_length=200)
    state = models.JSONField(blank=True, null=True)

    @property
    def owner(self):
        return self.device.inbound_configuration.owner

    class Meta:
        indexes = [
            models.Index(fields=["device", "created_at"]),
        ]
        ordering = ("device", "-created_at")

    def __str__(self):
        return f"{self.state}"


# This allows an organization to group a set of devices to send information to a series of outbound configs
# Must be tied to an OrgGroup
class DeviceGroup(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=200)
    owner = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        help_text="Organization that owns the data."
    )
    destinations = models.ManyToManyField(
        OutboundIntegrationConfiguration,
        related_name="devicegroups",
        related_query_name="devicegroup",
        blank=True,
        help_text="Outbound Integration."
    )
    devices = models.ManyToManyField(Device, blank=True)
    default_subject_type = models.ForeignKey(
        SubjectType,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        help_text="Subject type to be used unless overriden by the integration or data provider."
    )
    history = HistoricalRecords()

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return f"{self.name} - {self.owner.name}"


@receiver(post_save, sender=OutboundIntegrationConfiguration)
def integration_configuration_save_tasks(sender, instance, **kwargs):
    if type(instance.type) is OutboundIntegrationType:
        transaction.on_commit(
            lambda: celery.app.send_task(
                "cdip_admin.tasks.run_smart_integration_save_tasks",
                args=(str(instance.id),),
            )
        )

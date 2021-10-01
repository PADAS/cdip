import uuid
from django.db import models
from fernet_fields import EncryptedCharField
from core.models import TimestampedModel
from core.fields import APIConsumerField
from organizations.models import Organization, OrganizationGroup


# This is where the general information for a configuration will be stored
# This could be an inbound or outbound type
# Example Inbound Integrations: Savannah Tracking Collars, Garmin Inreach
class InboundIntegrationType(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=200, verbose_name='Type')
    slug = models.SlugField(max_length=200, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return f"{self.name}"


# This is where the general information for a configuration will be stored
# This could be an inbound or outbound type
# Example Outbound Integrations: EarthRanger, SMART, WpsWatch
class OutboundIntegrationType(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    description = models.TextField(blank=True)
    use_endpoint = models.BooleanField(default=False)
    use_login = models.BooleanField(default=False)
    use_password = models.BooleanField(default=False)
    use_token = models.BooleanField(default=False)

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return f"{self.name}"


class BridgeIntegrationType(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=200, verbose_name='Type')
    slug = models.SlugField(max_length=200, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return f"{self.name}"

# This is the information for a given configuration this will include a specific organizations account information
# Or organization specific information
class OutboundIntegrationConfiguration(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    type = models.ForeignKey(OutboundIntegrationType, on_delete=models.CASCADE)
    owner = models.ForeignKey(Organization, on_delete=models.CASCADE)
    name = models.CharField(max_length=200, blank=True)
    state = models.JSONField(blank=True, null=True)
    endpoint = models.URLField(blank=True)
    login = models.CharField(max_length=200, blank=True)
    password = EncryptedCharField(max_length=200, blank=True)
    token = EncryptedCharField(max_length=200, blank=True)
    additional = models.JSONField(default=dict, blank=True)
    enabled = models.BooleanField(default=True)


    class Meta:
        ordering = ('name',)

    def __str__(self):
        return f"{self.type.name} - {self.owner.name} - {self.name}"


# This is the information for a given configuration this will include a specific organizations account information
# Or organization specific information
class InboundIntegrationConfiguration(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    type = models.ForeignKey(InboundIntegrationType, on_delete=models.CASCADE)
    owner = models.ForeignKey(Organization, on_delete=models.CASCADE)
    name = models.CharField(max_length=200, blank=True)
    endpoint = models.URLField(blank=True)
    state = models.JSONField(blank=True, null=True)
    login = models.CharField(max_length=200, blank=True)
    password = EncryptedCharField(max_length=200, blank=True)
    token = EncryptedCharField(max_length=200, blank=True)
    provider = models.CharField(max_length=200, blank=True)
    enabled = models.BooleanField(default=True)

    default_devicegroup = models.ForeignKey('DeviceGroup', blank=True, null=True, on_delete=models.PROTECT,
                                            related_name='inbound_integration_configuration',
                                            related_query_name='inbound_integration_configurations',
                                            verbose_name='Default Device Group')

    consumer_id = models.CharField(max_length=200, blank=True)

    # api_consumer = APIConsumerField(verbose_name='API Key', null=True, blank=True)

    def __str__(self):
        return f"Type:{self.type.name} Owner:{self.owner.name} Name:{self.name}"

    def save(self, *args, **kwargs):
        if not self.provider:
            self.provider = self.type.slug
        super().save(*args, **kwargs)

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

    class Meta:
        ordering = ('name',)



# This is where the information is stored for a specific device
class Device(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    inbound_configuration = models.ForeignKey(InboundIntegrationConfiguration, on_delete=models.CASCADE)
    external_id = models.CharField(max_length=200)

    @property
    def owner(self):
        return self.inbound_configuration.owner

    def __str__(self):
        return f"{self.external_id} - {self.inbound_configuration.type.name}"

    class Meta:
        ordering = ('inbound_configuration', 'external_id')
        unique_together = ('inbound_configuration', 'external_id')


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
            models.Index(fields=['device', 'created_at']),
        ]
        ordering = ('device', '-created_at')

    def __str__(self):
        return f"{self.state}"


# This allows an organization to group a set of devices to send information to a series of outbound configs
# Must be tied to an OrgGroup
class DeviceGroup(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=200)
    owner = models.ForeignKey(Organization, on_delete=models.CASCADE)
    destinations = models.ManyToManyField(OutboundIntegrationConfiguration, related_name='devicegroups',
                                          related_query_name='devicegroup', blank=True)
    devices = models.ManyToManyField(Device, blank=True)

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return f"{self.name} - {self.owner.name}"



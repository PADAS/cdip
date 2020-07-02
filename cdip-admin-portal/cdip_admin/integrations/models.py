import uuid

from django.db import models
from core.models import TimestampedModel
from organizations.models import Organization, OrganizationGroup


# This is where the general information for a configuration will be stored
# This could be an inbound or outbound type
# Example Inbound Integrations: Savannah Tracking Collars, Garmin Inreach
class InboundIntegrationType(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    def __str__(self):
        return f"{self.name}"


# This is where the general information for a configuration will be stored
# This could be an inbound or outbound type
# Example Outbound Integrations: EarthRanger, SMART, WpsWatch
class OutboundIntegrationType(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    def __str__(self):
        return f"{self.name}"


# This is the information for a given configuration this will include a specific organizations account information
# Or organization specific information
class InboundIntegrationConfiguration(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    type = models.ForeignKey(InboundIntegrationType, on_delete=models.CASCADE)
    owner = models.ForeignKey(Organization, on_delete=models.CASCADE)
    endpoint = models.URLField(blank=True)
    slug = models.SlugField(blank=True)

    def __str__(self):
        return f"{self.type.name} - {self.owner.name}"


# This is the information for a given configuration this will include a specific organizations account information
# Or organization specific information
class OutboundIntegrationConfiguration(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    type = models.ForeignKey(OutboundIntegrationType, on_delete=models.CASCADE)
    owner = models.ForeignKey(Organization, on_delete=models.CASCADE)
    endpoint = models.URLField(blank=True)
    slug = models.SlugField(blank=True)

    def __str__(self):
        return f"{self.type.name} - {self.owner.name}"


# This is where the information is stored for a specific device
class Device(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    type = models.ForeignKey(InboundIntegrationType, on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    owner = models.ForeignKey(Organization, on_delete=models.CASCADE)
    location = models.SlugField(blank=True)

    def __str__(self):
        return f"{self.type.name} - {self.owner.name}"


# This allows an organization to group a set of devices to send information to a series of outbound configs
# Must be tied to an OrgGroup
class DeviceGroup(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=200)
    owner = models.ForeignKey(Organization, on_delete=models.CASCADE)
    devices = models.ManyToManyField(Device)
    # A Device can have many outbound configurations
    organization_group = models.ForeignKey(OrganizationGroup, on_delete=models.CASCADE)
    # startDate and endDate are used when the device group will only be in use for a certain period of time.
    start_date = models.DateField()
    end_date = models.DateField()
    # startTime and endTime are used to limit the share for a specific part of the day
    # Example: Would be for ranger tracking info at night to help APU response
    start_time = models.TimeField()
    end_time = models.TimeField()


# Stores the Device Configuration for a DeviceGroup
class DeviceGroupConfiguration(TimestampedModel):
    id = id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=200)
    device_group = models.OneToOneField(Device, on_delete=models.CASCADE)
    configuration = models.ManyToManyField(OutboundIntegrationConfiguration, related_name='configurations')

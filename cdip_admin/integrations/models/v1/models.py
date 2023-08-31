import uuid
import pydantic
import logging
from django.db import models, transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from fernet_fields import EncryptedCharField
from django_jsonform.models.fields import JSONField
from integrations.utils import does_movebank_permissions_config_changed
from integrations.tasks import recreate_and_send_movebank_permissions_csv_file
from cdip_admin import celery
from core.models import TimestampedModel
from organizations.models import Organization
from model_utils import FieldTracker
from simple_history.models import HistoricalRecords
from gundi_core import schemas


logger = logging.getLogger(__name__)


# This is where the general information for a configuration will be stored
# This could be an inbound or outbound type

class InboundIntegrationTypeManager(models.Manager):
    @classmethod
    def configuration_schema(cls, typeid=None):
        default_schema = {
            "type": "object",
            "keys": {}
        }
        if typeid:
            try:
                schema = InboundIntegrationType.objects.get(id=typeid).configuration_schema
                return schema or default_schema
            except InboundIntegrationType.DoesNotExist:
                pass
        # Return blank schema by default.
        return default_schema


# Example Inbound Integrations: Savannah Tracking Collars, Garmin Inreach
class InboundIntegrationType(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=200, verbose_name="Type")
    slug = models.SlugField(
        max_length=200,
        unique=True,
        help_text="Identifier using lowercase letters and no spaces.",
    )
    description = models.TextField(
        blank=True,
        help_text="Optional field - description of the Technology or Service.",
    )
    configuration_schema = models.JSONField(blank=True,
                                            default=dict, verbose_name='JSON Schema for configuration value')
    objects = InboundIntegrationTypeManager()
    history = HistoricalRecords()

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return f"{self.name}"

    EARTHRANGER = "earth_ranger"


# This is where the general information for a configuration will be stored
# This could be an inbound or outbound type

class OutboundIntegrationTypeManager(models.Manager):
    @classmethod
    def configuration_schema(cls, typeid=None):
        default_schema = {
            "type": "object",
            "keys": {}
        }
        if typeid:
            try:
                schema = OutboundIntegrationType.objects.get(id=typeid).configuration_schema
                return schema or default_schema
            except OutboundIntegrationType.DoesNotExist:
                pass
        # Return blank schema by default.
        return default_schema


# Example Outbound Integrations: EarthRanger, SMART, WpsWatch
class OutboundIntegrationType(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=200)
    slug = models.SlugField(
        max_length=200,
        unique=True,
        help_text="Identifier using lowercase letters and no spaces.",
    )
    description = models.TextField(
        blank=True,
        help_text="Optional - general description of the destination system.",
    )
    # configuration_schema is used for the state field of OutboundIntegrationConfiguration
    configuration_schema = models.JSONField(blank=True,
                                            default=dict, verbose_name='JSON Schema for configuration value')
    # dest_configuration_schema is used in Gundi 2.0
    # for the configuration field of OutboundIntegrationConfiguration (a.k.a. destination)
    dest_configuration_schema = models.JSONField(
        blank=True,
        default=dict,
        verbose_name='JSON Schema for destination configuration'
    )
    objects = OutboundIntegrationTypeManager()
    use_endpoint = models.BooleanField(default=False)
    use_login = models.BooleanField(default=False)
    use_password = models.BooleanField(default=False)
    use_token = models.BooleanField(default=False)
    history = HistoricalRecords()

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return f"{self.name}"

    SMARTCONNECT = "smart_connect"


class BridgeIntegrationTypeManager(models.Manager):
    @classmethod
    def configuration_schema(cls, typeid=None):
        default_schema = {
            "type": "object",
            "keys": {}
        }
        if typeid:
            try:
                schema = BridgeIntegrationType.objects.get(id=typeid).configuration_schema
                return schema or default_schema
            except BridgeIntegrationType.DoesNotExist:
                pass
        # Return blank schema by default.
        return default_schema


class BridgeIntegrationType(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=200, verbose_name="Type")
    slug = models.SlugField(
        max_length=200,
        unique=True,
        help_text="Identifier using lowercase letters and no spaces.")
    description = models.TextField(
        blank=True,
        help_text="Optional - general description of the destination system.")
    configuration_schema = models.JSONField(blank=True,
                                            default=dict, verbose_name='JSON Schema for configuration value')
    objects = BridgeIntegrationTypeManager()
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
        help_text="Integration component that can process the data.",
    )
    owner = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        help_text="Organization that owns the data.",
    )
    name = models.CharField(max_length=200, blank=True)
    # state = models.JSONField(
    #     blank=True, null=True, help_text="Additional configuration(s)."
    # )
    # ToDo: Rename to state_schema and separate state from configuration?
    state = JSONField(schema=OutboundIntegrationType.objects.configuration_schema, blank=True, default=dict)
    configuration = models.JSONField(default=dict, blank=True)  # New configuration field for Gundi 2.0
    endpoint = models.URLField(blank=True)
    ##########################################################
    # We keep these fields for backward compatibility.
    # Now they will be moved into the configuration json field
    login = models.CharField(max_length=200, blank=True)
    password = EncryptedCharField(max_length=200, blank=True)
    token = EncryptedCharField(max_length=200, blank=True)
    ##########################################################
    additional = models.JSONField(default=dict, blank=True)
    enabled = models.BooleanField(default=True)
    history = HistoricalRecords()

    tracker = FieldTracker()

    class Meta:
        ordering = ("owner", "name")

    def __str__(self):
        return f"{self.owner.name} - {self.name} - {self.type.name}"

    def _pre_save(self, *args, **kwargs):
        pass

    def _post_save(self, *args, **kwargs):
        if does_movebank_permissions_config_changed(self, "v1"):
            # Movebank permissions file needs to be recreated
            # Check if AUTH info is available
            movebank_auth_data = {}
            try:
                movebank_auth_data = schemas.v2.MBAuthActionConfig.parse_obj(
                    {
                        "username": self.login or None,
                        "password": self.password or None
                    }
                ).dict()
            except pydantic.ValidationError:  # Bad config, log a warning
                logger.warning(
                    "Invalid login/password or not present.",
                    extra={
                        "outbound_integration_config_id": self.id,
                        'attention_needed': True
                    }
                )
            transaction.on_commit(
                lambda: recreate_and_send_movebank_permissions_csv_file.delay(**movebank_auth_data)
            )

    def save(self, *args, **kwargs):
        with self.tracker:
            self._pre_save(self, *args, **kwargs)
            super().save(*args, **kwargs)
            self._post_save(self, *args, **kwargs)


# This is the information for a given configuration this will include a specific organizations account information
# Or organization specific information
class InboundIntegrationConfiguration(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    type = models.ForeignKey(
        InboundIntegrationType,
        on_delete=models.CASCADE,
        help_text="Integration component that can process the data.",
        verbose_name="Type",
    )
    owner = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        help_text="Organization that owns the data.",
        verbose_name="Owner",
    )
    name = models.CharField(max_length=200, blank=True)
    endpoint = models.URLField(blank=True)
    # state = models.JSONField(
    #     blank=True,
    #     null=True,
    #     help_text="Additional integration configuration(s).",
    #     verbose_name="State",
    # )
    state = JSONField(schema=InboundIntegrationType.objects.configuration_schema, blank=True, default=dict)
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

    history = HistoricalRecords(excluded_fields=["state"])

    default_devicegroup = models.ForeignKey(
        "DeviceGroup",
        blank=True,
        null=True,
        on_delete=models.PROTECT,
        related_name="inbound_integration_configuration",
        related_query_name="inbound_integration_configurations",
        verbose_name="Default Device Group",
        help_text="Device group that will be used unless a different group is specified by the data provider or integration.",
    )

    consumer_id = models.CharField(max_length=200, blank=True)

    # api_consumer = APIConsumerField(verbose_name='API Key', null=True, blank=True)

    class Meta:
        ordering = ("owner", "name")

    def __str__(self):
        return f"Owner: {self.owner.name} Name: {self.name} Type: {self.type.name}"

    @property
    def routing_rules(self):
        routing_rules = DeviceGroup.objects.filter(
            devices__inbound_configuration__id=self.id
        ).distinct()
        return routing_rules

    @property
    def destinations(self):
        destinations = OutboundIntegrationConfiguration.objects.filter(
            devicegroup__in=models.Subquery(self.routing_rules.values('id'))
        ).distinct()
        return destinations

    def _pre_save(self, *args, **kwargs):
        # Slug generation
        # ToDo: We could use a better slug generator like django.utils.text.slugify
        # https://docs.djangoproject.com/en/3.2/ref/utils/#django.utils.text.slugify
        if not self.provider:
            self.provider = self.type.slug.lower()
        else:
            self.provider = self.provider.lower()
        # Ensure that a default device group is set for new integrations
        if not self.default_devicegroup:
            name = self.name + " - Default Group"
            device_group, _ = DeviceGroup.objects.get_or_create(
                owner_id=self.owner.id, name=name
            )
            self.default_devicegroup = device_group

    def _post_save(self, *args, **kwargs):
        pass

    def save(self, *args, **kwargs):
        self._pre_save(self, *args, **kwargs)
        super().save(*args, **kwargs)
        self._post_save(self, *args, **kwargs)


# This is the information for a given configuration this will include a specific organizations account information
# Or organization specific information
def get_bridge_configuration_schema(instance=None):
    type_id = instance.type.id if instance else None
    return BridgeIntegrationType.objects.configuration_schema(typeid=type_id)


class BridgeIntegration(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    type = models.ForeignKey(
        BridgeIntegrationType,
        on_delete=models.CASCADE,
        help_text="Integration component that can process the data.")
    owner = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        help_text="Organization that owns the data.",)
    name = models.CharField(max_length=200, blank=True)
    state = models.JSONField(
        blank=True,
        null=True,
        help_text="Additional integration configuration(s).",)
    additional = JSONField(schema=BridgeIntegrationType.objects.configuration_schema, blank=True, default=dict)
    # additional = models.JSONField(default=dict, blank=True)
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
        max_length=200, help_text="Id sent by the data provider"
    )
    subject_type = models.ForeignKey(
        SubjectType,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        help_text="Default subject type. Can be overriden by the integration or data provider",
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

    @property
    def default_group(self):
        return self.inbound_configuration.default_devicegroup

    def __str__(self):
        return f"{self.external_id} - {self.inbound_configuration.type.name}"

    def _pre_save(self, *args, **kwargs):
        pass

    def _post_save(self, *args, **kwargs):
        # Ensure the device is added to the default group after creation
        self.default_group.devices.add(self)

    def save(self, *args, **kwargs):
        self._pre_save(self, *args, **kwargs)
        super().save(*args, **kwargs)
        self._post_save(self, *args, **kwargs)

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
        help_text="Organization that owns the data.",
    )
    destinations = models.ManyToManyField(
        OutboundIntegrationConfiguration,
        related_name="devicegroups",
        related_query_name="devicegroup",
        blank=True,
        help_text="Outbound Integration(s). To choose multiple options, hold CMD/Ctrl key and select.",
    )
    devices = models.ManyToManyField(Device, blank=True)
    default_subject_type = models.ForeignKey(
        SubjectType,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        help_text="Subject type to be used unless overriden by the integration or data provider.",
    )
    history = HistoricalRecords()

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return f"{self.name} - {self.owner.name}"


@receiver(post_save, sender=OutboundIntegrationConfiguration)
def integration_configuration_save_tasks(sender, instance, **kwargs):

    transaction.on_commit(
        lambda: celery.app.send_task(
            "sync_integrations.tasks.handle_outboundintegration_save",
            args=(str(instance.id),),
        )
    )

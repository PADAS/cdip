import django_tables2 as tables

from .models import (
    DeviceState,
    DeviceGroup,
    Device,
    InboundIntegrationConfiguration,
    OutboundIntegrationConfiguration,
    BridgeIntegration,
)


class DeviceStateTable(tables.Table):
    created = tables.Column(accessor="created_at", verbose_name="Created")
    organization = tables.Column(
        accessor="device__inbound_configuration__owner", verbose_name="Organization", linkify=True)

    class Meta:
        model = DeviceState
        template_name = "django_tables2/bootstrap4.html"
        fields = (
            "device__external_id",
            "device__inbound_configuration__type__name",
            "state",
        )
        row_attrs = {"device-id": lambda record: record.device.id}
        attrs = {"class": "table table-hover", "id": "device-state-table"}
        sequence = (
            "device__external_id",
            "organization",
            "device__inbound_configuration__type__name",
            "state",
            "created",
        )
        order_by = "-created"


class DeviceGroupTable(tables.Table):
    device_count = tables.Column(
        accessor="device_count", verbose_name="Device Count")
    created = tables.Column(accessor="created_at", verbose_name="Created")
    organization = tables.Column(
        accessor="owner", verbose_name="Organization", linkify=True)

    class Meta:
        model = DeviceGroup
        template_name = "django_tables2/bootstrap4.html"
        fields = ("name",)
        row_attrs = {"device-group-id": lambda record: record.id}
        attrs = {"class": "table table-hover", "id": "device-group-table"}
        sequence = ("name", "organization", "device_count", "created")
        order_by = ["organization", "-created"]


class DeviceTable(tables.Table):
    created = tables.Column(accessor="created_at", verbose_name="Created")
    owner = tables.Column(
        accessor="inbound_configuration__owner", verbose_name="Organization", linkify=True)
    integration_type = tables.Column(
        accessor="inbound_configuration__type__name", verbose_name="Integration Type"
    )

    class Meta:
        model = Device
        template_name = "django_tables2/bootstrap4.html"
        fields = ("external_id", "owner", "integration_type")
        row_attrs = {"device-id": lambda record: record.id}
        attrs = {"class": "table table-hover", "id": "device-table"}
        sequence = ("external_id", "owner", "integration_type", "created")
        order_by = "-created"


class InboundIntegrationConfigurationTable(tables.Table):

    organization = tables.Column(
        accessor="owner", verbose_name="Organization", linkify=True)

    class Meta:
        model = InboundIntegrationConfiguration
        template_name = "django_tables2/bootstrap4.html"
        fields = ("name", "type__name", "organization", "endpoint", "enabled")
        row_attrs = {"inbound-config-id": lambda record: record.id}
        attrs = {"class": "table table-hover", "id": "inbound-config-table"}
        order_by = "type__name"


class OutboundIntegrationConfigurationTable(tables.Table):
    type = tables.Column(accessor="type__name", verbose_name="Type")

    organization = tables.Column(
        accessor="owner", verbose_name="Organization", linkify=True)

    class Meta:
        model = OutboundIntegrationConfiguration
        template_name = "django_tables2/bootstrap4.html"
        fields = ("name", "type", "organization", "endpoint", "enabled")
        row_attrs = {"outbound-config-id": lambda record: record.id}
        attrs = {"class": "table table-hover", "id": "outbound-config-table"}
        order_by = "type__name"


class BridgeIntegrationTable(tables.Table):
    type = tables.Column(accessor="type__name", verbose_name="Type")
    organization = tables.Column(
        accessor="owner", verbose_name="Organization", linkify=True)

    class Meta:
        model = BridgeIntegration
        template_name = "django_tables2/bootstrap4.html"
        fields = ("name", "type", "organization", "enabled")
        row_attrs = {"bridge-config-id": lambda record: record.id}
        attrs = {"class": "table table-hover", "id": "bridge-config-table"}
        order_by = "type__name"

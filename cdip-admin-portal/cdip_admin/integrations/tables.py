import django_tables2 as tables

from .models import DeviceState, DeviceGroup, Device, InboundIntegrationConfiguration, OutboundIntegrationConfiguration


class DeviceStateTable(tables.Table):
    created = tables.Column(accessor="created_at", verbose_name="Created")

    class Meta:
        model = DeviceState
        template_name = "django_tables2/bootstrap4.html"
        fields = ('device__external_id', 'device__inbound_configuration__owner__name',
                  'device__inbound_configuration__type__name', 'state')
        row_attrs = {"device-id": lambda record: record.device.id}
        attrs = {"class": "table table-hover", "id": "device-state-table"}
        sequence = ('device__external_id', 'device__inbound_configuration__owner__name',
                  'device__inbound_configuration__type__name', 'state', 'created')
        order_by = '-created'


class DeviceGroupTable(tables.Table):
    count = tables.Column(accessor="devices", verbose_name="Device Count")
    created = tables.Column(accessor="created_at", verbose_name="Created")

    def render_count(self, value):
        return value.all().count()

    class Meta:
        model = DeviceGroup
        template_name = "django_tables2/bootstrap4.html"
        fields = ('name', 'owner__name')
        row_attrs = {"device-group-id": lambda record: record.id}
        attrs = {"class": "table table-hover", "id": "device-group-table"}
        sequence = ('name', 'owner__name', 'count', 'created')
        order_by = '-created'


class DeviceTable(tables.Table):
    created = tables.Column(accessor="created_at", verbose_name="Created")

    class Meta:
        model = Device
        template_name = "django_tables2/bootstrap4.html"
        fields = ('external_id', 'inbound_configuration__owner__name',
                  'inbound_configuration__type__name')
        row_attrs = {"device-id": lambda record: record.id}
        attrs = {"class": "table table-hover", "id": "device-table"}
        sequence = ('external_id', 'inbound_configuration__owner__name',
                  'inbound_configuration__type__name', 'created')
        order_by = '-created'


class InboundIntegrationConfigurationTable(tables.Table):

    class Meta:
        model = InboundIntegrationConfiguration
        template_name = "django_tables2/bootstrap4.html"
        fields = ('name', 'type__name', 'owner__name', 'endpoint', 'state', 'enabled')
        row_attrs = {"inbound-config-id": lambda record: record.id}
        attrs = {"class": "table table-hover", "id": "inbound-config-table"}
        order_by = 'type__name'


class OutboundIntegrationConfigurationTable(tables.Table):
    type = tables.Column(accessor="type__name", verbose_name="Type")

    class Meta:
        model = OutboundIntegrationConfiguration
        template_name = "django_tables2/bootstrap4.html"
        fields = ('name', 'type', 'owner__name', 'endpoint', 'state', 'enabled')
        row_attrs = {"outbound-config-id": lambda record: record.id}
        attrs = {"class": "table table-hover", "id": "outbound-config-table"}
        order_by = 'type__name'


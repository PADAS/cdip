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
        accessor="device__inbound_configuration__owner",
        verbose_name="Organization",
        linkify=True,
    )

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
    device_count = tables.Column(accessor="device_count", verbose_name="Device Count")
    created = tables.Column(accessor="created_at", verbose_name="Created")
    organization = tables.Column(
        accessor="owner", verbose_name="Organization", linkify=True
    )

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
        accessor="inbound_configuration__owner",
        verbose_name="Organization",
        linkify=True,
    )
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

    enabled = tables.TemplateColumn(
        template_code='''<span hx-post="{% url 'inbound_toggle_enabled' configuration_id=record.id %}" hx-target="this" hx-swap="outerHTML" style="cursor: pointer;">{% if record.enabled %}<span class="text-success" title="Enabled">&#10003;</span>{% else %}<span class="text-muted" title="Disabled">&#10005;</span>{% endif %}</span>''',
        verbose_name="Enabled",
        orderable=False,
    )
    name = tables.TemplateColumn(
        template_code='''{{ record.name }}<br><small class="text-muted">{{ record.type }}</small>''',
        verbose_name="Name / Type",
    )
    organization = tables.Column(
        accessor="owner", verbose_name="Organization", linkify=True
    )
    status = tables.TemplateColumn(
        template_code='''
        {% if not record.enabled %}
          <span class="badge badge-secondary">OK</span>
        {% elif record.state.error %}
          <span class="badge badge-danger" title="{{ record.state.error }}">Error</span>
        {% else %}
          <span class="badge badge-success">OK</span>
        {% endif %}
        ''',
        verbose_name="Status",
        orderable=False,
    )
    actions = tables.TemplateColumn(
        template_code='''
        <button type="button"
           class="btn btn-sm btn-outline-primary"
           onclick="htmx.ajax('GET', '{% url 'inbound_integration_configuration_update' configuration_id=record.id %}', {target: '#slide-panel-body', swap: 'innerHTML'}); document.body.dispatchEvent(new Event('openPanel'));">Edit</button>
        ''',
        verbose_name="",
        orderable=False,
    )

    class Meta:
        model = InboundIntegrationConfiguration
        template_name = "django_tables2/bootstrap4.html"
        fields = ("actions", "enabled", "status", "name", "organization", "endpoint")
        sequence = ("actions", "enabled", "status", "name", "organization", "endpoint")
        row_attrs = {"inbound-config-id": lambda record: record.id}
        attrs = {"class": "table table-hover", "id": "inbound-config-table"}
        order_by = "type__name"


class OutboundIntegrationConfigurationTable(tables.Table):

    enabled = tables.TemplateColumn(
        template_code='''<span hx-post="{% url 'outbound_toggle_enabled' configuration_id=record.id %}" hx-target="this" hx-swap="outerHTML" style="cursor: pointer;">{% if record.enabled %}<span class="text-success" title="Enabled">&#10003;</span>{% else %}<span class="text-muted" title="Disabled">&#10005;</span>{% endif %}</span>''',
        verbose_name="Enabled",
        orderable=False,
    )
    name = tables.TemplateColumn(
        template_code='''{{ record.name }}<br><small class="text-muted">{{ record.type }}</small>''',
        verbose_name="Name / Type",
    )
    organization = tables.Column(
        accessor="owner", verbose_name="Organization", linkify=True
    )
    status = tables.TemplateColumn(
        template_code='''
        {% if not record.enabled %}
          <span class="badge badge-secondary">OK</span>
        {% elif record.state.error %}
          <span class="badge badge-danger" title="{{ record.state.error }}">Error</span>
        {% else %}
          <span class="badge badge-success">OK</span>
        {% endif %}
        ''',
        verbose_name="Status",
        orderable=False,
    )
    actions = tables.TemplateColumn(
        template_code='''
        <button type="button"
           class="btn btn-sm btn-outline-primary"
           onclick="htmx.ajax('GET', '{% url 'outbound_integration_configuration_update' configuration_id=record.id %}', {target: '#slide-panel-body', swap: 'innerHTML'}); document.body.dispatchEvent(new Event('openPanel'));">Edit</button>
        ''',
        verbose_name="",
        orderable=False,
    )

    class Meta:
        model = OutboundIntegrationConfiguration
        template_name = "django_tables2/bootstrap4.html"
        fields = ("actions", "enabled", "status", "name", "organization", "endpoint")
        sequence = ("actions", "enabled", "status", "name", "organization", "endpoint")
        row_attrs = {"outbound-config-id": lambda record: record.id}
        attrs = {"class": "table table-hover", "id": "outbound-config-table"}
        order_by = "type__name"


class BridgeIntegrationTable(tables.Table):

    enabled = tables.TemplateColumn(
        template_code='''<span hx-post="{% url 'bridge_toggle_enabled' id=record.id %}" hx-target="this" hx-swap="outerHTML" style="cursor: pointer;">{% if record.enabled %}<span class="text-success" title="Enabled">&#10003;</span>{% else %}<span class="text-muted" title="Disabled">&#10005;</span>{% endif %}</span>''',
        verbose_name="Enabled",
        orderable=False,
    )
    name = tables.TemplateColumn(
        template_code='''{{ record.name }}<br><small class="text-muted">{{ record.type }}</small>''',
        verbose_name="Name / Type",
    )
    organization = tables.Column(
        accessor="owner", verbose_name="Organization", linkify=True
    )
    status = tables.TemplateColumn(
        template_code='''
        {% if not record.enabled %}
          <span class="badge badge-secondary">OK</span>
        {% elif record.state.error %}
          <span class="badge badge-danger" title="{{ record.state.error }}">Error</span>
        {% else %}
          <span class="badge badge-success">OK</span>
        {% endif %}
        ''',
        verbose_name="Status",
        orderable=False,
    )
    actions = tables.TemplateColumn(
        template_code='''
        <button type="button"
           class="btn btn-sm btn-outline-primary"
           onclick="htmx.ajax('GET', '{% url 'bridge_integration_update' id=record.id %}', {target: '#slide-panel-body', swap: 'innerHTML'}); document.body.dispatchEvent(new Event('openPanel'));">Edit</button>
        ''',
        verbose_name="",
        orderable=False,
    )

    class Meta:
        model = BridgeIntegration
        template_name = "django_tables2/bootstrap4.html"
        fields = ("actions", "enabled", "status", "name", "organization")
        sequence = ("actions", "enabled", "status", "name", "organization")
        attrs = {"class": "table table-hover", "id": "bridge-config-table"}
        order_by = "type__name"

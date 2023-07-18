from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

import deployments.models
from .models import (
    OutboundIntegrationType,
    InboundIntegrationType,
    OutboundIntegrationConfiguration,
    InboundIntegrationConfiguration,
    Device,
    DeviceGroup,
    DeviceState,
    BridgeIntegrationType,
    BridgeIntegration,
    SubjectType,
    IntegrationType,
    IntegrationAction,
    Integration,
    IntegrationConfiguration,
    Route,
    RouteConfiguration,
    SourceFilter, Source, SourceState, SourceConfiguration,
    GundiTrace,
)

from .forms import (
    InboundIntegrationConfigurationForm,
    OutboundIntegrationConfigurationForm,
    BridgeIntegrationForm
)

# Register your models here.
admin.site.register(InboundIntegrationType, SimpleHistoryAdmin)
admin.site.register(OutboundIntegrationType, SimpleHistoryAdmin)


@admin.register(DeviceState)
class DeviceStateAdmin(admin.ModelAdmin):
    list_display = (
        "device",
        "_external_id",
        "_owner",
        "created_at",
    )
    list_filter = (
        "device__inbound_configuration__name",
        "device__inbound_configuration__owner",
    )
    search_fields = (
        "device__external_id",
        "device__inbound_configuration__name",
    )

    date_hierarchy = "created_at"

    def _external_id(self, obj):
        return obj.device.external_id

    _external_id.short_description = "Device ID"

    def _owner(self, obj):
        return obj.device.inbound_configuration.owner

    _owner.short_description = "Owner"


@admin.register(Device)
class DeviceAdmin(SimpleHistoryAdmin):
    list_display = (
        "external_id",
        "_owner",
        "created_at",
    )
    list_filter = (
        "inbound_configuration__name",
        "inbound_configuration__owner",
    )

    search_fields = (
        "external_id",
        "inbound_configuration__name",
        "inbound_configuration__owner__name",
    )

    date_hierarchy = "created_at"

    def _owner(self, obj):
        return obj.inbound_configuration.owner

    _owner.short_description = "Owner"


@admin.register(SubjectType)
class SubjectTypeAdmin(SimpleHistoryAdmin):
    list_display = ("value", "display_name", "created_at")


@admin.register(DeviceGroup)
class DeviceGroupAdmin(SimpleHistoryAdmin):
    list_display = ("name", "owner", "created_at")
    list_filter = ("owner",)

    search_fields = ("id", "name", "owner__name", "devices__external_id")


@admin.register(InboundIntegrationConfiguration)
class InboundIntegrationConfigurationAdmin(SimpleHistoryAdmin):
    readonly_fields = [
        "id",
    ]
    form = InboundIntegrationConfigurationForm

    list_display = (
        "name",
        "type",
        "owner",
        "enabled",
    )

    list_filter = (
        "type",
        "owner",
        "enabled",
    )

    list_editable = ("enabled",)

    search_fields = (
        "id",
        "name",
        "type__name",
        "owner__name",
    )


@admin.register(OutboundIntegrationConfiguration)
class OutboundIntegrationConfigurationAdmin(SimpleHistoryAdmin):
    readonly_fields = [
        "id",
    ]
    form = OutboundIntegrationConfigurationForm

    list_filter = (
        "type",
        "owner",
        "enabled",
    )

    search_fields = (
        "id",
        "name",
        "type__name",
        "owner__name",
    )

    def _name(self, obj):
        return obj.name or "-no-name-"

    list_display = ("type", "_name", "owner", "created_at", "updated_at")
    list_display_links = (
        "_name",
        "owner",
    )


@admin.register(BridgeIntegrationType)
class BridgeIntegrationTypeAdmin(SimpleHistoryAdmin):

    list_display = ("name",)


@admin.register(BridgeIntegration)
class BridgeIntegrationAdmin(SimpleHistoryAdmin):
    form = BridgeIntegrationForm
    list_display = ("name", "owner", "type")
    list_filter = (
        "type",
        "owner",
        "enabled",
    )

    search_fields = (
        "id",
        "name",
        "type__name",
        "owner__name",
    )


@admin.register(IntegrationType)
class IntegrationTypeAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "value",
        "description",
    )


@admin.register(IntegrationAction)
class IntegrationActionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "integration_type",
        "type",
        "name",
        "value",
        "description",
    )
    list_filter = (
        "integration_type",
        "type",
    )


class DispatcherDeploymentInline(admin.StackedInline):
    model = deployments.models.DispatcherDeployment
    readonly_fields = (
        "status",
    )


@admin.register(Integration)
class IntegrationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "type",
        "owner",
        "name",
        "enabled",
        "api_key",  # ToDo: Add an endpoint to manage API Keys to manage them through the Portal UI?
    )
    list_filter = (
        "owner",
        "type",
    )
    inlines = [
        DispatcherDeploymentInline,
    ]


@admin.register(IntegrationConfiguration)
class IntegrationConfigurationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "integration",
        "action",
    )
    list_filter = (
        "integration__owner",
        "integration__type",
        "action__type",
    )


@admin.register(Route)
class RouteAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
    )
    list_filter = (
        "owner",
    )


@admin.register(RouteConfiguration)
class RouteAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
    )


@admin.register(SourceFilter)
class SourceFilterAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "order_number",
        "type",
        "name",
        "description"
    )
    list_filter = (
        "type",
        "routing_rule",
    )


@admin.register(Source)
class SourceAdmin(SimpleHistoryAdmin):
    list_display = (
        "external_id",
        "integration",
        "created_at",
    )
    list_filter = (
        "integration__name",
        "integration__owner",
        "integration__type",
    )

    search_fields = (
        "external_id",
        "integration__name",
        "integration__owner__name",
        "integration__type__name",
    )

    date_hierarchy = "created_at"


@admin.register(SourceState)
class SourceStateAdmin(SimpleHistoryAdmin):
    list_display = (
        "source",
        "updated_at",
        "data",
    )


@admin.register(SourceConfiguration)
class SourceConfigurationAdmin(SimpleHistoryAdmin):
    list_display = (
        "name",
        "updated_at",
        "data",
    )


@admin.register(GundiTrace)
class GundiTraceAdmin(SimpleHistoryAdmin):
    list_display = (
        "object_id",
        "related_to",
        "object_type",
        "data_provider",
        "destination",
        "external_id",
        "delivered_at",
        "created_by",
    )

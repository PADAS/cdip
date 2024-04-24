from django.contrib import admin
from django.forms import ModelForm
from simple_history.admin import SimpleHistoryAdmin
from django.contrib import messages
from core.admin import CustomDateFilter
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


class DispatcherDeploymentInline(admin.StackedInline):
    model = deployments.models.DispatcherDeployment
    fields = (
        "name",
        "configuration",
        "status",
        "status_details"
    )
    readonly_fields = (
        "status", "status_details",
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

    inlines = [
        DispatcherDeploymentInline,
    ]

    def delete_model(self, request, obj):
        try:  # Is there a deployment?
            deployment = obj.dispatcher_by_outbound
        except OutboundIntegrationConfiguration.dispatcher_by_outbound.RelatedObjectDoesNotExist:
            pass  # No deployment to delete
        else:  # Delete deployment
            if deployment.status not in [  # Check if it's in a safe state to delete
                deployments.models.DispatcherDeployment.Status.COMPLETE,
                deployments.models.DispatcherDeployment.Status.ERROR
            ]:
                msg = f"Warning: related dispatcher cannot be deleted in the current status. You can delete it later from the deployments page."
                messages.add_message(request, messages.WARNING, message=msg)
            elif OutboundIntegrationConfiguration.objects.filter(
                    additional__topic=deployment.topic_name).count() > 1:  # Check if the topic is being used by other integrations
                msg = f"Warning: related dispatcher won't be deleted as it's being used by other integrations."
                messages.add_message(request, messages.WARNING, message=msg)
            else:  # It's safe to delete it
                deployment.delete()
        # Then delete the integration
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        # Overwritten to call deployment.delete() in bulk deletion
        for obj in queryset:
            self.delete_model(request, obj)


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
        "service_url"
    )


@admin.register(IntegrationAction)
class IntegrationActionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "integration_type",
        "type",
        "name",
        "value",
        "is_periodic_action",
        "description",
    )
    list_filter = (
        "integration_type",
        "type",
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

    def delete_model(self, request, obj):
        try:  # Is there a deployment?
            deployment = obj.dispatcher_by_integration
        except Integration.dispatcher_by_integration.RelatedObjectDoesNotExist:
            pass  # No deployment to delete
        else:   # Delete deployment
            if deployment.status not in [  # Check if it's in a safe state to delete
                deployments.models.DispatcherDeployment.Status.COMPLETE,
                deployments.models.DispatcherDeployment.Status.ERROR
            ]:
                msg = f"Warning: related dispatcher cannot be deleted in the current status. You can delete it later from the deployments page."
                messages.add_message(request, messages.WARNING, message=msg)
            elif Integration.objects.filter(additional__topic=deployment.topic_name).count() > 1:  # Check if the topic is being used by other integrations
                msg = f"Warning: related dispatcher won't be deleted as it's being used by other integrations."
                messages.add_message(request, messages.WARNING, message=msg)
            else:  # It's safe to delete it
                deployment.delete()
        # Delete the integration
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        # Overwritten to call deployment.delete() in bulk deletion
        for obj in queryset:
            self.delete_model(request, obj)


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


class RouteProviderInline(admin.TabularInline):
    model = Route.data_providers.through


class RouteDestinationInline(admin.TabularInline):
    model = Route.destinations.through


@admin.register(Route)
class RouteAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
    )
    list_filter = (
        "owner",
    )
    inlines = (
        RouteProviderInline,
        RouteDestinationInline,
    )


@admin.register(RouteConfiguration)
class RouteConfigAdmin(admin.ModelAdmin):
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
        "is_duplicate",
        "has_error",
        "error",
        "created_at",
        "updated_at",
        "created_by",
    )
    search_fields = (
        "object_id",
        "related_to",
        "external_id",
        "data_provider__name",
        "data_provider__owner__name",
        "data_provider__type__name",
        "destination__name",
        "destination__owner__name",
        "destination__type__name",
    )
    date_hierarchy = 'created_at'
    list_filter = (
        ("delivered_at", CustomDateFilter),
        "has_error",
        "is_duplicate",
        "object_type",
        "data_provider__type",
        "destination__type",
        "data_provider",
        "destination",
    )

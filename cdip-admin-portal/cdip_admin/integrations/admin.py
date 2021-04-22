from django.contrib import admin

from .models import OutboundIntegrationType, InboundIntegrationType, OutboundIntegrationConfiguration, \
    InboundIntegrationConfiguration, Device, DeviceGroup, DeviceState

from .forms import InboundIntegrationConfigurationForm, OutboundIntegrationConfigurationForm

# Register your models here.
admin.site.register(InboundIntegrationType)
admin.site.register(OutboundIntegrationType)
admin.site.register(Device)
@admin.register(DeviceState)
class DeviceStateAdmin(admin.ModelAdmin):
    list_display = ('device', '_external_id', '_owner', 'created_at',)
    list_filter = ('device__inbound_configuration__name' , 'device__inbound_configuration__owner',)
    search_fields = ('device__external_id', 'device__inbound_configuration__name', )

    date_hierarchy = 'created_at'
    
    def _external_id(self, obj):
        return obj.device.external_id
    _external_id.short_description = 'Device ID'

    def _owner(self, obj):
        return obj.device.inbound_configuration.owner

    _owner.short_description = 'Owner'


@admin.register(DeviceGroup)
class DeviceGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner',)
    list_filter = ('owner',)


@admin.register(InboundIntegrationConfiguration)
class InboundIntegrationConfigurationAdmin(admin.ModelAdmin):
    readonly_fields = ['id', ]
    form = InboundIntegrationConfigurationForm

    list_display = ('name', 'type', 'owner','enabled',)

    list_filter = ('type', 'owner', 'enabled',)

    list_editable = ('enabled',)


@admin.register(OutboundIntegrationConfiguration)
class OutboundIntegrationConfigurationAdmin(admin.ModelAdmin):
    readonly_fields = ['id', ]
    form = OutboundIntegrationConfigurationForm

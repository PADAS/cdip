from django.contrib import admin

from .models import OutboundIntegrationType, InboundIntegrationType, OutboundIntegrationConfiguration, \
    InboundIntegrationConfiguration, Device, DeviceGroup, DeviceState

from .views import InboundIntegrationConfigurationForm, OutboundIntegrationConfigurationForm

# Register your models here.
admin.site.register(InboundIntegrationType)
admin.site.register(OutboundIntegrationType)
admin.site.register(Device)
admin.site.register(DeviceGroup)
admin.site.register(DeviceState)


@admin.register(InboundIntegrationConfiguration)
class InboundIntegrationConfigurationAdmin(admin.ModelAdmin):
    readonly_fields = ['id', ]
    form = InboundIntegrationConfigurationForm


@admin.register(OutboundIntegrationConfiguration)
class OutboundIntegrationConfigurationAdmin(admin.ModelAdmin):
    readonly_fields = ['id', ]
    form = OutboundIntegrationConfigurationForm

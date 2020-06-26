from django.contrib import admin

from .models import OutboundIntegrationType, InboundIntegrationType, OutboundIntegrationConfiguration, InboundIntegrationConfiguration, Device, DeviceGroup

# Register your models here.
admin.site.register(InboundIntegrationType)
admin.site.register(InboundIntegrationConfiguration)
admin.site.register(OutboundIntegrationType)
admin.site.register(OutboundIntegrationConfiguration)
admin.site.register(Device)
admin.site.register(DeviceGroup)

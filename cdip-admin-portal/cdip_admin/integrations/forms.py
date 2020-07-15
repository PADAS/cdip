from django import forms

from .models import Device, DeviceGroup, OutboundIntegrationConfiguration, InboundIntegrationConfiguration


class DeviceGroupForm(forms.ModelForm):
    class Meta:
        model = DeviceGroup
        fields = ('name', 'type', 'organization_group', 'devices', 'configuration',
                  'start_date', 'end_date', 'start_time', 'end_time')


class InboundIntegrationConfigurationForm(forms.ModelForm):
    class Meta:
        model = InboundIntegrationConfiguration
        fields = ('type', 'owner', 'endpoint', 'login', 'password',
                  'token', 'useDefaultConfiguration', 'defaultConfiguration', 'useAdvancedConfiguration')


class OutboundIntegrationConfigurationForm(forms.ModelForm):
    class Meta:
        model = OutboundIntegrationConfiguration
        fields = ('type', 'owner', 'endpoint', 'login', 'password',
                  'token')

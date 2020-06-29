from django import forms

from .models import Device, DeviceGroup, IntegrationConfiguration, IntegrationType


class DeviceGroupForm(forms.ModelForm):
    class Meta:
        model = DeviceGroup
        fields = ('name', 'type', 'organization_group', 'devices', 'configuration',
                  'start_date', 'end_date', 'start_time', 'end_time')

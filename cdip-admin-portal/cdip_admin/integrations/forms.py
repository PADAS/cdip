from django import forms

from .models import OutboundIntegrationConfiguration, InboundIntegrationConfiguration


# class DeviceGroupForm(forms.ModelForm):
#     class Meta:
#         model = DeviceGroup
#         fields = ('name', 'type', 'organization_group', 'devices', 'configuration',
#                   'start_date', 'end_date', 'start_time', 'end_time')


class InboundIntegrationConfigurationForm(forms.ModelForm):

    class Meta:
        model = InboundIntegrationConfiguration
        exclude = ['id']
        widgets = {
            'password': forms.PasswordInput(),
        }


class OutboundIntegrationConfigurationForm(forms.ModelForm):

    class Meta:
        model = OutboundIntegrationConfiguration
        exclude = ['id']
        widgets = {
            'password': forms.PasswordInput(),
        }

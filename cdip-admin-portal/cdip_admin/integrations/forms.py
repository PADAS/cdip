from django import forms

from .models import OutboundIntegrationConfiguration, InboundIntegrationConfiguration


# class DeviceGroupForm(forms.ModelForm):
#     class Meta:
#         model = DeviceGroup
#         fields = ('name', 'type', 'organization_group', 'devices', 'configuration',
#                   'start_date', 'end_date', 'start_time', 'end_time')


class InboundIntegrationConfigurationForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput(render_value=True), required=False)

    class Meta:
        model = InboundIntegrationConfiguration
        exclude = ['id']
        widgets = {
            'password': forms.PasswordInput(),
            # 'state': forms.HiddenInput()
        }


class OutboundIntegrationConfigurationForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput(render_value=True), required=False)

    class Meta:
        model = OutboundIntegrationConfiguration
        exclude = ['id']
        widgets = {
            'password': forms.PasswordInput(),
        }

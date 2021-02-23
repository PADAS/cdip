from django import forms

from accounts.utils import get_user_profile
from organizations.models import Organization
from .models import OutboundIntegrationConfiguration, InboundIntegrationConfiguration, DeviceGroup, Device


class DeviceGroupForm(forms.ModelForm):
    class Meta:
        model = DeviceGroup
        exclude = ['id', 'devices', 'organization_group', 'start_date', 'end_date', 'start_time', 'end_time']

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.profile = get_user_profile(self.user.username)
        super(DeviceGroupForm, self).__init__(*args, **kwargs)
        # self.fields['owner'].queryset = Organization.objects.filter(id__in=self.organizations.all())


class DeviceGroupManagementForm(forms.ModelForm):
    class Meta:
        model = DeviceGroup
        exclude = ['id', 'name', 'destinations', 'owner',
                   'organization_group', 'start_date', 'end_date', 'start_time', 'end_time']

    def __init__(self, *args, **kwargs):
        super(DeviceGroupManagementForm, self).__init__(*args, **kwargs)
        if self.instance:
            self.fields['devices'].queryset =\
                Device.objects.filter(inbound_configuration__owner_id=self.instance.owner_id)


class InboundIntegrationConfigurationForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput(render_value=True), required=False)

    class Meta:
        model = InboundIntegrationConfiguration
        exclude = ['id',]
        labels = {'default_devicegroup': "Default Device Group"}
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

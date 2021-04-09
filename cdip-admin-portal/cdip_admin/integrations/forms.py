from django import forms

from accounts.utils import get_user_profile
from core.permissions import IsGlobalAdmin, IsOrganizationMember
from organizations.models import Organization
from .models import OutboundIntegrationConfiguration, OutboundIntegrationType, InboundIntegrationConfiguration, \
    InboundIntegrationType, DeviceGroup, Device


class DeviceGroupForm(forms.ModelForm):
    class Meta:
        model = DeviceGroup
        exclude = ['id', 'devices',]

    def __init__(self, *args, request=None, **kwargs):
        super(DeviceGroupForm, self).__init__(*args, **kwargs)
        if self.instance and request:
            qs = Organization.objects.all()
            if not IsGlobalAdmin.has_permission(None, request, None):
                self.fields['owner'].queryset = IsOrganizationMember.\
                    filter_queryset_for_user(qs, request.user, 'name')
            else:
                self.fields['owner'].queryset = qs


class DeviceGroupManagementForm(forms.ModelForm):
    class Meta:
        model = DeviceGroup
        exclude = ['id', 'name', 'destinations', 'owner',]

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

    def __init__(self, *args, request=None, **kwargs):
        super(InboundIntegrationConfigurationForm, self).__init__(*args, **kwargs)
        if self.instance and request:
            qs = Organization.objects.all()
            if not IsGlobalAdmin.has_permission(None, request, None):
                self.fields['owner'].queryset = IsOrganizationMember. \
                    filter_queryset_for_user(qs, request.user, 'name', admin_only=True)
            else:
                self.fields['owner'].queryset = qs


class InboundIntegrationTypeForm(forms.ModelForm):

    class Meta:
        model = InboundIntegrationType
        exclude = ['id']


class OutboundIntegrationConfigurationForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput(render_value=True), required=False)

    class Meta:
        model = OutboundIntegrationConfiguration
        exclude = ['id']
        widgets = {
            'password': forms.PasswordInput(),
        }

    def __init__(self, *args, request=None, **kwargs):
        super(OutboundIntegrationConfigurationForm, self).__init__(*args, **kwargs)
        if self.instance and request:
            qs = Organization.objects.all()
            if not IsGlobalAdmin.has_permission(None, request, None):
                self.fields['owner'].queryset = IsOrganizationMember. \
                    filter_queryset_for_user(qs, request.user, 'name', admin_only=True)
            else:
                self.fields['owner'].queryset = qs


class OutboundIntegrationTypeForm(forms.ModelForm):

    class Meta:
        model = OutboundIntegrationType
        exclude = ['id']

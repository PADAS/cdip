from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit
from django import forms

from core.permissions import IsGlobalAdmin, IsOrganizationMember
from core.widgets import FormattedJsonFieldWidget, PeekabooTextInput, ReadonlyPeekabooTextInput
from organizations.models import Organization
from .models import BridgeIntegration
from .models import OutboundIntegrationConfiguration, OutboundIntegrationType, InboundIntegrationConfiguration, \
    InboundIntegrationType, DeviceGroup


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

    helper = FormHelper()
    helper.add_input(Submit('submit', 'Save', css_class='btn-primary'))
    helper.form_method = 'POST'


class DeviceGroupManagementForm(forms.ModelForm):
    class Meta:
        model = DeviceGroup
        exclude = ['id', 'name', 'destinations', 'owner']

    helper = FormHelper()
    helper.add_input(Submit('submit', 'Save', css_class='btn-primary'))
    helper.form_method = 'POST'


class InboundIntegrationConfigurationForm(forms.ModelForm):

    class Meta:
        model = InboundIntegrationConfiguration
        exclude = ['id',]
        fields = (
            'name', 'type', 'owner', 'enabled', 'default_devicegroup', 'endpoint', 'login', 'password', 'token',
            'state', 'consumer_id',)
        labels = {'default_devicegroup': "Default Device Group"}
        widgets = {
            'password': PeekabooTextInput(),
            'token': PeekabooTextInput(),
            'state': FormattedJsonFieldWidget(),
            'apikey': PeekabooTextInput(),
        }

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and request:
            qs = Organization.objects.all()
            if not IsGlobalAdmin.has_permission(None, request, None):
                self.fields['owner'].queryset = IsOrganizationMember. \
                    filter_queryset_for_user(qs, request.user, 'name', admin_only=True)
            else:
                self.fields['owner'].queryset = qs

    helper = FormHelper()
    helper.add_input(Submit('submit', 'Save', css_class='btn-primary'))
    helper.form_method = 'POST'


class InboundIntegrationTypeForm(forms.ModelForm):

    class Meta:
        model = InboundIntegrationType
        exclude = ['id']

    helper = FormHelper()
    helper.add_input(Submit('submit', 'Save', css_class='btn-primary'))
    helper.form_method = 'POST'


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

    helper = FormHelper()
    helper.add_input(Submit('submit', 'Save', css_class='btn-primary'))
    helper.form_method = 'POST'


class OutboundIntegrationTypeForm(forms.ModelForm):

    class Meta:
        model = OutboundIntegrationType
        exclude = ['id']

    helper = FormHelper()
    helper.add_input(Submit('submit', 'Save', css_class='btn-primary'))
    helper.form_method = 'POST'


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

    helper = FormHelper()
    helper.add_input(Submit('submit', 'Save', css_class='btn-primary'))
    helper.form_method = 'POST'


class DeviceGroupManagementForm(forms.ModelForm):
    class Meta:
        model = DeviceGroup
        exclude = ['id', 'name', 'destinations', 'owner']

    helper = FormHelper()
    helper.add_input(Submit('submit', 'Save', css_class='btn-primary'))
    helper.form_method = 'POST'


class InboundIntegrationTypeForm(forms.ModelForm):

    class Meta:
        model = InboundIntegrationType
        exclude = ['id']

    helper = FormHelper()
    helper.add_input(Submit('submit', 'Save', css_class='btn-primary'))
    helper.form_method = 'POST'


class OutboundIntegrationConfigurationForm(forms.ModelForm):

    class Meta:
        model = OutboundIntegrationConfiguration
        exclude = ['id']
        widgets = {
            'password': PeekabooTextInput(attrs={'class': 'form-control'}),
            'token': PeekabooTextInput(attrs={'class': 'form-control'}),
            'state': FormattedJsonFieldWidget(),
        }

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and request:
            qs = Organization.objects.all()
            if not IsGlobalAdmin.has_permission(None, request, None):
                self.fields['owner'].queryset = IsOrganizationMember. \
                    filter_queryset_for_user(qs, request.user, 'name', admin_only=True)
            else:
                self.fields['owner'].queryset = qs

    helper = FormHelper()
    helper.add_input(Submit('submit', 'Save', css_class='btn-primary'))
    helper.form_method = 'POST'


class OutboundIntegrationTypeForm(forms.ModelForm):

    class Meta:
        model = OutboundIntegrationType
        exclude = ['id']

    helper = FormHelper()
    helper.add_input(Submit('submit', 'Save', css_class='btn-primary'))
    helper.form_method = 'POST'


class BridgeIntegrationForm(forms.ModelForm):

    class Meta:
        model = BridgeIntegration
        exclude = ['id', 'state',]
        fields = ('name', 'type', 'owner', 'enabled', 'additional', 'state')
        widgets = {
            'additional': FormattedJsonFieldWidget(),
            'state': FormattedJsonFieldWidget(),
        }

    def __init__(self, *args, request=None, **kwargs):
        super(BridgeIntegrationForm, self).__init__(*args, **kwargs)
        if self.instance and request:
            qs = Organization.objects.all()
            if not IsGlobalAdmin.has_permission(None, request, None):
                self.fields['owner'].queryset = IsOrganizationMember. \
                    filter_queryset_for_user(qs, request.user, 'name', admin_only=True)
            else:
                self.fields['owner'].queryset = qs

    helper = FormHelper()
    helper.add_input(Submit('submit', 'Save', css_class='btn-primary'))
    helper.form_method = 'POST'


class KeyAuthForm(forms.Form):
    key = forms.CharField(label="API Key", max_length=100, widget=ReadonlyPeekabooTextInput, required=False)


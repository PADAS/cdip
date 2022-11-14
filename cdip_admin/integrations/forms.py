from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Submit, Row, Column, MultiField
from crispy_forms.layout import Submit, Field
from django import forms
from django.urls import reverse_lazy
from django_jsonform.widgets import JSONFormWidget

from core.permissions import IsGlobalAdmin, IsOrganizationMember
from core.widgets import (
    FormattedJsonFieldWidget,
    PeekabooTextInput,
    ReadonlyPeekabooTextInput,
)
from organizations.models import Organization
from .models import BridgeIntegration, Device
from .models import (
    OutboundIntegrationConfiguration,
    OutboundIntegrationType,
    InboundIntegrationConfiguration,
    InboundIntegrationType,
    DeviceGroup,
    BridgeIntegrationType
)
from django.urls import reverse


def tooltip_labels(text):
    return f""" <button type="button" class="btn btn-light btn-sm py-0 mb-0 align-top" 
    data-toggle="tooltip" data-placement="right" 
    title="{text}">?</button>"""


class InboundIntegrationConfigurationForm(forms.ModelForm):
    class Meta:
        model = InboundIntegrationConfiguration
        exclude = [
            "id",
        ]

        widgets = {
            "password": PeekabooTextInput(),
            "token": PeekabooTextInput(),
            "state": FormattedJsonFieldWidget(),
            "apikey": PeekabooTextInput(),
        }

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance:
            for field_name in self.fields:
                if self.fields[field_name].help_text != "":
                    self.fields[
                        field_name
                    ].label += tooltip_labels(self.fields[field_name].help_text)
                self.fields[field_name].help_text = None
            if request:
                qs = Organization.objects.all()
                if not IsGlobalAdmin.has_permission(None, request, None):
                    self.fields[
                        "owner"
                    ].queryset = IsOrganizationMember.filter_queryset_for_user(
                        qs, request.user, "name", admin_only=True
                    )
                else:
                    self.fields["owner"].queryset = qs

    helper = FormHelper()
    helper.add_input(Submit("submit", "Save", css_class="btn-primary"))
    helper.form_method = "POST"

    helper.layout = Layout(
        Row(
            Column(Field("name", autocomplete="off"), css_class="form-group col-lg-3 mb-0"),
            Column("owner", css_class="form-group col-lg-3 mb-0"),
            css_class="form-row",
        ),
        Row(
            Column("type", css_class="form-group col-lg-3 mb-0"),
            Column(
                Field("provider", autocomplete="off"), css_class="form-group col-lg-3 mb-0"
            ),
            css_class="form-row",
        ),
        "enabled",
        Row(
            Column("default_devicegroup", css_class="form-group col-lg-3 mb-0"),
            css_class="form-row",
        ),
        Row(
            Column(
                Field("endpoint", autocomplete="off"),
                css_class="form-group col-lg-3 mb-0",
            ),
            Column(Field("token", autocomplete="off"), css_class="form-group col-lg-3 mb-0"),
            css_class="form-row",
        ),
        Row(
            Column(Field("login", autocomplete="off"), css_class="form-group col-md-3"),
            Column(
                Field("password", autocomplete="off"), css_class="form-group col-md-3"
            ),
            css_class="form-row",
        ),
        Row(Column("state", css_class="form-group col-lg-3 mb-0")),
    )


class InboundIntegrationTypeForm(forms.ModelForm):
    class Meta:
        model = InboundIntegrationType
        exclude = ["id"]

    helper = FormHelper()
    helper.add_input(Submit("submit", "Save", css_class="btn-primary"))
    helper.form_method = "POST"


class OutboundIntegrationConfigurationForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput(render_value=True), required=False
    )

    class Meta:
        model = OutboundIntegrationConfiguration
        exclude = ["id"]
        widgets = {
            "password": forms.PasswordInput(),
        }

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and request:
            qs = Organization.objects.all()
            for field_name in self.fields:
                if self.fields[field_name].help_text != "":
                    self.fields[
                        field_name
                    ].label += tooltip_labels(self.fields[field_name].help_text)
                self.fields[field_name].help_text = None
            if not IsGlobalAdmin.has_permission(None, request, None):
                self.fields[
                    "owner"
                ].queryset = IsOrganizationMember.filter_queryset_for_user(
                    qs, request.user, "name", admin_only=True
                )
            else:
                self.fields["owner"].queryset = qs

    helper = FormHelper()
    helper.add_input(Submit("submit", "Save", css_class="btn-primary"))
    helper.form_method = "POST"


class OutboundIntegrationTypeForm(forms.ModelForm):
    class Meta:
        model = OutboundIntegrationType
        exclude = ["id"]

    helper = FormHelper()
    helper.add_input(Submit("submit", "Save", css_class="btn-primary"))
    helper.form_method = "POST"


class DeviceGroupForm(forms.ModelForm):
    class Meta:
        model = DeviceGroup
        exclude = [
            "id",
            "devices",
        ]

    def __init__(self, *args, request=None, **kwargs):
        super(DeviceGroupForm, self).__init__(*args, **kwargs)
        for field_name in self.fields:
            if self.fields[field_name].help_text != "":
                self.fields[
                    field_name
                ].label += tooltip_labels(self.fields[field_name].help_text)
            self.fields[field_name].help_text = None
        if self.instance and request:
            qs = Organization.objects.all()
            if not IsGlobalAdmin.has_permission(None, request, None):
                self.fields[
                    "owner"
                ].queryset = IsOrganizationMember.filter_queryset_for_user(
                    qs, request.user, "name"
                )
            else:
                self.fields["owner"].queryset = qs

    field_order = [
        "name",
        "owner",
        "default_subject_type",
        "destinations",
    ]
    helper = FormHelper()
    helper.add_input(Submit("submit", "Save", css_class="btn-primary"))
    helper.form_method = "POST"


class DeviceGroupManagementForm(forms.ModelForm):
    class Meta:
        model = DeviceGroup
        exclude = ["id", "name", "destinations", "owner"]

    helper = FormHelper()
    helper.add_input(Submit("submit", "Save", css_class="btn-primary"))
    helper.form_method = "POST"


class DeviceForm(forms.ModelForm):
    class Meta:
        model = Device
        exclude = ["id"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in self.fields:
            if self.fields[field_name].help_text != "":
                self.fields[
                    field_name
                ].label += tooltip_labels(self.fields[field_name].help_text)
            self.fields[field_name].help_text = None

    helper = FormHelper()
    helper.layout = Layout(
        Row(
            Column(Field("name", autocomplete="off"), css_class="form-group col-lg-3 mb-0"),
            Column("external_id", css_class="form-group col-lg-3 mb-0"),
            css_class="form-row",
        ),
        Row(
            Column(Field("inbound_configuration", autocomplete="off"), css_class="form-group col-lg-3 mb-0"),
            Column("subject_type", css_class="form-group col-lg-3 mb-0"),
            css_class="form-row",
        ),
        Row(
            Column("additional", css_class="form-group col-lg-6"),
            css_class="form-row",
        ),
    )
    helper.add_input(Submit("submit", "Save", css_class="btn-primary"))
    helper.form_method = "POST"


class InboundIntegrationTypeForm(forms.ModelForm):
    class Meta:
        model = InboundIntegrationType
        exclude = ["id"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in self.fields:
            if self.fields[field_name].help_text != "":
                self.fields[
                    field_name
                ].label += tooltip_labels(self.fields[field_name].help_text)
            self.fields[field_name].help_text = None

    helper = FormHelper()
    helper.layout = Layout(
        Row(
            Column("name", autocomplete="off", css_class="form-group col-lg-3 mb-0"),
            Column("slug", css_class="form-group col-lg-3 mb-0"),
            css_class="form-row",
        ),
        Row(
            Column("description", css_class="form-group col-lg-6 mt-0"),
            css_class="form-row",
        ),
    )
    helper.add_input(Submit("submit", "Save", css_class="btn-primary"))
    helper.form_method = "POST"


class OutboundIntegrationConfigurationForm(forms.ModelForm):
    class Meta:
        model = OutboundIntegrationConfiguration
        exclude = ["id"]
        widgets = {
            "password": PeekabooTextInput(attrs={"class": "form-control"}),
            "token": PeekabooTextInput(attrs={"class": "form-control"}),
            "state": FormattedJsonFieldWidget(),
            "additional": FormattedJsonFieldWidget(),
        }

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance:
            for field_name in self.fields:
                if self.fields[field_name].help_text != "":
                    self.fields[
                        field_name
                    ].label += tooltip_labels(self.fields[field_name].help_text)
                self.fields[field_name].help_text = None
            if request:
                qs = Organization.objects.all()
                if not IsGlobalAdmin.has_permission(None, request, None):
                    self.fields[
                        "owner"
                    ].queryset = IsOrganizationMember.filter_queryset_for_user(
                        qs, request.user, "name", admin_only=True
                    )
                else:
                    self.fields["owner"].queryset = qs

    helper = FormHelper()
    helper.layout = Layout(
        Row(
            Column(Field("name", autocomplete="off"), css_class="form-group col-lg-3 mb-0"),
            Column("owner", css_class="form-group col-lg-3 mb-0"),
            css_class="form-row",
        ),
        Row(
            Column("enabled", css_class="form-group col-lg-6 mt-0"),
            css_class="form-row",
        ),
        Row(
            Column("type", css_class="form-group col-lg-6"),
            css_class="form-row",
        ),
        Row(
            Column(
                Field("endpoint", autocomplete="off"),
                css_class="form-group col-lg-3 mb-0",
            ),
            Column(Field("token", autocomplete="off"), css_class="form-group col-lg-3 mb-0"),
            css_class="form-row",
        ),
        Row(
            Column(Field("login", autocomplete="off"), css_class="form-group col-md-3"),
            Column(
                Field("password", autocomplete="off"), css_class="form-group col-md-3"
            ),
            css_class="form-row",
        ),
        Row(Column("state", css_class="form-group col-lg-3 mb-0")),
        Row(
            Column("additional", css_class="form-group col-lg-6"),
            css_class="form-row",
        ),
    )
    helper.add_input(Submit("submit", "Save", css_class="btn-primary"))
    helper.form_method = "POST"


class OutboundIntegrationTypeForm(forms.ModelForm):
    class Meta:
        model = OutboundIntegrationType
        exclude = ["id"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in self.fields:
            if self.fields[field_name].help_text != "":
                self.fields[
                    field_name
                ].label += tooltip_labels(self.fields[field_name].help_text)
            self.fields[field_name].help_text = None

    helper = FormHelper()
    helper.layout = Layout(
        Row(
            Column(Field("name", autocomplete="off"), css_class="form-group col-lg-3 mb-0"),
            Column("slug", css_class="form-group col-lg-3 mb-0"),
            css_class="form-row",
        ),
        Row(
            Column("description", css_class="form-group col-lg-6 mt-0"),
            css_class="form-row",
        ),
        Row(
            Column("use_endpoint", css_class="form-group col-lg-6 my-0"),
            css_class="form-row",
        ),
        Row(
            Column("use_login", css_class="form-group col-lg-6 my-0"),
            css_class="form-row",
        ),
        Row(
            Column("use_password", css_class="form-group col-lg-6 my-0"),
            css_class="form-row",
        ),
        Row(
            Column("use_token", css_class="form-group col-lg-6 mt-0"),
            css_class="form-row",
        ),
    )
    helper.add_input(Submit("submit", "Save", css_class="btn-primary"))
    helper.form_method = "POST"


class BridgeIntegrationForm(forms.ModelForm):
    def full_clean(self):

        if hasattr(self.instance, 'type'):
            self.fields['additional'].widget.instance = self.instance.type.id

        super().full_clean()

    class Meta:
        model = BridgeIntegration
        exclude = [
            "id",
            "state",
        ]
        fields = ("name", "owner", "enabled", "type", "additional", "state")
        widgets = {
            "type": forms.Select(
                attrs={
                    'name': "type",
                    'hx-trigger': 'change',
                    'hx-target': 'body',
                    'hx-swap': 'beforeend'
                }),
            "additional": JSONFormWidget(
                schema=BridgeIntegrationType.objects.configuration_schema,
            ),
            "state": FormattedJsonFieldWidget(),
        }

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance:
            for field_name in self.fields:
                if self.fields[field_name].help_text != "":
                    self.fields[
                        field_name
                    ].label += tooltip_labels(self.fields[field_name].help_text)
                self.fields[field_name].help_text = None
            qs = Organization.objects.all()
            if request:
                if not IsGlobalAdmin.has_permission(None, request, None):
                    self.fields[
                        "owner"
                    ].queryset = IsOrganizationMember.filter_queryset_for_user(
                        qs, request.user, "name", admin_only=True
                    )
                else:
                    self.fields["owner"].queryset = qs
            self.fields['type'].widget.attrs['hx-get'] = reverse("type_modal",
                                                                 kwargs={"integration_id": self.instance.id})
            if hasattr(self.instance, 'type'):

                if hasattr(request, 'session'):
                    request.session["integration_type"] = str(self.instance.type.id)
                self.fields['additional'].widget.instance = self.instance.type.id

    helper = FormHelper()
    helper.layout = Layout(
            Row(
                Column(Field("name", autocomplete="off"), css_class="form-group col-lg-3 mb-0"),
                Column("owner", css_class="form-group col-lg-3 mb-0"),
                css_class="form-row",
            ),
            Row(
                Column("enabled", css_class="form-group col-lg-6 mt-0"),
                css_class="form-row",
             ),
            Row(
                Column("type", css_class="form-group col-lg-6"),
                css_class="form-row",
            ),
            Row(
                Column("additional", css_class="form-group col-lg-6"),
                css_class="form-row",
            ),
    )
    helper.add_input(Submit("submit", "Save", css_class="btn btn-primary"))
    helper.form_method = "POST"


class KeyAuthForm(forms.Form):
    key = forms.CharField(
        label="API Key",
        max_length=100,
        widget=ReadonlyPeekabooTextInput,
        required=False,
    )

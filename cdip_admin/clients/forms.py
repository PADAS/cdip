from django import forms

from clients.models import ClientProfile


grant_types = {
    "authorization_code": "authorization_code",
    "implicit": "implicit",
    "refresh_token": "refresh_token",
    "client_credentials": "client_credentials",
}

grant_types_init = [
    "authorization_code",
    "implicit",
    "refresh_token",
    "client_credentials",
]


class ClientForm(forms.Form):
    clientId = forms.CharField(max_length=200, required=True, label="Client ID")
    rootUrl = forms.URLField(
        max_length=200, required=False, label="Root Url", widget=forms.HiddenInput
    )
    protocol = forms.CharField(
        max_length=200,
        required=True,
        initial="openid-connect",
        widget=forms.HiddenInput,
    )


class ClientUpdateForm(forms.Form):
    clientId = forms.CharField(max_length=200, required=True, label="Client ID")
    rootUrl = forms.URLField(
        max_length=200, required=False, label="Root Url", widget=forms.HiddenInput
    )
    protocol = forms.CharField(
        max_length=200,
        required=True,
        initial="openid-connect",
        widget=forms.HiddenInput,
    )


class ClientProfileForm(forms.ModelForm):
    client_id = forms.CharField(widget=forms.HiddenInput, required=False)

    class Meta:
        model = ClientProfile
        exclude = ["id", "organizations"]


class ClientProfileUpdateForm(forms.ModelForm):
    id = forms.UUIDField(widget=forms.HiddenInput)
    client_id = forms.CharField(widget=forms.HiddenInput)

    class Meta:
        model = ClientProfile
        fields = ["id", "client_id", "type"]

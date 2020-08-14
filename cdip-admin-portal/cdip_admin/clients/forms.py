from django import forms
from environ import Env

env = Env()
env.read_env()

AUTH0_TENANT = env('AUTH0_TENANT')

grant_types = {
    'authorization_code': 'authorization_code',
    'implicit': 'implicit',
    'refresh_token': 'refresh_token',
    'client_credentials': 'client_credentials'
}

grant_types_init = [
    'authorization_code',
    'implicit',
    'refresh_token',
    'client_credentials'
]


class ClientForm(forms.Form):
    name = forms.CharField(max_length=200, required=True)
    description = forms.CharField(max_length=200, required=True)
    # tenant = forms.CharField(initial=AUTH0_TENANT, widget=forms.HiddenInput)
    # grant_types = forms.(widget=forms.HiddenInput, initial=grant_types_init)

    # def __init__(self, *args, **kwargs):
    #     super(ClientForm, self).__init__(*args, **kwargs)
    #     self.fields["grant_types"].initial = grant_types_init


class ClientUpdateForm(forms.Form):
    name = forms.CharField(max_length=200, required=True)
    description = forms.CharField(max_length=200, required=True)




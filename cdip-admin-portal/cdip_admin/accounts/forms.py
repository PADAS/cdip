from django import forms
from django.contrib.auth.models import Permission

from accounts.models import AccountProfile
from core.models import Task


class AccountForm(forms.Form):
    firstName = forms.CharField(max_length=200, label='First Name', required=True)
    lastName = forms.CharField(max_length=200, label='Last Name', required=True)
    username = forms.CharField(max_length=200, label='User Name', required=True)
    email = forms.EmailField(max_length=200, label='Email', required=True)
    enabled = forms.CharField(max_length=200, initial='true', widget=forms.HiddenInput)


class AccountUpdateForm(forms.Form):
    all_permissions = Task._meta.permissions
    firstName = forms.CharField(max_length=200, label='First Name', required=True)
    lastName = forms.CharField(max_length=200, label='Last Name', required=True)
    username = forms.CharField(max_length=200, label='User Name', required=True)
    email = forms.EmailField(max_length=200, label='Email', required=True)
    enabled = forms.CharField(max_length=200, widget=forms.HiddenInput)


class AccountProfileForm(forms.ModelForm):
    user_id = forms.CharField(widget=forms.HiddenInput)

    class Meta:
        model = AccountProfile
        exclude = ['id']


class AccountProfileUpdateForm(forms.ModelForm):
    id = forms.UUIDField(widget=forms.HiddenInput)
    user_id = forms.CharField(widget=forms.HiddenInput)

    class Meta:
        model = AccountProfile
        fields = ['id', 'user_id', 'organizations']


class AccountRoleForm(forms.Form):
    user_id = forms.CharField(widget=forms.HiddenInput)
    all_permissions = Task._meta.permissions
    permissions = forms.MultipleChoiceField(widget=forms.CheckboxSelectMultiple, label='Role',
                                            choices=all_permissions, required=True)




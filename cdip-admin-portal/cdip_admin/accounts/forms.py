from django import forms

from core.enums import RoleChoices
from core.models import Task
from django.forms.models import BaseModelFormSet


class AccountForm(forms.Form):
    email = forms.EmailField(max_length=200, label='Email', required=True)
    role = forms.ChoiceField(choices=[(tag.value, tag.value) for tag in RoleChoices])
    firstName = forms.CharField(max_length=200, label='First Name', required=False)
    lastName = forms.CharField(max_length=200, label='Last Name', required=False)
    organization = forms.CharField(widget=forms.HiddenInput, required=True)



class AccountUpdateForm(forms.Form):
    all_permissions = Task._meta.permissions
    firstName = forms.CharField(max_length=200, label='First Name', required=True)
    lastName = forms.CharField(max_length=200, label='Last Name', required=True)
    username = forms.CharField(max_length=200, label='User Name', required=True)


class AccountProfileForm(forms.Form):
    role = forms.ChoiceField(choices=[(tag.value, tag.value) for tag in RoleChoices])
    organization = forms.CharField(widget=forms.HiddenInput, required=True)







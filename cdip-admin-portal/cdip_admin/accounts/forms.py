from django import forms
from core.models import Task
from django.forms.models import BaseModelFormSet


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


class AccountProfileFormSet(BaseModelFormSet):
    def __init__(self, *args, **kwargs):
        form_kwargs = kwargs.pop('form_kwargs', None)
        super(AccountProfileFormSet, self).__init__(*args, **kwargs)

        if form_kwargs:
            for form in self.forms:
                form.fields['organization'].queryset = form_kwargs['qs']


class AccountRoleForm(forms.Form):
    user_id = forms.CharField(widget=forms.HiddenInput)
    all_permissions = Task._meta.permissions
    permissions = forms.MultipleChoiceField(widget=forms.CheckboxSelectMultiple, label='Role',
                                            choices=all_permissions, required=True)







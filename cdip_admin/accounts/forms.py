from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout, Row, Column
from django import forms

from core.enums import RoleChoices
from core.models import Task
from django.forms.models import BaseModelFormSet


class AccountForm(forms.Form):
    email = forms.EmailField(max_length=200, label="Email", required=True)
    role = forms.ChoiceField(choices=[(tag.value, tag.value) for tag in RoleChoices])
    first_name = forms.CharField(max_length=200, label="First Name", required=False)
    last_name = forms.CharField(max_length=200, label="Last Name", required=False)
    organization = forms.CharField(widget=forms.HiddenInput, required=True)

    helper = FormHelper()
    helper.add_input(Submit("submit", "Submit", css_class="btn-primary"))


class AccountUpdateForm(forms.Form):
    all_permissions = Task._meta.permissions
    firstName = forms.CharField(max_length=200, label="First Name", required=True)
    lastName = forms.CharField(max_length=200, label="Last Name", required=True)
    username = forms.CharField(max_length=200, label="User Name", required=True)

    helper = FormHelper()
    helper.layout = Layout(
        Row(
            Column("role", css_class="form-group col-lg-6 mb-0"),
            css_class="form-row",
        ),
    )
    helper.add_input(Submit("submit", "Save", css_class="btn-primary"))


class AccountProfileForm(forms.Form):
    role = forms.ChoiceField(choices=[(tag.value, tag.value) for tag in RoleChoices])
    organization = forms.CharField(widget=forms.HiddenInput, required=True)

    helper = FormHelper()
    helper.add_input(Submit("submit", "Save", css_class="btn-primary"))

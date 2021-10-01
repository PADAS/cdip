from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit
from django import forms

from .models import Organization


class OrganizationForm(forms.ModelForm):

    class Meta:
        model = Organization
        exclude = ['id']
        widgets = {}
        labels = {
            'name': 'Organization Name',
        }

    helper = FormHelper()
    helper.add_input(Submit('submit', 'Save', css_class='btn-primary'))
    helper.form_method = 'POST'

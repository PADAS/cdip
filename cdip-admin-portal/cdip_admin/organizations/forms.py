from django import forms
from .models import Organization


class OrganizationForm(forms.ModelForm):

    class Meta:
        model = Organization
        exclude = ['id']
        widgets = {}


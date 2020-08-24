from django import forms

from accounts.models import AccountProfile


class AccountForm(forms.Form):
    name = forms.CharField(max_length=200, required=True)
    email = forms.EmailField(max_length=200, required=True)
    password = forms.CharField(widget=forms.PasswordInput, label="Password", required=True)
    connection = forms.CharField(initial='Username-Password-Authentication', widget=forms.HiddenInput)


class AccountUpdateForm(forms.Form):
    name = forms.CharField(max_length=200, required=True)
    email = forms.EmailField(max_length=200, required=True)


class AccountProfileForm(forms.ModelForm):

    class Meta:
        model = AccountProfile
        exclude = ['id', 'user_id']




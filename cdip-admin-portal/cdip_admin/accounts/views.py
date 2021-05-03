import logging

from django.contrib.auth.decorators import permission_required
from django.contrib.auth.mixins import PermissionRequiredMixin, LoginRequiredMixin
from django.shortcuts import render, redirect, get_object_or_404
from django.core.exceptions import SuspiciousOperation, PermissionDenied
from django.forms import modelformset_factory
from django.views.generic import ListView, FormView, UpdateView
from django.contrib.auth.models import User

from cdip_admin import settings
from core.permissions import IsOrganizationMember, IsGlobalAdmin
from organizations.models import Organization
from .forms import AccountForm, AccountUpdateForm, AccountRoleForm
from .models import AccountProfile, AccountProfileOrganization
from .utils import add_account, get_account, update_account

KEYCLOAK_CLIENT = settings.KEYCLOAK_CLIENT_ID

logger = logging.getLogger(__name__)

ProfileFormSet = modelformset_factory(AccountProfileOrganization,
                                      fields=('organization', 'role'), extra=1)


class AccountsListView(LoginRequiredMixin, ListView):
    template_name = 'accounts/account_list.html'
    queryset = User.objects.filter(email__contains='@').order_by('last_name')
    context_object_name = 'accounts'
    logger.info('Getting account list')

    def get_queryset(self):
        qs = super().get_queryset()
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            user_orgs = IsOrganizationMember.get_organizations_for_user(self.request.user, admin_only=False)
            aco = AccountProfileOrganization.objects.filter(organization__name__in=user_orgs)
            apo_ids = aco.values_list('accountprofile_id', flat=True)
            ap = AccountProfile.objects.filter(id__in=apo_ids)
            uids = ap.values_list('user_id', flat=True)
            qs = qs.filter(username__in=uids)
            return qs
        else:
            return qs


@permission_required('accounts.view_accountprofile')
def account_detail(request, user_id):
    logger.info('Getting account detail')
    user = User.objects.get(username=user_id)
    try:
        profile = AccountProfile.objects.get(user_id=user_id)
        account_profiles = AccountProfileOrganization.objects.filter(accountprofile_id=profile.id)
    except AccountProfile.DoesNotExist:
        profile = None
        account_profiles = None

    return render(request, "accounts/account_detail.html", {"user": user, "profile": profile,
                                                            "account_profiles": account_profiles})


class AccountsAddView(LoginRequiredMixin, FormView):
    form_class = AccountForm

    def post(self, request, *args, **kwargs):
        form = AccountForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            response = add_account(data)

            if response:
                return redirect('account_list')
            else:
                raise SuspiciousOperation

    def get(self, request, *args, **kwargs):
        form = AccountForm()
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            # can only add if you are an admin of at least one organization
            if not IsOrganizationMember.filter_queryset_for_user(Organization.objects.all(),
                                                                 self.request.user, 'name', True):
                raise PermissionDenied
        return render(request, "accounts/account_add.html", {'form': form})


class AccountsUpdateView(PermissionRequiredMixin, UpdateView):
    template_name = 'organizations/organizations_update.html'
    form_class = AccountUpdateForm
    permission_required = 'accounts.change_accountprofile'

    def post(self, request, *args, **kwargs):
        account_form = AccountUpdateForm(request.POST)
        user_id = self.kwargs.get("user_id")
        if account_form.is_valid():
            data = account_form.cleaned_data
            response = update_account(data, user_id)

            if response:
                return redirect('account_detail', user_id=user_id)
            else:
                raise SuspiciousOperation

    def get(self, request, *args, **kwargs):
        account_form = AccountUpdateForm()
        user_id = self.kwargs.get("user_id")
        account = get_account(user_id)

        account_form.initial['firstName'] = account["firstName"]
        account_form.initial['lastName'] = account["lastName"]
        account_form.initial['username'] = account["username"]
        account_form.initial['email'] = account["email"]
        account_form.initial['enabled'] = account["enabled"]

        return render(request, "accounts/account_update.html", {"account_form": account_form, "user_id": user_id})


@permission_required('accounts.add_accountprofile')
def account_profile_add(request, user_id):
    if request.method == 'POST':
        profile_form = ProfileFormSet(request.POST)
        if profile_form.is_valid():
            instances = profile_form.save(commit=False)
            profile = AccountProfile.objects.create(user_id=user_id)
            for instance in instances:
                instance.accountprofile_id = profile.id
                instance.save()
            return redirect('account_detail', user_id=user_id)
        else:
            return render(request, "accounts/account_profile_add.html", {"user_id": user_id,
                                                                         "profile_form": profile_form})

    else:
        profile_form = ProfileFormSet(queryset=AccountProfileOrganization.objects.none())
        return render(request, "accounts/account_profile_add.html", {"user_id": user_id, "profile_form": profile_form})


@permission_required('accounts.change_accountprofile')
def account_profile_update(request, user_id):
    profile = get_object_or_404(AccountProfile, user_id=user_id)

    if request.method == 'POST':
        profile_form = ProfileFormSet(request.POST)
        if profile_form.is_valid():
            instances = profile_form.save(commit=False)
            for instance in instances:
                instance.accountprofile_id = profile.id
                instance.save()
            profile_form.save()
            return redirect('account_detail', user_id=user_id)
        else:
            return render(request, "accounts/account_profile_update.html", {"user_id": user_id,
                                                                            "profile_form": profile_form})

    else:
        qs = Organization.objects.all()
        profile_form = ProfileFormSet(queryset=AccountProfileOrganization.objects.filter(accountprofile_id=profile.id))
        if not IsGlobalAdmin.has_permission(None, request, None):
            qs = IsOrganizationMember.filter_queryset_for_user(qs, request.user, 'name', True)
            for form in profile_form.forms:
                org_bound_field = form['organization']
                org_field_val = org_bound_field.form.initial.get(org_bound_field.name, '')
                org_choice_field = form.fields['organization']
                role_choice_field = form.fields['role']
                # if form is not an empty form
                if org_field_val:
                    org_name = Organization.objects.get(id=org_field_val)
                    # disable form fields if user is not admin of the set organization
                    if org_name not in qs:
                        org_choice_field.widget.attrs['readonly'] = True
                        role_choice_field.widget.attrs['readonly'] = True
                        # org_choice_field.widget.attrs['disabled'] = True
                        # role_choice_field.widget.attrs['disabled'] = True
                        # org_choice_field.widget.attrs['required'] = False
                        # role_choice_field.widget.attrs['required'] = False
                    # otherwise restrict organization options
                    else:
                        org_choice_field.queryset = qs
                # restrict the organizations options on empty form
                else:
                    org_choice_field.queryset = qs
        return render(request, "accounts/account_profile_update.html",
                      {"profile_form": profile_form, "user_id": user_id})

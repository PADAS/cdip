import logging

from django.contrib.auth.decorators import permission_required
from django.contrib.auth.mixins import PermissionRequiredMixin, LoginRequiredMixin
from django.shortcuts import render, redirect, get_object_or_404
from django.core.exceptions import SuspiciousOperation, PermissionDenied
from django.forms import modelformset_factory
from django.views.generic import ListView, FormView, UpdateView

from cdip_admin import settings
from core.permissions import IsOrganizationMember, IsGlobalAdmin
from organizations.models import Organization
from .forms import AccountForm, AccountUpdateForm, AccountRoleForm
from .utils import get_accounts, get_account, add_account, update_account, get_account_roles, add_account_roles, \
    get_client_roles
from .models import AccountProfile, AccountProfileOrganization

KEYCLOAK_CLIENT = settings.KEYCLOAK_CLIENT_ID

logger = logging.getLogger(__name__)

ProfileFormSet = modelformset_factory(AccountProfileOrganization,
                                      fields=('organization', 'role'), extra=1)


class AccountsListView(LoginRequiredMixin, ListView):
    template_name = 'accounts/account_list.html'
    queryset = accounts = get_accounts()
    context_object_name = 'accounts'
    logger.info('Getting account list')

    def get_queryset(self):
        qs = super(AccountsListView, self).get_queryset()
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            account_ids = []
            # create a queryset of account profiles based on ids
            for user_profile in qs:
                try:
                    account_profile = AccountProfile.objects.get(user_id=user_profile['id'])
                except AccountProfile.DoesNotExist:
                    account_profile = None
                if account_profile is not None:
                    account_ids.append(account_profile.id)
            # get the distinct organizations that are mapped to those profiles
            apo_qs = AccountProfileOrganization.objects.all().filter(accountprofile__id__in=account_ids)
            org_qs = apo_qs.values_list('organization', flat=True).distinct()
            # filter those organizations based on what current user is allowed to see
            org_qs = IsOrganizationMember.filter_queryset_for_user(org_qs, self.request.user, 'organization__name')
            # filter our account organization profile queryset by those allowed organizations
            apo_qs = apo_qs.filter(organization__in=org_qs)
            # get back to valid account profiles by filtering against the list of valid account profile ids
            ap_qs = AccountProfile.objects.filter(id__in=apo_qs.values_list('accountprofile_id', flat=True))
            filtered_qs = []
            # loop through our original list of users and only include accounts we deem viewable
            for user_profile in qs:
                pass
                if ap_qs.filter(user_id=user_profile['id']).exists():
                    filtered_qs.append(user_profile)
            return filtered_qs
        else:
            return qs


@permission_required('accounts.view_accountprofile')
def account_detail(request, user_id):
    logger.info('Getting account detail')
    account = get_account(user_id)
    account_profiles = None
    try:
        profile = AccountProfile.objects.get(user_id=user_id)
        account_profiles = AccountProfileOrganization.objects.filter(accountprofile_id=profile.id)
    except AccountProfile.DoesNotExist:
        profile = None

    return render(request, "accounts/account_detail.html", {"account": account, "profile": profile,
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
        # if not IsOrganizationAdmin.has_object_permission(None, self.request, None, organization):
        #     raise PermissionDenied
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
        qs = Organization.objects.all()
        if not IsGlobalAdmin.has_permission(None, request, None):
            qs = IsOrganizationMember.filter_queryset_for_user(Organization.objects.all(), request.user, 'name', True)
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
                    # otherwise restrict organization options
                    else:
                        org_choice_field.queryset = qs
                # restrict the organizations options on empty form
                else:
                    org_choice_field.queryset = qs
        return render(request, "accounts/account_profile_update.html",
                      {"profile_form": profile_form, "user_id": user_id})


@permission_required('core.admin')
def account_role_add(request, user_id):
    logger.info('Manage account roles')
    user_roles = get_account_roles(user_id)
    if request.method == 'POST':
        account_role_form = AccountRoleForm(request.POST)
        client_roles = get_client_roles()
        if account_role_form.is_valid():
            data = account_role_form.cleaned_data
            permissions = data['permissions']

            if permissions:
                update_roles = []

                for perm in data['permissions']:
                    role = next((x for x in client_roles if x['name'] == 'core.' + perm), None)

                    if role is not None:
                        update_roles.append(role)

            response = add_account_roles(update_roles, user_id)

            if response:
                return redirect('account_detail', user_id=user_id)
            else:
                raise SuspiciousOperation

    else:
        roles = []
        for role in user_roles:
            role_name = role['name'].replace("core.", "")
            roles.append(role_name)
        account_role_form = AccountRoleForm()
        account_role_form.initial['permissions'] = roles
        account_role_form.initial['user_id'] = user_id
        return render(request, "accounts/account_role_add.html", {"account_role_form": account_role_form,
                                                                  "user_id": user_id})

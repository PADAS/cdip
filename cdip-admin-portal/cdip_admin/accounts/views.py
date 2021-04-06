import logging

from django.contrib.auth.decorators import permission_required
from django.contrib.auth.mixins import PermissionRequiredMixin, LoginRequiredMixin
from django.shortcuts import render, redirect, get_object_or_404
from django.core.exceptions import SuspiciousOperation
from django.forms import modelformset_factory
from django.views.generic import ListView

from cdip_admin import settings
from core.permissions import IsOrganizationAdmin, IsGlobalAdmin
from organizations.models import Organization
from .forms import AccountForm, AccountUpdateForm, AccountRoleForm, AccountProfileFormSet
from .utils import get_accounts, get_account, add_account, update_account, get_account_roles, add_account_roles, \
    get_client_roles
from .models import AccountProfile, AccountProfileOrganization

KEYCLOAK_CLIENT = settings.KEYCLOAK_CLIENT_ID

logger = logging.getLogger(__name__)

ProfileFormSet = modelformset_factory(AccountProfileOrganization, formset=AccountProfileFormSet,
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
            org_qs = IsOrganizationAdmin.filter_queryset_for_user(org_qs, self.request.user, 'organization__name')
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


@permission_required('core.admin')
def account_detail(request, user_id):
    logger.info('Getting account detail')
    account = get_account(user_id)

    try:
        profile = AccountProfile.objects.get(user_id=user_id)
    except AccountProfile.DoesNotExist:
        profile = None

    account_profiles = AccountProfileOrganization.objects.filter(accountprofile_id=profile.id)

    return render(request, "accounts/account_detail.html", {"account": account, "profile": profile,
                                                            "account_profiles": account_profiles})


@permission_required('core.admin')
def account_add(request):
    logger.info('Adding account')
    if request.method == 'POST':
        account_form = AccountForm(request.POST)

        if account_form.is_valid():
            data = account_form.cleaned_data
            response = add_account(data)

            if response:
                return redirect('account_list')
            else:
                raise SuspiciousOperation

    else:
        account_form = AccountForm()
        return render(request, "accounts/account_add.html", {"account_form": account_form})


@permission_required('core.admin')
def account_update(request, user_id):
    if request.method == 'POST':
        account_form = AccountUpdateForm(request.POST)
        if account_form.is_valid():
            data = account_form.cleaned_data
            response = update_account(data, user_id)

            if response:
                return redirect('account_detail', user_id=user_id)
            else:
                raise SuspiciousOperation

    else:
        account_form = AccountUpdateForm()

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
        qs = IsOrganizationAdmin.filter_queryset_for_user(Organization.objects.all(), request.user, 'name', True)
        profile_form = ProfileFormSet(queryset=AccountProfileOrganization.objects.none(), form_kwargs={"qs": qs})
        return render(request, "accounts/account_profile_add.html", {"user_id": user_id, "profile_form": profile_form})


@permission_required('core.admin')
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
            return render(request, "accounts/account_profile_add.html", {"user_id": user_id,
                                                                         "profile_form": profile_form})

    else:
        qs = Organization.objects.all()
        if not IsGlobalAdmin.has_permission(None, request, None):
            qs = IsOrganizationAdmin.filter_queryset_for_user(qs, request.user, 'name', True)
        profile_form = ProfileFormSet(queryset=AccountProfileOrganization.objects.filter(accountprofile_id=profile.id),
                                      form_kwargs={"qs": qs})

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

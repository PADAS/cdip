import logging

from django.contrib.auth.decorators import permission_required
from django.shortcuts import render, redirect, get_object_or_404
from django.core.exceptions import SuspiciousOperation
from django.forms import modelformset_factory

from cdip_admin import settings
from .forms import AccountForm, AccountUpdateForm, AccountProfileForm, AccountRoleForm
from .utils import get_accounts, get_account, add_account, update_account, get_account_roles, add_account_roles, \
    get_client_roles
from .models import AccountProfile, AccountProfileOrganization

KEYCLOAK_CLIENT = settings.KEYCLOAK_CLIENT_ID

logger = logging.getLogger(__name__)


# Create your views here.
@permission_required('core.admin')
def account_list(request):
    logger.info('Getting account list')
    accounts = get_accounts()
    return render(request, "accounts/account_list.html", {"module": accounts})


@permission_required('core.admin')
def account_detail(request, user_id):
    logger.info('Getting account detail')
    account = get_account(user_id)
    roles = get_account_roles(user_id)

    try:
        profile = AccountProfile.objects.get(user_id=user_id)
    except AccountProfile.DoesNotExist:
        profile = None

    organizations = []

    if profile:
        try:
            for org in profile.organizations.all():
                organizations.append(org.name)
        except profile.DoesNotExist:
            logger.debug('User has no UserProfile')

    return render(request, "accounts/account_detail.html", {"account": account, "profile": profile,
                                                            "organizations": organizations, "roles": roles})


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


# @permission_required('core.admin')
# def account_profile_add(request, user_id):
#     if request.method == 'POST':
#         profile_form = AccountProfileForm(request.POST)
#
#         if profile_form.is_valid():
#             profile_form.save()
#             return redirect('account_detail', user_id=user_id)
#         else:
#             return render(request, "accounts/account_profile_add.html", {"user_id": user_id,
#                                                                          "profile_form": profile_form})
#
#     else:
#         profile_form = AccountProfileForm()
#         profile_form.initial['user_id'] = user_id
#         return render(request, "accounts/account_profile_add.html", {"user_id": user_id, "profile_form": profile_form})

ProfileFormSet = modelformset_factory(AccountProfileOrganization, fields=('organization', 'role'), extra=1)

@permission_required('core.admin')
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
        profile_form = ProfileFormSet(queryset=AccountProfileOrganization.objects.filter(accountprofile_id=profile.id))

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

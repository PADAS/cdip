import logging

from django.contrib.auth.decorators import permission_required
from django.contrib.auth.mixins import PermissionRequiredMixin, LoginRequiredMixin
from django.shortcuts import render, redirect, get_object_or_404
from django.core.exceptions import SuspiciousOperation, PermissionDenied
from django.forms import modelformset_factory
from django.views.generic import ListView, FormView, UpdateView
from django.contrib.auth.models import User, Group

from cdip_admin import settings
from core.enums import RoleChoices, DjangoGroups
from core.permissions import IsOrganizationMember, IsGlobalAdmin
from organizations.models import Organization
from .forms import AccountForm, AccountUpdateForm, AccountProfileForm
from .models import AccountProfile, AccountProfileOrganization
from .utils import add_account

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
    user = User.objects.get(id=user_id)
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

            email = data["email"]
            first_name = data["firstName"]
            last_name = data["firstName"]
            org_id = data["organization"]
            role = data["role"]
            username = email

            try:
                user = User.objects.get(email=email)
                if not user.groups.filter(name=DjangoGroups.ORGANIZATION_MEMBER.value).exists():
                    group_id = Group.objects.get(name=DjangoGroups.ORGANIZATION_MEMBER).id
                    user.groups.add(group_id)

            except User.DoesNotExist:
                # create keycloak user
                response = add_account(data)
                # create django user
                if response:
                    user = User.objects.create(email=email, username=username, first_name=first_name, last_name=last_name)
                    group_id = Group.objects.get(name=DjangoGroups.ORGANIZATION_MEMBER).id
                    user.groups.add(group_id)
                else:
                    raise SuspiciousOperation

            account_profile, created = AccountProfile.objects.get_or_create(user_id=user.id,
                                                                            defaults={'user_username': user.username})
            apo, created = AccountProfileOrganization.objects.get_or_create(accountprofile_id=account_profile.id,
                                                                            organization_id=org_id,
                                                                            role=role)
            return redirect('organizations_detail', module_id=org_id)
        else:
            raise SuspiciousOperation


    def get(self, request, *args, **kwargs):
        form = AccountForm()
        org_id = self.kwargs.get("org_id")
        form.initial["organization"] = org_id
        form.initial["role"] = RoleChoices.VIEWER
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            # can only add if you are an admin of at least one organization
            if not IsOrganizationMember.filter_queryset_for_user(Organization.objects.all(),
                                                                 self.request.user, 'name', True):
                raise PermissionDenied
        return render(request, "accounts/account_add.html", {'form': form, 'org_id': org_id})


class AccountsUpdateView(PermissionRequiredMixin, UpdateView):
    template_name = 'accounts/account_update.html'
    form_class = AccountUpdateForm
    permission_required = 'accounts.change_accountprofile'

    def post(self, request, *args, **kwargs):
        user_id = self.kwargs.get("user_id")
        user = get_object_or_404(User, id=user_id)
        account_form = AccountUpdateForm(request.POST)

        if account_form.is_valid():
            data = account_form.cleaned_data
            user.first_name = data["firstName"]
            user.last_name = data["lastName"]
            user.username = data["username"]
            user.save()
            return redirect('account_detail', user_id=user_id)
        else:
            raise SuspiciousOperation

    def get(self, request, *args, **kwargs):
        account_form = AccountUpdateForm()
        user_id = self.kwargs.get("user_id")
        user = get_object_or_404(User, id=user_id)

        account_form.initial['firstName'] = user.first_name
        account_form.initial['lastName'] = user.last_name
        account_form.initial['username'] = user.username

        return render(request, "accounts/account_update.html", {"account_form": account_form, "user_id": user_id})


class AccountProfileUpdateView(PermissionRequiredMixin, UpdateView):
    template_name = 'accounts/account_profile_update.html'
    form_class = AccountProfileForm
    permission_required = 'accounts.change_accountprofile'

    def post(self, request, *args, **kwargs):
        org_id = self.kwargs.get("org_id")
        user_id = self.kwargs.get("user_id")
        ap = AccountProfile.objects.get(user_id=user_id)
        acos = AccountProfileOrganization.objects.filter(accountprofile_id=ap.id)
        aco = acos.get(organization_id=org_id)
        profile_form = AccountProfileForm(request.POST)

        if profile_form.is_valid():
            data = profile_form.cleaned_data
            aco.role = data["role"]
            aco.save()
            return redirect('organizations_detail', module_id=org_id)
        else:
            raise SuspiciousOperation

    def get(self, request, *args, **kwargs):
        profile_form = AccountProfileForm()
        org_id = self.kwargs.get("org_id")
        user_id = self.kwargs.get("user_id")
        user = get_object_or_404(User, id=user_id)
        org = Organization.objects.get(id=org_id)
        ap = AccountProfile.objects.get(user_id=user_id)
        acos = AccountProfileOrganization.objects.filter(accountprofile_id=ap.id)
        aco = acos.get(organization_id=org_id)

        profile_form.initial['role'] = aco.role
        profile_form.initial['organization'] = aco.organization.id

        return render(request, "accounts/account_profile_update.html", {"profile_form": profile_form,
                                                                        "user": user,
                                                                        "organization": org})

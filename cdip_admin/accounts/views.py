import logging
from django.contrib.auth.decorators import permission_required
from django.contrib.auth.mixins import PermissionRequiredMixin, LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.core.exceptions import SuspiciousOperation, PermissionDenied
from django.urls import reverse
from django.views.generic import ListView, FormView, UpdateView
from django.contrib.auth.models import User
from django_filters.views import FilterView
from django_tables2.views import SingleTableMixin
from cdip_admin import settings
from core.enums import RoleChoices
from core.permissions import IsOrganizationMember, IsGlobalAdmin
from organizations.models import Organization
from .filters import AccountFilter
from .forms import AccountForm, AccountUpdateForm, AccountProfileForm
from .models import AccountProfile, AccountProfileOrganization
from .tables import AccountTable
from .utils import add_or_create_user_in_org

KEYCLOAK_CLIENT = settings.KEYCLOAK_CLIENT_ID

logger = logging.getLogger(__name__)
default_paginate_by = settings.DEFAULT_PAGINATE_BY


def get_accounts_in_user_organization(user):
    """
    Based on a given user, return all user accounts that are members of the same organizations
    regardless of role
    """
    user_orgs = IsOrganizationMember.get_organizations_for_user(user, admin_only=False)
    aco = AccountProfileOrganization.objects.filter(organization__name__in=user_orgs)
    apo_ids = aco.values_list("accountprofile_id", flat=True)
    ap = AccountProfile.objects.filter(id__in=apo_ids)
    accounts = ap.values_list("user_id", flat=True)
    return accounts


class AccountsListView(LoginRequiredMixin, SingleTableMixin, FilterView):
    template_name = "accounts/account_list.html"
    table_class = AccountTable
    paginate_by = default_paginate_by
    filterset_class = AccountFilter
    queryset = User.objects.filter(email__contains="@").order_by("last_name")

    def get_queryset(self):
        qs = super().get_queryset()
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            accounts = get_accounts_in_user_organization(self.request.user)
            qs = qs.filter(id__in=accounts)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["base_url"] = reverse("account_list")
        return context

    def get_template_names(self):
        if self.request.headers.get("HX-Request"):
            return ["accounts/table_partial.html"]
        return super().get_template_names()


@permission_required("accounts.view_accountprofile")
def account_detail(request, user_id):
    logger.info("Getting account detail")
    user = User.objects.get(id=user_id)

    # check that requesting user has permission to view this account
    if not IsGlobalAdmin.has_permission(None, request, None):
        accounts = get_accounts_in_user_organization(request.user)
        if user.id not in accounts:
            raise PermissionDenied

    try:
        profile = AccountProfile.objects.get(user_id=user_id)
        account_profiles = AccountProfileOrganization.objects.filter(
            accountprofile_id=profile.id
        )
    except AccountProfile.DoesNotExist:
        profile = None
        account_profiles = None

    return render(
        request,
        "accounts/account_detail.html",
        {"user": user, "profile": profile, "account_profiles": account_profiles},
    )


class AccountsAddView(LoginRequiredMixin, FormView):
    form_class = AccountForm

    def post(self, request, *args, **kwargs):
        form = AccountForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            role = data.pop("role")
            org_id = data.pop("organization")
            add_or_create_user_in_org(org_id=org_id, role=role, user_data=data)
            return redirect("organizations_detail", module_id=org_id)
        else:
            raise SuspiciousOperation

    def get(self, request, *args, **kwargs):
        form = AccountForm()
        org_id = self.kwargs.get("org_id")
        org = Organization.objects.get(id=org_id)
        form.initial["organization"] = org_id
        form.initial["role"] = RoleChoices.VIEWER
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            # can only add if you are an admin of this organization
            if not IsOrganizationMember.is_object_owner(request.user, org):
                raise PermissionDenied
        return render(
            request, "accounts/account_add.html", {"form": form, "org_id": org_id}
        )


class AccountsUpdateView(PermissionRequiredMixin, UpdateView):
    template_name = "accounts/account_update.html"
    form_class = AccountUpdateForm
    permission_required = "accounts.change_accountprofile"

    def get_object(self):
        user = get_object_or_404(User, id=self.kwargs.get("user_id"))
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            accounts = get_accounts_in_user_organization(self.request.user)
            if user.id not in accounts:
                raise PermissionDenied
        return user

    def get(self, request, *args, **kwargs):
        user = self.get_object()
        account_form = AccountUpdateForm()
        account_form.initial["firstName"] = user.first_name
        account_form.initial["lastName"] = user.last_name
        account_form.initial["username"] = user.username

        is_htmx = request.headers.get("HX-Request")
        if is_htmx:
            self._configure_htmx_helper(account_form, user.id)
            return render(
                request,
                "accounts/account_update_partial.html",
                {"account_form": account_form, "user_id": user.id},
            )
        return render(
            request,
            "accounts/account_update.html",
            {"account_form": account_form, "user_id": user.id},
        )

    def post(self, request, *args, **kwargs):
        user = self.get_object()
        account_form = AccountUpdateForm(request.POST)

        if account_form.is_valid():
            data = account_form.cleaned_data
            user.first_name = data["firstName"]
            user.last_name = data["lastName"]
            user.username = data["username"]
            user.save()
            if request.headers.get("HX-Request"):
                response = HttpResponse(status=204)
                response["HX-Trigger"] = "panelFormSaved"
                return response
            return redirect("account_detail", user_id=user.id)
        else:
            if request.headers.get("HX-Request"):
                self._configure_htmx_helper(account_form, user.id)
                return render(
                    request,
                    "accounts/account_update_partial.html",
                    {"account_form": account_form, "user_id": user.id},
                )
            raise SuspiciousOperation

    @staticmethod
    def _configure_htmx_helper(form, user_id):
        form_action = reverse("account_update", kwargs={"user_id": user_id})
        form.helper.form_action = form_action
        form.helper.inputs = []
        form.helper.attrs = {
            "hx-post": form_action,
            "hx-target": "#slide-panel-body",
            "hx-swap": "innerHTML",
            "novalidate": "",
        }


class AccountProfileUpdateView(PermissionRequiredMixin, UpdateView):
    template_name = "accounts/account_profile_update.html"
    form_class = AccountProfileForm
    permission_required = "accounts.change_accountprofile"

    def post(self, request, *args, **kwargs):
        org_id = self.kwargs.get("org_id")
        user_id = self.kwargs.get("user_id")
        org = Organization.objects.get(id=org_id)

        # Only allow organization owners to change roles
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            if not IsOrganizationMember.is_object_owner(self.request.user, org):
                raise PermissionDenied

        ap = AccountProfile.objects.get(user_id=user_id)
        acos = AccountProfileOrganization.objects.filter(accountprofile_id=ap.id)
        aco = acos.get(organization_id=org_id)
        profile_form = AccountProfileForm(request.POST)

        if profile_form.is_valid():
            data = profile_form.cleaned_data
            aco.role = data["role"]
            aco.save()
            return redirect("organizations_detail", module_id=org_id)
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

        # Only allow organization owners to change roles
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            if not IsOrganizationMember.is_object_owner(self.request.user, org):
                raise PermissionDenied

        profile_form.initial["role"] = aco.role
        profile_form.initial["organization"] = aco.organization.id

        return render(
            request,
            "accounts/account_profile_update.html",
            {"profile_form": profile_form, "user": user, "organization": org},
        )

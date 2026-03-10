from django.contrib.auth.decorators import permission_required, login_required
from django.contrib.auth.mixins import PermissionRequiredMixin, LoginRequiredMixin
from django.contrib.auth.models import User
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.core.exceptions import PermissionDenied
from django.views.decorators.http import require_GET, require_POST
from django_filters.views import FilterView
from django_tables2.views import SingleTableMixin

from cdip_admin import settings
from .forms import OrganizationForm
from .models import Organization
from .filters import OrganizationFilter
from .tables import OrganizationTable
from accounts.models import AccountProfile, AccountProfileOrganization
from accounts.utils import add_or_create_user_in_org
from core.enums import RoleChoices
from core.permissions import IsGlobalAdmin, IsOrganizationMember
from django.views.generic import ListView, UpdateView

default_paginate_by = settings.DEFAULT_PAGINATE_BY


@permission_required("organizations.add_organization", raise_exception=True)
def organizations_add(request):
    if request.method == "POST":
        form = OrganizationForm(request.POST)
        if form.is_valid():
            org = form.save()
            return redirect("organizations_detail", org.id)
    else:
        form = OrganizationForm
    return render(request, "organizations/organizations_add.html", {"form": form})


class OrganizationUpdateView(PermissionRequiredMixin, UpdateView):
    template_name = "organizations/organizations_update.html"
    form_class = OrganizationForm
    model = Organization
    permission_required = "organizations.change_organization"

    def get_object(self):
        organization = get_object_or_404(
            Organization, pk=self.kwargs.get("organization_id")
        )
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            if not IsOrganizationMember.is_object_owner(
                self.request.user, organization
            ):
                raise PermissionDenied
        return organization

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        is_htmx = request.headers.get("HX-Request")
        if is_htmx:
            self._configure_htmx_helper(form, self.object.id)
            return render(
                request,
                "organizations/organizations_update_partial.html",
                {"form": form, "organization": self.object},
            )
        return render(
            request,
            "organizations/organizations_update.html",
            {"form": form},
        )

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        if form.is_valid():
            form.save()
            if request.headers.get("HX-Request"):
                response = HttpResponse(status=204)
                response["HX-Trigger"] = "panelFormSaved"
                return response
            return redirect(
                "organizations_detail",
                module_id=self.object.id,
            )
        else:
            if request.headers.get("HX-Request"):
                self._configure_htmx_helper(form, self.object.id)
                return render(
                    request,
                    "organizations/organizations_update_partial.html",
                    {"form": form, "organization": self.object},
                )
            return self.form_invalid(form)

    def get_success_url(self):
        return reverse(
            "organizations_detail",
            kwargs={"module_id": self.kwargs.get("organization_id")},
        )

    @staticmethod
    def _configure_htmx_helper(form, organization_id):
        form_action = reverse(
            "organizations_update",
            kwargs={"organization_id": organization_id},
        )
        form.helper.form_action = form_action
        form.helper.inputs = []
        form.helper.attrs = {
            "hx-post": form_action,
            "hx-target": "#slide-panel-body",
            "hx-swap": "innerHTML",
            "novalidate": "",
        }


class OrganizationDetailListView(PermissionRequiredMixin, ListView):
    template_name = "organizations/organizations_detail.html"
    context_object_name = "accounts"
    permission_required = "organizations.view_organization"

    def get_queryset(self):
        org = get_object_or_404(Organization, pk=self.kwargs.get("module_id"))
        aco = AccountProfileOrganization.objects.filter(organization__id=org.id)
        apo_ids = aco.values_list("accountprofile_id", flat=True)
        ap = AccountProfile.objects.filter(id__in=apo_ids)
        uids = ap.values_list("user_id", flat=True)
        users = User.objects.filter(id__in=uids)
        accounts = []
        for user in users:
            role = aco.get(accountprofile_id=ap.get(user_id=user.id).id).role
            accounts.append((user, role))
        return accounts

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        org = get_object_or_404(Organization, pk=self.kwargs.get("module_id"))
        is_owner = IsGlobalAdmin.has_permission(
            None, self.request, None
        ) or IsOrganizationMember.is_object_owner(self.request.user, org)
        context["organization"] = org
        context["is_owner"] = is_owner
        return context


class OrganizationsListView(LoginRequiredMixin, SingleTableMixin, FilterView):
    template_name = "organizations/organizations_list.html"
    table_class = OrganizationTable
    paginate_by = default_paginate_by
    filterset_class = OrganizationFilter
    queryset = Organization.objects.get_queryset().order_by("name")

    def get_queryset(self):
        qs = super().get_queryset()
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            return IsOrganizationMember.filter_queryset_for_user(
                qs, self.request.user, "name"
            )
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["base_url"] = reverse("organizations_list")
        return context

    def get_template_names(self):
        if self.request.headers.get("HX-Request"):
            return ["organizations/table_partial.html"]
        return super().get_template_names()


def _check_org_owner(request, organization):
    """Verify the requesting user is a global admin or owner of the organization."""
    if not IsGlobalAdmin.has_permission(None, request, None):
        if not IsOrganizationMember.is_object_owner(request.user, organization):
            raise PermissionDenied


def _org_members_context(organization):
    """Build context for the org members partial template."""
    members = AccountProfileOrganization.objects.filter(
        organization=organization
    ).select_related("accountprofile__user").order_by("accountprofile__user__last_name")
    role_choices = [(tag.value, tag.value) for tag in RoleChoices]
    return {
        "members": members,
        "role_choices": role_choices,
        "organization_id": organization.id,
    }


@login_required
@require_GET
def org_members_list(request, organization_id):
    organization = get_object_or_404(Organization, pk=organization_id)
    _check_org_owner(request, organization)
    context = _org_members_context(organization)
    return render(request, "organizations/org_members_partial.html", context)


@login_required
@require_POST
def org_members_add(request, organization_id):
    organization = get_object_or_404(Organization, pk=organization_id)
    _check_org_owner(request, organization)

    email = request.POST.get("email", "").strip()
    role = request.POST.get("role", RoleChoices.VIEWER.value)

    context = _org_members_context(organization)

    if not email:
        context["add_error"] = "Email address is required."
        return render(request, "organizations/org_members_partial.html", context)

    try:
        add_or_create_user_in_org(
            org_id=organization_id,
            role=role,
            user_data={"email": email, "first_name": "", "last_name": ""},
        )
    except Exception as e:
        context = _org_members_context(organization)
        context["add_error"] = f"Error adding member: {e}"
        return render(request, "organizations/org_members_partial.html", context)

    context = _org_members_context(organization)
    context["add_success"] = f"{email} added to organization."
    return render(request, "organizations/org_members_partial.html", context)


@login_required
@require_POST
def org_members_remove(request, organization_id, member_id):
    organization = get_object_or_404(Organization, pk=organization_id)
    _check_org_owner(request, organization)

    membership = get_object_or_404(
        AccountProfileOrganization, pk=member_id, organization=organization
    )
    membership.delete()

    context = _org_members_context(organization)
    return render(request, "organizations/org_members_partial.html", context)


@login_required
@require_POST
def org_members_change_role(request, organization_id, member_id):
    organization = get_object_or_404(Organization, pk=organization_id)
    _check_org_owner(request, organization)

    membership = get_object_or_404(
        AccountProfileOrganization, pk=member_id, organization=organization
    )
    new_role = request.POST.get("role", "").strip()
    valid_roles = [tag.value for tag in RoleChoices]
    if new_role in valid_roles:
        membership.role = new_role
        membership.save()

    context = _org_members_context(organization)
    return render(request, "organizations/org_members_partial.html", context)

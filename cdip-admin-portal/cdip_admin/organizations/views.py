from django.contrib.auth.decorators import permission_required
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from rest_framework import permissions
from django.core.exceptions import PermissionDenied

from .forms import OrganizationForm
from .models import Organization
from accounts.models import AccountProfile, AccountProfileOrganization
from core.permissions import IsGlobalAdmin, IsOrganizationAdmin
from django.views.generic import ListView, DetailView, UpdateView


@permission_required('organizations.add_organization', raise_exception=True)
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
    template_name = 'organizations/organizations_update.html'
    form_class = OrganizationForm
    model = Organization
    permission_required = 'organizations.change_organization'

    def can_update(self, obj):
        account_profile_id = AccountProfile.objects.only('id').get(user_id=self.request.user.username).id
        account_organizations = AccountProfileOrganization.objects.filter(accountprofile_id=account_profile_id)
        role = account_organizations.only('role').get(organization_id=obj.id).role
        if role == 'admin':
            return True
        return False

    def get_object(self):
        organization = get_object_or_404(Organization, pk=self.kwargs.get("organization_id"))
        if not self.can_update(organization):
            raise PermissionDenied
        return organization

    def get_success_url(self):
        return reverse('organizations_detail', kwargs={'module_id': self.kwargs.get("organization_id")})


class OrganizationDetailView(PermissionRequiredMixin, DetailView):
    template_name = 'organizations/organizations_detail.html'
    model = Organization
    permission_required = 'organizations.view_organization'

    def get_object(self):
        return get_object_or_404(Organization, pk=self.kwargs.get("module_id"))


def get_organizations_for_user(user):
    organizations = []
    account_profiles = AccountProfile.objects.filter(user_id=user.username)
    for account in account_profiles:
        for organization in account.organizations.values_list('name', flat=True):
            organizations.append(organization)
    return organizations


class OrganizationsListView(ListView):
    template_name = 'organizations/organizations_list.html'
    queryset = Organization.objects.get_queryset().order_by('name')
    context_object_name = 'organizations'

    def get_queryset(self):
        qs = super(OrganizationsListView, self).get_queryset()
        if not self.request.user.groups.values_list('name', flat=True).filter(name='GlobalAdmin').exists():
            return self.filter_queryset_for_user(qs, self.request.user)
        else:
            return qs

    def filter_queryset_for_user(self, qs, user):
        organizations = get_organizations_for_user(user)
        return qs.filter(name__in=organizations)





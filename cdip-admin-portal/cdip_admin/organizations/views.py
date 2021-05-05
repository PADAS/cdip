from django.contrib.auth.decorators import permission_required
from django.contrib.auth.mixins import PermissionRequiredMixin, LoginRequiredMixin
from django.contrib.auth.models import User
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.core.exceptions import PermissionDenied

from .forms import OrganizationForm
from .models import Organization
from accounts.models import AccountProfile, AccountProfileOrganization
from core.permissions import IsGlobalAdmin, IsOrganizationMember
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

    def get_object(self):
        organization = get_object_or_404(Organization, pk=self.kwargs.get("organization_id"))
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            if not IsOrganizationMember.is_object_owner(self.request.user, organization):
                raise PermissionDenied
        return organization

    def get_success_url(self):
        return reverse('organizations_detail', kwargs={'module_id': self.kwargs.get("organization_id")})


class OrganizationDetailListView(PermissionRequiredMixin, ListView):
    template_name = 'organizations/organizations_detail.html'
    context_object_name = 'accounts'
    permission_required = 'organizations.view_organization'

    def get_queryset(self):
        org = get_object_or_404(Organization, pk=self.kwargs.get("module_id"))
        aco = AccountProfileOrganization.objects.filter(organization__id=org.id)
        apo_ids = aco.values_list('accountprofile_id', flat=True)
        ap = AccountProfile.objects.filter(id__in=apo_ids)
        uids = ap.values_list('user_id', flat=True)
        users = User.objects.filter(username__in=uids)
        accounts = []
        for user in users:
            role = aco.get(accountprofile_id=ap.get(user_id=user.username).id).role
            accounts.append((user, role))
        return accounts

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        org = get_object_or_404(Organization, pk=self.kwargs.get("module_id"))
        can_invite = IsGlobalAdmin.has_permission(None, self.request, None) or \
                     IsOrganizationMember.is_object_owner(self.request.user, org)
        context['organization'] = org
        context['can_invite'] = can_invite
        return context


class OrganizationsListView(LoginRequiredMixin, ListView):
    template_name = 'organizations/organizations_list.html'
    queryset = Organization.objects.get_queryset().order_by('name')
    context_object_name = 'organizations'

    def get_queryset(self):
        qs = super(OrganizationsListView, self).get_queryset()
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            return IsOrganizationMember.filter_queryset_for_user(qs, self.request.user, 'name')
        else:
            return qs







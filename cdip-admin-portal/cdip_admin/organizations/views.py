from django.contrib.auth.decorators import permission_required
from django.shortcuts import render, get_object_or_404, redirect

from .forms import OrganizationForm
from .models import Organization
from accounts.models import AccountProfile
from core.permissions import IsGlobalAdmin, IsOrganizationAdmin
from django.views.generic import ListView


@permission_required('core.admin')
def organizations_add(request):
    if request.method == "POST":
        form = OrganizationForm(request.POST)
        if form.is_valid():
            org = form.save()
            return redirect("organizations_detail", org.id)
    else:
        form = OrganizationForm
    return render(request, "organizations/organizations_add.html", {"form": form})


# Create your views here.
@permission_required('core.admin')
def organizations_detail(request, module_id):
    organization = get_object_or_404(Organization, pk=module_id)
    return render(request, "organizations/organizations_detail.html", {"organization": organization})


def get_organizations_for_user(user):
    organizations = []
    account_profiles = AccountProfile.objects.filter(user_id=user.username)
    for account in account_profiles:
        for organization in account.organizations.values_list('name', flat=True):
            organizations.append(organization)
    return organizations


class OrganizationsListView(ListView):
    permission_classes = ([IsGlobalAdmin | IsOrganizationAdmin])
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


@permission_required('core.admin')
def organizations_update(request, organization_id):
    organization = get_object_or_404(Organization, id=organization_id)
    form = OrganizationForm(request.POST or None, instance=organization)
    if form.is_valid():
        form.save()
        return redirect("organizations_detail", organization_id)
    return render(request, "organizations/organizations_update.html", {"form": form})


from django.contrib.auth.decorators import permission_required
from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import FormView

from integrations.models import DeviceGroup
from .forms import OrganizationForm
from .models import Organization, UserProfile


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


@permission_required('core.admin')
def organizations_list(request):
    organizations = Organization.objects.all()
    return render(request, "organizations/organizations_list.html",
                  {"organizations": organizations})


@permission_required('core.admin')
def organizations_update(request, organization_id):
    organization = get_object_or_404(Organization, id=organization_id)
    form = OrganizationForm(request.POST or None, instance=organization)
    if form.is_valid():
        form.save()
        return redirect("organizations_detail", organization_id)
    return render(request, "organizations/organizations_update.html", {"form": form})


from django.contrib.auth.decorators import permission_required
from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import FormView

from .models import Organization, UserProfile


# Create your views here.
@permission_required('core.admin')
def organizations_detail(request, module_id):
    organization = get_object_or_404(Organization, pk=module_id)
    return render(request, "organizations/organizations_detail.html", {"module": organization})


@permission_required('core.admin')
def organizations_list(request):
    organizations = Organization.objects.all()
    return render(request, "organizations/organizations_list.html",
                  {"organizations": organizations})


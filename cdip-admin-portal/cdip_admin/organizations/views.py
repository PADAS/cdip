from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import FormView

from .models import Organization


# Create your views here.
def organizations_detail(request, module_id):
    organization = get_object_or_404(Organization, pk=module_id)
    return render(request, "organizations/organizations_detail.html", {"module": organization})


def organizations_list(request):
    if request.user.has_perm('organizations.view_organization'):

        profile = request.user.user_profile

        return render(request, "organizations/organizations_list.html",
                      {"organizations": profile.organizations.all()})
    else:
        return redirect("welcome")


from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import FormView

from .models import Organization, UserProfile


# Create your views here.
def organizations_detail(request, module_id):
    organization = get_object_or_404(Organization, pk=module_id)
    return render(request, "organizations/organizations_detail.html", {"module": organization})


def organizations_list(request):
    if request.user.has_perm('organizations.view_organization'):

        organizations = Organization.objects.filter(user_profile__user=request.user)
        return render(request, "organizations/organizations_list.html",
                      {"organizations": organizations})
    else:
        return redirect("welcome")


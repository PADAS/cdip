from django.shortcuts import render, get_object_or_404, redirect
from django.forms import modelform_factory
from django.contrib.auth.decorators import user_passes_test

from .models import InboundIntegrationType


# Create your views here.
def detail(request, module_id):
    integration_module = get_object_or_404(InboundIntegrationType, pk=module_id)
    return render(request, "integrations/detail.html", {"module": integration_module})


def integrations_list(request):
    if request.user.has_perm("integrations.view_inboundintegrationtype"):
        return render(request, "integrations/integrations_list.html",
                      {"integrations": InboundIntegrationType.objects.all()})
    else:
        return redirect("welcome")


IntegrationForm = modelform_factory(InboundIntegrationType, exclude=[])


def new(request):
    if request.method == "POST":
        form = IntegrationForm(request.Post)
        if form.is_valid():
            form.save()
            return redirect("welcome")
    else:
        form = IntegrationForm
    return render(request, "integrations/new.html", {"form": form})

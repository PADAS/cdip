from django.shortcuts import render, get_object_or_404, redirect
from django.forms import modelform_factory

from .models import InboundIntegrationType


# Create your views here.
def detail(request, module_id):
    integration_module = get_object_or_404(InboundIntegrationType, pk=module_id)
    return render(request, "integrations/detail.html", {"module": integration_module})


def integrations_list(request):
    return render(request, "integrations/integrations_list.html",
                  {"integrations": InboundIntegrationType.objects.all()})


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


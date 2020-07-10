from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.shortcuts import render, get_object_or_404, redirect
from django.forms import modelform_factory
from django.contrib.auth.decorators import user_passes_test
from django.views.generic import ListView

from .models import InboundIntegrationType


# Create your views here.
def detail(request, module_id):
    integration_module = get_object_or_404(InboundIntegrationType, pk=module_id)
    return render(request, "integrations/detail.html", {"module": integration_module})


class IntegrationsList(ListView):
    template_name = 'integrations/integrations_list.html'
    queryset = InboundIntegrationType.objects.get_queryset().order_by('name')
    context_object_name = 'integrations'
    paginate_by = 2


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

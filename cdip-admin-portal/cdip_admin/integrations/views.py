from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.shortcuts import render, get_object_or_404, redirect
from django.forms import modelform_factory
from django.contrib.auth.decorators import user_passes_test
from django.views.generic import ListView

from .models import InboundIntegrationType, OutboundIntegrationType\
    , InboundIntegrationConfiguration, OutboundIntegrationConfiguration


###
# Inbound Integration Type Methods/Classes
###
def inbound_integration_type_detail(request, module_id):
    integration_module = get_object_or_404(InboundIntegrationType, pk=module_id)
    return render(request, "integrations/inbound_integration_type_detail.html", {"module": integration_module})


class InboundIntegrationTypeList(ListView):
    template_name = 'integrations/inbound_integration_type_list.html'
    queryset = InboundIntegrationType.objects.get_queryset().order_by('name')
    context_object_name = 'integrations'
    paginate_by = 2


###
# Outbound Integration Type Methods/Classes
###
def outbound_integration_type_detail(request, module_id):
    integration_module = get_object_or_404(OutboundIntegrationType, pk=module_id)
    return render(request, "integrations/outbound_integration_type_detail.html", {"module": integration_module})


class OutboundIntegrationTypeList(ListView):
    template_name = 'integrations/outbound_integration_type_list.html'
    queryset = OutboundIntegrationType.objects.get_queryset().order_by('name')
    context_object_name = 'integrations'
    paginate_by = 2


###
# Inbound Integration Configuration Methods/Classes
###
def inbound_integration_configuration_detail(request, module_id):
    integration_module = get_object_or_404(InboundIntegrationConfiguration, pk=module_id)
    return render(request, "integrations/inbound_integration_configuration_detail.html", {"module": integration_module})


class InboundIntegrationConfigurationList(ListView):
    template_name = 'integrations/inbound_integration_configuration_list.html'
    queryset = InboundIntegrationConfiguration.objects.get_queryset().order_by('id')
    context_object_name = 'integrations'
    paginate_by = 2


InboundIntegrationForm = modelform_factory(InboundIntegrationConfiguration, exclude=['id'])


def inbound_integration_configuration_add(request):
    if request.method == "POST":
        form = InboundIntegrationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("welcome")
    else:
        form = InboundIntegrationForm
    return render(request, "integrations/inbound_integration_configuration_add.html", {"form": form})


###
# Outbound Integration Configuration Methods/Classes
###
def outbound_integration_configuration_detail(request, module_id):
    integration_module = get_object_or_404(OutboundIntegrationConfiguration, pk=module_id)
    return render(request, "integrations/outbound_integration_configuration_detail.html",
                  {"module": integration_module})


class OutboundIntegrationConfigurationList(ListView):
    template_name = 'integrations/outbound_integration_configuration_list.html'
    queryset = OutboundIntegrationConfiguration.objects.get_queryset().order_by('id')
    context_object_name = 'integrations'
    paginate_by = 2


OutboundIntegrationForm = modelform_factory(OutboundIntegrationConfiguration, exclude=['id'])


def outbound_integration_configuration_add(request):
    if request.method == "POST":
        form = OutboundIntegrationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("welcome")
    else:
        form = OutboundIntegrationForm
    return render(request, "integrations/outbound_integration_configuration_add.html", {"form": form})

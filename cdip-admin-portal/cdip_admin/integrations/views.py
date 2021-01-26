from django.contrib.auth.decorators import permission_required
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView
from django_filters.views import FilterView
from django_tables2.views import SingleTableMixin

import logging

from cdip_admin import settings
from .forms import InboundIntegrationConfigurationForm, OutboundIntegrationConfigurationForm
from .filters import DeviceStateFilter
from .models import InboundIntegrationType, OutboundIntegrationType \
    , InboundIntegrationConfiguration, OutboundIntegrationConfiguration, Device, DeviceState
from .tables import DeviceStateTable

logger = logging.getLogger(__name__)
default_paginate_by = settings.DEFAULT_PAGINATE_BY


###
# Device Methods/Classes
###
@permission_required('core.admin')
def device_detail(request, module_id):
    logger.info(f"Request for Device: {module_id}")
    device = get_object_or_404(Device, pk=module_id)
    return render(request, "integrations/device_detail.html", {"device": device})


class DeviceList(PermissionRequiredMixin, ListView):
    permission_required = 'core.admin'
    template_name = 'integrations/device_list.html'
    queryset = Device.objects.get_queryset().order_by('inbound_configuration__owner__name',
                                                      'inbound_configuration__type__name')
    context_object_name = 'devices'
    paginate_by = default_paginate_by


###
# DeviceState Methods/Classes
###
class DeviceStateList(PermissionRequiredMixin, SingleTableMixin, FilterView):
    permission_required = 'core.admin'
    model = DeviceState
    table_class = DeviceStateTable
    template_name = 'integrations/device_state_list.html'
    filterset_class = DeviceStateFilter


###
# Inbound Integration Type Methods/Classes
###
@permission_required('core.admin')
def inbound_integration_type_detail(request, module_id):
    logger.info(f"Request for Integration Type: {module_id}")
    integration_module = get_object_or_404(InboundIntegrationType, pk=module_id)
    return render(request, "integrations/inbound_integration_type_detail.html", {"module": integration_module})


class InboundIntegrationTypeList(PermissionRequiredMixin, ListView):
    permission_required = 'core.admin'
    template_name = 'integrations/inbound_integration_type_list.html'
    queryset = InboundIntegrationType.objects.get_queryset().order_by('name')
    context_object_name = 'integrations'
    paginate_by = default_paginate_by


###
# Outbound Integration Type Methods/Classes
###
@permission_required('core.admin')
def outbound_integration_type_detail(request, module_id):
    integration_module = get_object_or_404(OutboundIntegrationType, pk=module_id)
    return render(request, "integrations/outbound_integration_type_detail.html", {"module": integration_module})


class OutboundIntegrationTypeList(PermissionRequiredMixin, ListView):
    permission_required = 'core.admin'
    template_name = 'integrations/outbound_integration_type_list.html'
    queryset = OutboundIntegrationType.objects.get_queryset().order_by('name')
    context_object_name = 'integrations'
    paginate_by = default_paginate_by


###
# Inbound Integration Configuration Methods/Classes
###
@permission_required('core.admin')
def inbound_integration_configuration_detail(request, module_id):
    integration_module = get_object_or_404(InboundIntegrationConfiguration, pk=module_id)
    return render(request, "integrations/inbound_integration_configuration_detail.html", {"module": integration_module})


class InboundIntegrationConfigurationList(PermissionRequiredMixin, ListView):
    permission_required = 'core.admin'
    template_name = 'integrations/inbound_integration_configuration_list.html'
    queryset = InboundIntegrationConfiguration.objects.get_queryset().order_by('id')
    context_object_name = 'integrations'
    paginate_by = default_paginate_by


@permission_required('core.admin')
def inbound_integration_configuration_add(request):
    if request.method == "POST":
        form = InboundIntegrationConfigurationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("welcome")
    else:
        form = InboundIntegrationConfigurationForm
    return render(request, "integrations/inbound_integration_configuration_add.html", {"form": form})


###
# Outbound Integration Configuration Methods/Classes
###
@permission_required('core.admin')
def outbound_integration_configuration_detail(request, module_id):
    integration_module = get_object_or_404(OutboundIntegrationConfiguration, pk=module_id)
    return render(request, "integrations/outbound_integration_configuration_detail.html",
                  {"module": integration_module})


class OutboundIntegrationConfigurationList(PermissionRequiredMixin, ListView):
    permission_required = 'core.admin'
    template_name = 'integrations/outbound_integration_configuration_list.html'
    queryset = OutboundIntegrationConfiguration.objects.get_queryset().order_by('id')
    context_object_name = 'integrations'
    paginate_by = default_paginate_by


@permission_required('core.admin')
def outbound_integration_configuration_add(request):
    if request.method == "POST":
        form = OutboundIntegrationConfigurationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("welcome")
    else:
        form = OutboundIntegrationConfigurationForm
    return render(request, "integrations/outbound_integration_configuration_add.html", {"form": form})

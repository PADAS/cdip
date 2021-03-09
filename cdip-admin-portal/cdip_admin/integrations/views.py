from django.contrib.auth.decorators import permission_required
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView
from django_filters.views import FilterView
from django_tables2.views import SingleTableMixin

import logging

from cdip_admin import settings
from .forms import InboundIntegrationConfigurationForm, OutboundIntegrationConfigurationForm, DeviceGroupForm, \
    DeviceGroupManagementForm, InboundIntegrationTypeForm
from .filters import DeviceStateFilter
from .models import InboundIntegrationType, OutboundIntegrationType \
    , InboundIntegrationConfiguration, OutboundIntegrationConfiguration, Device, DeviceState, DeviceGroup
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
# Device Group Methods/Classes
###
@permission_required('core.admin')
def device_group_detail(request, module_id):
    logger.info(f"Request for Device Group: {module_id}")
    device_group = get_object_or_404(DeviceGroup, pk=module_id)
    return render(request, "integrations/device_group_detail.html", {"device_group": device_group})


class DeviceGroupList(PermissionRequiredMixin, ListView):
    permission_required = 'core.admin'
    template_name = 'integrations/device_group_list.html'
    queryset = DeviceGroup.objects.get_queryset().order_by('name')
    context_object_name = 'device_groups'
    paginate_by = default_paginate_by


@permission_required('core.admin')
def device_group_add(request):
    if request.method == "POST":
        form = DeviceGroupForm(request.POST, user=request.user)
        if form.is_valid():
            config = form.save()
            return redirect("device_group_detail", config.id)
    else:
        form = DeviceGroupForm(user=request.user)
    return render(request, "integrations/device_group_add.html", {"form": form})


@permission_required('core.admin')
def device_group_update(request, device_group_id):
    device_group = get_object_or_404(DeviceGroup, id=device_group_id)
    form = DeviceGroupForm(request.POST or None, instance=device_group, user=request.user)
    if form.is_valid():
        form.save()
        return redirect("device_group_detail", device_group_id)
    return render(request, "integrations/device_group_update.html", {"form": form})


@permission_required('core.admin')
def device_group_management_update(request, device_group_id):
    device_group = get_object_or_404(DeviceGroup, id=device_group_id)
    form = DeviceGroupManagementForm(request.POST or None, instance=device_group)

    if form.is_valid():
        form.save()
        return redirect("device_group_detail", device_group_id)
    return render(request, "integrations/device_group_update.html", {"form": form})


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


@permission_required('core.admin')
def inbound_integration_type_add(request):
    if request.method == "POST":
        form = InboundIntegrationTypeForm(request.POST)
        if form.is_valid():
            integration_type = form.save()
            return redirect("inbound_integration_type_detail", integration_type.id)
            #return redirect("inbound_integration_type_update", integration_type.id)
    else:
        form = InboundIntegrationTypeForm
    return render(request, "integrations/inbound_integration_type_add.html", {"form": form})


@permission_required('core.admin')
def inbound_integration_type_update(request, inbound_integration_type_id):
    integration_type = get_object_or_404(InboundIntegrationType, id=inbound_integration_type_id)
    form = InboundIntegrationTypeForm(request.POST or None, instance=integration_type)
    if form.is_valid():
        form.save()
        return redirect("inbound_integration_type_detail", inbound_integration_type_id)
    return render(request, "integrations/inbound_integration_type_update.html", {"form": form})


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
            config: InboundIntegrationConfiguration = form.save()
            if not config.default_devicegroup:
                name = config.type.name + " - Default"
                device_group = DeviceGroup.objects.create(owner_id=config.owner.id, name=name)
                config.default_devicegroup = device_group
                config.save()
            else:
                device_group = config.default_devicegroup
            return redirect("device_group_update", device_group.id)
    else:
        form = InboundIntegrationConfigurationForm
    return render(request, "integrations/inbound_integration_configuration_add.html", {"form": form})


@permission_required('core.admin')
def inbound_integration_configuration_update(request, configuration_id):
    configuration = get_object_or_404(InboundIntegrationConfiguration, id=configuration_id)
    form = InboundIntegrationConfigurationForm(request.POST or None, instance=configuration)
    if form.is_valid():
        form.save()
        return redirect("inbound_integration_configuration_detail", configuration_id)
    return render(request, "integrations/inbound_integration_configuration_update.html", {"form": form})


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
            config = form.save()
            return redirect("outbound_integration_configuration_detail", config.id)
    else:
        form = OutboundIntegrationConfigurationForm
    return render(request, "integrations/outbound_integration_configuration_add.html", {"form": form})


@permission_required('core.admin')
def outbound_integration_configuration_update(request, configuration_id):
    configuration = get_object_or_404(OutboundIntegrationConfiguration, id=configuration_id)
    form = OutboundIntegrationConfigurationForm(request.POST or None, instance=configuration)
    if form.is_valid():
        form.save()
        return redirect("outbound_integration_configuration_detail", configuration_id)
    return render(request, "integrations/outbound_integration_configuration_update.html", {"form": form})

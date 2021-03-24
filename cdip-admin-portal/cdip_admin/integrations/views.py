from django.contrib.auth.decorators import permission_required
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, DetailView
from django_filters.views import FilterView
from django_tables2.views import SingleTableMixin
from django.urls import reverse

import logging

from cdip_admin import settings
from .forms import InboundIntegrationConfigurationForm, OutboundIntegrationConfigurationForm, DeviceGroupForm, \
    DeviceGroupManagementForm, InboundIntegrationTypeForm, OutboundIntegrationTypeForm
from .filters import DeviceStateFilter, DeviceGroupFilter, DeviceFilter
from .models import InboundIntegrationType, OutboundIntegrationType \
    , InboundIntegrationConfiguration, OutboundIntegrationConfiguration, Device, DeviceGroup
from .tables import DeviceStateTable, DeviceGroupTable, DeviceTable, InboundIntegrationConfigurationTable, \
    OutboundIntegrationConfigurationTable

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


class DeviceList(PermissionRequiredMixin, SingleTableMixin, FilterView):
    permission_required = 'core.admin'
    template_name = 'integrations/device_list.html'
    table_class = DeviceTable
    paginate_by = default_paginate_by
    filterset_class = DeviceFilter

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        base_url = reverse('device_list')
        context["base_url"] = base_url
        return context


###
# Device Group Methods/Classes
###
class DeviceGroupList(PermissionRequiredMixin, SingleTableMixin, FilterView):
    permission_required = 'core.admin'
    template_name = 'integrations/device_group_list.html'
    table_class = DeviceGroupTable
    paginate_by = default_paginate_by
    filterset_class = DeviceGroupFilter

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        base_url = reverse('device_group_list')
        context["base_url"] = base_url
        return context


class DeviceGroupDetail(PermissionRequiredMixin, SingleTableMixin, DetailView):
    permission_required = 'core.admin'
    template_name = 'integrations/device_group_detail.html'
    model = DeviceGroup
    table_class = DeviceTable
    paginate_by = default_paginate_by

    def get_object(self):
        return get_object_or_404(DeviceGroup, pk=self.kwargs.get("module_id"))

    def get_table_data(self):
        return self.get_object().devices

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        base_url = reverse('device_list')
        context["base_url"] = base_url
        return context


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
    table_class = DeviceStateTable
    template_name = 'integrations/device_state_list.html'
    paginate_by = default_paginate_by
    filterset_class = DeviceStateFilter

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        base_url = reverse('device_list')
        context["base_url"] = base_url
        return context


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


@permission_required('core.admin')
def outbound_integration_type_add(request):
    if request.method == "POST":
        form = OutboundIntegrationTypeForm(request.POST)
        if form.is_valid():
            integration_type = form.save()
            return redirect("outbound_integration_type_detail", integration_type.id)
    else:
        form = OutboundIntegrationTypeForm
    return render(request, "integrations/outbound_integration_type_add.html", {"form": form})


@permission_required('core.admin')
def outbound_integration_type_update(request, outbound_integration_type_id):
    integration_type = get_object_or_404(OutboundIntegrationType, id=outbound_integration_type_id)
    form = OutboundIntegrationTypeForm(request.POST or None, instance=integration_type)
    if form.is_valid():
        form.save()
        return redirect("outbound_integration_type_detail", outbound_integration_type_id)
    return render(request, "integrations/outbound_integration_type_update.html", {"form": form})


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


class InboundIntegrationConfigurationList(PermissionRequiredMixin, SingleTableMixin, ListView):
    permission_required = 'core.admin'
    table_class = InboundIntegrationConfigurationTable
    template_name = 'integrations/inbound_integration_configuration_list.html'
    queryset = InboundIntegrationConfiguration.objects.get_queryset().order_by('id')
    paginate_by = default_paginate_by

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        base_url = reverse('inbound_integration_configuration_list')
        context["base_url"] = base_url
        return context


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


class OutboundIntegrationConfigurationList(PermissionRequiredMixin, SingleTableMixin, ListView):
    permission_required = 'core.admin'
    table_class = OutboundIntegrationConfigurationTable
    template_name = 'integrations/outbound_integration_configuration_list.html'
    queryset = OutboundIntegrationConfiguration.objects.get_queryset().order_by('id')
    paginate_by = default_paginate_by

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        base_url = reverse('outbound_integration_configuration_list')
        context["base_url"] = base_url
        return context


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

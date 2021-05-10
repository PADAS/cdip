import base64

import requests as requests
from django.contrib.auth.decorators import permission_required
from django.contrib.auth.mixins import PermissionRequiredMixin, LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, DetailView, UpdateView, FormView
from django_filters.views import FilterView
from django_tables2.views import SingleTableMixin
from django.urls import reverse

import logging

import random

from rest_framework.utils import json

from cdip_admin import settings
from core.permissions import IsGlobalAdmin, IsOrganizationMember
from organizations.models import Organization
from .forms import InboundIntegrationConfigurationForm, OutboundIntegrationConfigurationForm, DeviceGroupForm, \
    DeviceGroupManagementForm, InboundIntegrationTypeForm, OutboundIntegrationTypeForm, BridgeIntegrationForm
from .filters import DeviceStateFilter, DeviceGroupFilter, DeviceFilter
from .models import InboundIntegrationType, OutboundIntegrationType \
    , InboundIntegrationConfiguration, OutboundIntegrationConfiguration, Device, DeviceGroup, BridgeIntegration
from .tables import DeviceStateTable, DeviceGroupTable, DeviceTable, InboundIntegrationConfigurationTable, \
    OutboundIntegrationConfigurationTable, BridgeIntegrationTable

logger = logging.getLogger(__name__)
default_paginate_by = settings.DEFAULT_PAGINATE_BY

KONG_PROXY_URL = settings.KONG_PROXY_URL

def random_string(n=4):
    return ''.join(random.sample([chr(x) for x in range(97, 97+26)], n))

###
# Device Methods/Classes
###
@permission_required('integrations.view_device')
def device_detail(request, module_id):
    logger.info(f"Request for Device: {module_id}")
    device = get_object_or_404(Device, pk=module_id)
    return render(request, "integrations/device_detail.html", {"device": device})


class DeviceList(LoginRequiredMixin, SingleTableMixin, FilterView):
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
class DeviceGroupListView(LoginRequiredMixin, SingleTableMixin, FilterView):
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
    template_name = 'integrations/device_group_detail.html'
    model = DeviceGroup
    table_class = DeviceTable
    paginate_by = default_paginate_by
    permission_required = 'integrations.view_devicegroup'

    def get_object(self):
        return get_object_or_404(DeviceGroup, pk=self.kwargs.get("module_id"))

    def get_table_data(self):
        return self.get_object().devices

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        base_url = reverse('device_list')
        context["base_url"] = base_url
        return context


def filter_device_group_form_fields(form, user):
    # owner restricted to admin role
    if form.fields.get('owner'):
        form.fields['owner'].queryset = IsOrganizationMember.filter_queryset_for_user(form.fields['owner'].queryset,
                                                                                      user,
                                                                                      'name',
                                                                                      True)
    # destinations open to viewer roles
    if form.fields.get('destinations'):
        des_qs = form.fields['destinations'].queryset
        org_qs = Organization.objects.filter(id__in=des_qs.values_list('owner', flat=True))
        org_qs = IsOrganizationMember.filter_queryset_for_user(org_qs, user, 'name')
        form.fields['destinations'].queryset = des_qs.filter(owner__in=org_qs)

    if form.fields.get('devices'):
        dev_qs = form.fields['devices'].queryset
        org_qs = Organization.objects.filter(id__in=dev_qs.values_list('inbound_configuration__owner', flat=True))
        org_qs = IsOrganizationMember.filter_queryset_for_user(org_qs, user, 'name')
        form.fields['devices'].queryset = dev_qs.filter(inbound_configuration__owner__in=org_qs)
    return form


class DeviceGroupAddView(PermissionRequiredMixin, FormView):
    template_name = 'integrations/device_group_add.html'
    form_class = DeviceGroupForm
    model = DeviceGroup
    permission_required = 'integrations.add_devicegroup'

    def post(self, request, *args, **kwargs):
        form = DeviceGroupForm(request.POST)
        if form.is_valid():
            config = form.save()
            return redirect("device_group_detail", config.id)

    def get_form(self, form_class=None):
        form = DeviceGroupForm()
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            # can only add if you are an admin of at least one organization
            if not IsOrganizationMember.filter_queryset_for_user(Organization.objects.all(),
                                                                 self.request.user, 'name', admin_only=True):
                raise PermissionDenied
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            form = filter_device_group_form_fields(form, self.request.user)
        return form


class DeviceGroupUpdateView(PermissionRequiredMixin, UpdateView):
    template_name = 'integrations/device_group_update.html'
    form_class = DeviceGroupForm
    model = DeviceGroup
    permission_required = 'integrations.change_devicegroup'

    def get(self, request, *args, **kwargs):
        form_class = self.get_form_class()
        self.object = self.get_object()
        form = form_class(instance=self.object)
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            form = filter_device_group_form_fields(form, self.request.user)
        return self.render_to_response(self.get_context_data(form=form))

    def get_object(self):
        device_group = get_object_or_404(DeviceGroup, pk=self.kwargs.get("device_group_id"))
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            if not IsOrganizationMember.is_object_owner(self.request.user, device_group.owner):
                raise PermissionDenied
        return device_group

    def get_success_url(self):
        return reverse('device_group_detail', kwargs={'module_id': self.kwargs.get("device_group_id")})


class DeviceGroupManagementUpdateView(LoginRequiredMixin, UpdateView):
    template_name = 'integrations/device_group_update.html'
    form_class = DeviceGroupManagementForm
    model = DeviceGroup

    def get_object(self):
        device_group = get_object_or_404(DeviceGroup, pk=self.kwargs.get("device_group_id"))
        return device_group

    def get(self, request, *args, **kwargs):
        form_class = self.get_form_class()
        self.object = self.get_object()
        form = form_class(instance=self.object)
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            form = filter_device_group_form_fields(form, self.request.user)
        return self.render_to_response(self.get_context_data(form=form))

    def get_success_url(self):
        return reverse('device_group_detail', kwargs={'module_id': self.kwargs.get("device_group_id")})


###
# DeviceState Methods/Classes
###

class DeviceStateList(LoginRequiredMixin, SingleTableMixin, FilterView):
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
@permission_required('integrations.view_inboundintegrationtype', raise_exception=True)
def inbound_integration_type_detail(request, module_id):
    logger.info(f"Request for Integration Type: {module_id}")
    integration_module = get_object_or_404(InboundIntegrationType, pk=module_id)
    return render(request, "integrations/inbound_integration_type_detail.html", {"module": integration_module})


@permission_required('integrations.add_inboundintegrationtype', raise_exception=True)
def inbound_integration_type_add(request):
    if request.method == "POST":
        form = InboundIntegrationTypeForm(request.POST)
        if form.is_valid():
            integration_type = form.save()
            return redirect("inbound_integration_type_detail", integration_type.id)
    else:
        form = InboundIntegrationTypeForm
    return render(request, "integrations/inbound_integration_type_add.html", {"form": form})


@permission_required('integrations.change_inboundintegrationtype', raise_exception=True)
def inbound_integration_type_update(request, inbound_integration_type_id):
    integration_type = get_object_or_404(InboundIntegrationType, id=inbound_integration_type_id)
    form = InboundIntegrationTypeForm(request.POST or None, instance=integration_type)
    if form.is_valid():
        form.save()
        return redirect("inbound_integration_type_detail", inbound_integration_type_id)
    return render(request, "integrations/inbound_integration_type_update.html", {"form": form})


class InboundIntegrationTypeListView(LoginRequiredMixin, ListView):
    template_name = 'integrations/inbound_integration_type_list.html'
    queryset = InboundIntegrationType.objects.get_queryset().order_by('name')
    context_object_name = 'integrations'
    paginate_by = default_paginate_by


###
# Outbound Integration Type Methods/Classes
###
@permission_required('integrations.view_outboundintegrationtype', raise_exception=True)
def outbound_integration_type_detail(request, module_id):
    integration_module = get_object_or_404(OutboundIntegrationType, pk=module_id)
    return render(request, "integrations/outbound_integration_type_detail.html", {"module": integration_module})


@permission_required('integrations.add_outboundintegrationtype', raise_exception=True)
def outbound_integration_type_add(request):
    if request.method == "POST":
        form = OutboundIntegrationTypeForm(request.POST)
        if form.is_valid():
            integration_type = form.save()
            return redirect("outbound_integration_type_detail", integration_type.id)
    else:
        form = OutboundIntegrationTypeForm
    return render(request, "integrations/outbound_integration_type_add.html", {"form": form})


@permission_required('integrations.change_inboundintegrationtype', raise_exception=True)
def outbound_integration_type_update(request, outbound_integration_type_id):
    integration_type = get_object_or_404(OutboundIntegrationType, id=outbound_integration_type_id)
    form = OutboundIntegrationTypeForm(request.POST or None, instance=integration_type)
    if form.is_valid():
        form.save()
        return redirect("outbound_integration_type_detail", outbound_integration_type_id)
    return render(request, "integrations/outbound_integration_type_update.html", {"form": form})


class OutboundIntegrationTypeList(LoginRequiredMixin, ListView):
    template_name = 'integrations/outbound_integration_type_list.html'
    queryset = OutboundIntegrationType.objects.get_queryset().order_by('name')
    context_object_name = 'integrations'
    paginate_by = default_paginate_by


###
# Inbound Integration Configuration Methods/Classes
###
@permission_required('integrations.view_inboundintegrationconfiguration', raise_exception=True)
def inbound_integration_configuration_detail(request, module_id):
    integration_module = get_object_or_404(InboundIntegrationConfiguration, pk=module_id)
    return render(request, "integrations/inbound_integration_configuration_detail.html", {"module": integration_module})


class InboundIntegrationConfigurationAddView(PermissionRequiredMixin, FormView):
    template_name = 'integrations/inbound_integration_configuration_add.html'
    form_class = InboundIntegrationConfigurationForm
    model = InboundIntegrationConfiguration
    permission_required = 'integrations.add_inboundintegrationconfiguration'

    def post(self, request, *args, **kwargs):
        form = InboundIntegrationConfigurationForm(request.POST)
        if form.is_valid():
            config: InboundIntegrationConfiguration = form.save()
            if not config.default_devicegroup:

                if not config.name:
                    config.name = f'{config.type.name} ({random_string()})'
                name = config.name + " - Default Group"
                device_group = DeviceGroup.objects.create(owner_id=config.owner.id, name=name)
                config.default_devicegroup = device_group
                config.save()
            else:
                device_group = config.default_devicegroup
            return redirect("device_group_update", device_group.id)

    def get_form(self, form_class=None):
        form = InboundIntegrationConfigurationForm()
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            form.fields['owner'].queryset = IsOrganizationMember.filter_queryset_for_user(form.fields['owner'].queryset,
                                                                                          self.request.user,
                                                                                          'name',
                                                                                          True)
        return form


class InboundIntegrationConfigurationUpdateView(PermissionRequiredMixin, UpdateView):
    template_name = 'integrations/inbound_integration_configuration_update.html'
    form_class = InboundIntegrationConfigurationForm
    model = InboundIntegrationConfiguration
    permission_required = 'integrations.change_inboundintegrationconfiguration'

    def get_object(self):
        configuration = get_object_or_404(InboundIntegrationConfiguration, pk=self.kwargs.get("configuration_id"))
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            if not IsOrganizationMember.is_object_owner(self.request.user, configuration):
                raise PermissionDenied
        return configuration

    def get(self, request, *args, **kwargs):
        form_class = self.get_form_class()
        self.object = self.get_object()
        # needed for model form field filtering
        form = form_class(request=request, instance=self.object)
        return self.render_to_response(self.get_context_data(form=form))

    def get_success_url(self):
        return reverse('inbound_integration_configuration_detail',
                       kwargs={'module_id': self.kwargs.get("configuration_id")})


class InboundIntegrationConfigurationListView(LoginRequiredMixin, SingleTableMixin, ListView):
    table_class = InboundIntegrationConfigurationTable
    template_name = 'integrations/inbound_integration_configuration_list.html'
    queryset = InboundIntegrationConfiguration.objects.get_queryset().order_by('id')
    paginate_by = default_paginate_by

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        base_url = reverse('inbound_integration_configuration_list')
        context["base_url"] = base_url
        return context

    def get_queryset(self):
        qs = super(InboundIntegrationConfigurationListView, self).get_queryset()
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            return IsOrganizationMember.filter_queryset_for_user(qs, self.request.user, 'owner__name')
        else:
            return qs


###
# Outbound Integration Configuration Methods/Classes
###
@permission_required('integrations.view_outboundintegrationconfiguration', raise_exception=True)
def outbound_integration_configuration_detail(request, module_id):
    integration_module = get_object_or_404(OutboundIntegrationConfiguration, pk=module_id)
    return render(request, "integrations/outbound_integration_configuration_detail.html",
                  {"module": integration_module})


class OutboundIntegrationConfigurationAddView(PermissionRequiredMixin, FormView):
    template_name = 'integrations/outbound_integration_configuration_add.html'
    form_class = OutboundIntegrationConfigurationForm
    model = OutboundIntegrationConfiguration
    permission_required = 'integrations.add_outboundintegrationconfiguration'

    def post(self, request, *args, **kwargs):
        form = OutboundIntegrationConfigurationForm(request.POST)
        if form.is_valid():
            config = form.save()
            return redirect("outbound_integration_configuration_detail", config.id)

    def get_form(self, form_class=None):
        form = OutboundIntegrationConfigurationForm()
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            form.fields['owner'].queryset = IsOrganizationMember.filter_queryset_for_user(form.fields['owner'].queryset,
                                                                                          self.request.user,
                                                                                         'name',
                                                                                          True)
        return form


class OutboundIntegrationConfigurationUpdateView(PermissionRequiredMixin, UpdateView):
    template_name = 'integrations/outbound_integration_configuration_update.html'
    form_class = OutboundIntegrationConfigurationForm
    model = OutboundIntegrationConfiguration
    permission_required = 'integrations.change_outboundintegrationconfiguration'

    def get_object(self):
        configuration = get_object_or_404(OutboundIntegrationConfiguration, pk=self.kwargs.get("configuration_id"))
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            if not IsOrganizationMember.is_object_owner(self.request.user, configuration):
                raise PermissionDenied
        return configuration

    def get(self, request, *args, **kwargs):
        form_class = self.get_form_class()
        self.object = self.get_object()
        # needed for model form field filtering
        form = form_class(request=request, instance=self.object)
        return self.render_to_response(self.get_context_data(form=form))

    def get_success_url(self):
        return reverse('outbound_integration_configuration_detail',
                       kwargs={'module_id': self.kwargs.get("configuration_id")})


class OutboundIntegrationConfigurationListView(LoginRequiredMixin, SingleTableMixin, ListView):
    table_class = OutboundIntegrationConfigurationTable
    template_name = 'integrations/outbound_integration_configuration_list.html'
    queryset = OutboundIntegrationConfiguration.objects.get_queryset().order_by('id')
    paginate_by = default_paginate_by

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        base_url = reverse('outbound_integration_configuration_list')
        context["base_url"] = base_url
        return context

    def get_queryset(self):
        qs = super(OutboundIntegrationConfigurationListView, self).get_queryset()
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            return IsOrganizationMember.filter_queryset_for_user(qs, self.request.user, 'owner__name')
        else:
            return qs


class BridgeIntegrationListView(LoginRequiredMixin, SingleTableMixin, ListView):
    table_class = BridgeIntegrationTable
    template_name = 'integrations/bridge_integration_list.html'
    queryset = BridgeIntegration.objects.get_queryset().order_by('name')
    paginate_by = default_paginate_by

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['base_url'] = reverse('bridge_integration_list')
        return context

    def get_querset(self):
        qs = super(BridgeIntegrationListView, self).get_queryset()
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            return IsOrganizationMember.filter_queryset_for_user(qs, self.request.user, 'owner__name')
        else:
            return qs


@permission_required('integrations.view_bridgeintegration', raise_exception=True)
def bridge_integration_view(request, module_id):
    bridge = get_object_or_404(BridgeIntegration, pk=module_id)
    return render(request, "integrations/bridge_integration_view.html",
                  {"module": bridge})


class BridgeIntegrationAddView(PermissionRequiredMixin, FormView):
    template_name = 'integrations/bridge_integration_add.html'
    form_class = BridgeIntegrationForm
    model = BridgeIntegration
    permission_required = 'integrations.add_bridgeintegration'

    def post(self, request, *args, **kwargs):
        form = BridgeIntegrationForm(request.POST)
        if form.is_valid():
            config = form.save()
            return redirect("bridge_integration_view", config.id)

    def get_form(self, form_class=None):
        form = BridgeIntegrationForm()
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            form.fields['owner'].queryset = IsOrganizationMember.filter_queryset_for_user(form.fields['owner'].queryset,
                                                                                          self.request.user,
                                                                                         'name',
                                                                                          True)
        return form


class BridgeIntegrationUpdateView(PermissionRequiredMixin, UpdateView):
    template_name = 'integrations/bridge_integration_update.html'
    form_class = BridgeIntegrationForm
    model = BridgeIntegration
    permission_required = 'integrations.change_bridgeintegration'

    def get_object(self):
        configuration = get_object_or_404(BridgeIntegration, pk=self.kwargs.get("id"))
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            if not IsOrganizationMember.is_object_owner(self.request.user, configuration):
                raise PermissionDenied
        return configuration

    def get(self, request, *args, **kwargs):
        form_class = self.get_form_class()
        self.object = self.get_object()
        # needed for model form field filtering
        form = form_class(request=request, instance=self.object)
        return self.render_to_response(self.get_context_data(form=form))

    def get_success_url(self):
        return reverse('bridge_integration_view',
                       kwargs={'module_id': self.kwargs.get("id")})


class ConsumerCreationError(Exception):
    """Raised when consumer fails to create"""
    def __init__(self, message="Failed to Create API Consumer"):
        self.message = message
        super().__init__(self.message)

    def __str__(self):
        return f'{self.message}'


def generate_consumer(request, id):
    bridge = get_object_or_404(BridgeIntegration, pk=id)
    url = "http://kong-proxy-127.0.0.1.nip.io/consumers"
    keys_route = "key-auth"
    test_url = KONG_PROXY_URL
    bridge_id = str(bridge.id)

    if bridge.consumer_id:
        # consumer has already been generated, lets get it
        get_url = f'{url}/{bridge.consumer_id}'
        response = requests.get(get_url)
        consumer = response.json()
        custom_id = consumer['custom_id']
        consumer_id = consumer['id']
        json_blob = custom_id.encode('utf-8')
        json_blob = base64.b64decode(json_blob)
        json_blob = json_blob.decode('utf-8')
        json_blob = json.loads(json_blob)
        integration_ids = json_blob['integration_ids']

        # check consumer is valid for this integration
        if bridge_id not in integration_ids:
            raise PermissionDenied

        api_key_url = f'{url}/{consumer_id}/{keys_route}'
        response = requests.get(api_key_url)
        api_keys = response.json()['data']


    else:
        json_blob = {"integration_ids": [bridge_id]}
        json_blob = json.dumps(json_blob)
        json_blob = json_blob.encode('utf-8')
        custom_id = base64.b64encode(json_blob)

        post_data = {'username': bridge.name,
                     'custom_id': custom_id}

        response = requests.post(url, data=post_data)

        if not response.ok:
            raise ConsumerCreationError

        content = json.loads(response.content)
        consumer_id = content["id"]

        api_key_url = f'{url}/{consumer_id}/{keys_route}'

        response = requests.post(api_key_url)

        if not response.ok:
            raise ConsumerCreationError
            # TODO: delete consumer if api key creation fails?

        bridge.consumer_id = consumer_id
        bridge.save()

    return render(request, "integrations/bridge_generate_consumer.html",
                  {"module": bridge,
                   "api_keys": api_keys})


import logging
import random

from django.contrib.auth.decorators import permission_required
from django.contrib.auth.mixins import PermissionRequiredMixin, LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.views.generic import ListView, DetailView, UpdateView, FormView
from django_filters.views import FilterView
from django_tables2.views import SingleTableMixin
from django.db.models import Count

from cdip_admin import settings
from core.permissions import IsGlobalAdmin, IsOrganizationMember
from organizations.models import Organization
from accounts.models import AccountProfileOrganization
from .filters import (
    DeviceStateFilter,
    DeviceGroupFilter,
    DeviceFilter,
    InboundIntegrationFilter,
    OutboundIntegrationFilter,
    BridgeIntegrationFilter
)
from .forms import (
    InboundIntegrationConfigurationForm,
    OutboundIntegrationConfigurationForm,
    DeviceGroupForm,
    DeviceGroupManagementForm,
    InboundIntegrationTypeForm,
    OutboundIntegrationTypeForm,
    BridgeIntegrationForm,
    KeyAuthForm,
    DeviceForm,
)
from .models import (
    InboundIntegrationType,
    OutboundIntegrationType,
    InboundIntegrationConfiguration,
    OutboundIntegrationConfiguration,
    Device,
    DeviceGroup,
    BridgeIntegration,
    BridgeIntegrationType
)
from .tables import (
    DeviceStateTable,
    DeviceGroupTable,
    DeviceTable,
    InboundIntegrationConfigurationTable,
    OutboundIntegrationConfigurationTable,
    BridgeIntegrationTable,
)
from .utils import get_api_key
from django.core.cache import cache
from django.http import HttpResponse
from crispy_forms.templatetags.crispy_forms_filters import as_crispy_field
from django.views.decorators.csrf import requires_csrf_token
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)
default_paginate_by = settings.DEFAULT_PAGINATE_BY


def random_string(n=4):
    return "".join(random.sample([chr(x) for x in range(97, 97 + 26)], n))


###
# Device Methods/Classes
###


@permission_required("integrations.view_device")
def device_detail(request, module_id):
    logger.info(f"Request for Device: {module_id}")
    device = get_object_or_404(Device, pk=module_id)
    return render(request, "integrations/device_detail.html", {"device": device})


class DeviceAddView(PermissionRequiredMixin, FormView):
    template_name = "integrations/device_add.html"
    form_class = DeviceForm
    model = Device
    permission_required = "integrations.add_device"

    def post(self, request, *args, **kwargs):
        form = DeviceForm(request.POST)
        if form.is_valid():
            dev = form.save()
            # save device automatically into default device group of inbound integration selected
            device_group = DeviceGroup.objects.get(
                pk=dev.inbound_configuration.default_devicegroup.id
            )
            if device_group:
                device_group.devices.add(dev)
            else:
                logger.warning(
                    f"Did not find default device group for {dev.id} with integration id: {dev.inbound_configuration}"
                )
            return redirect("device_list")
        else:
            logger.warning(f"Error saving device form: {form.errors}")
            # TODO: Validate JSON before saving

    def get_form(self, form_class=None):
        form = DeviceForm()
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            # can only add if you are an admin of at least one organization
            if not IsOrganizationMember.filter_queryset_for_user(
                Organization.objects.all(), self.request.user, "name", admin_only=True
            ):
                raise PermissionDenied
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            form = filter_device_group_form_fields(form, self.request.user)
        return form


class DeviceUpdateView(
    PermissionRequiredMixin,
    UpdateView,
):
    template_name = "integrations/device_update.html"
    form_class = DeviceForm
    model = Device
    permission_required = "integrations.change_device"

    def get_object(self):
        device = get_object_or_404(Device, pk=self.kwargs.get("module_id"))
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            if not IsOrganizationMember.is_object_owner(self.request.user, device):
                raise PermissionDenied
        return device

    def get(self, request, *args, **kwargs):
        form_class = self.get_form_class()
        self.object = self.get_object()
        form = form_class(instance=self.object)
        return self.render_to_response(self.get_context_data(form=form))

    def get_success_url(self):
        return reverse(
            "device_detail", kwargs={"module_id": self.kwargs.get("module_id")}
        )


class DeviceList(LoginRequiredMixin, SingleTableMixin, FilterView):
    template_name = "integrations/device_list.html"
    table_class = DeviceTable
    paginate_by = default_paginate_by
    filterset_class = DeviceFilter

    def get_context_data(self, **kwargs):
        # context = super().get_context_data(**kwargs)
        devices = cache.get("device_list")
        if not devices:
            context = super().get_context_data(**kwargs)
        base_url = reverse("device_list")
        context["base_url"] = base_url
        return context

        # context = super().get_context_data(**kwargs)
        # base_url = reverse("device_list")
        # context["base_url"] = base_url
        # return context


###
# Device Group Methods/Classes
###
class DeviceGroupListView(LoginRequiredMixin, SingleTableMixin, FilterView):
    template_name = "integrations/device_group_list.html"
    table_class = DeviceGroupTable
    paginate_by = default_paginate_by
    filterset_class = DeviceGroupFilter

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        base_url = reverse("device_group_list")
        context["base_url"] = base_url
        return context

    def get_table_data(self):
        qs = super().get_table_data()
        return qs.annotate(device_count=Count("devices"))


class DeviceGroupDetail(PermissionRequiredMixin, SingleTableMixin, DetailView):
    template_name = "integrations/device_group_detail.html"
    model = DeviceGroup
    table_class = DeviceTable
    paginate_by = default_paginate_by
    permission_required = "integrations.view_devicegroup"

    def get_object(self):
        return get_object_or_404(DeviceGroup, pk=self.kwargs.get("module_id"))

    def get_table_data(self):
        return self.get_object().devices

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        base_url = reverse("device_list")
        context["base_url"] = base_url
        return context


def filter_device_group_form_fields(form, user):
    # owner restricted to admin role
    if form.fields.get("owner"):
        form.fields["owner"].queryset = IsOrganizationMember.filter_queryset_for_user(
            form.fields["owner"].queryset, user, "name", True
        )
    # destinations open to viewer roles
    if form.fields.get("destinations"):
        des_qs = form.fields["destinations"].queryset
        org_qs = Organization.objects.filter(
            id__in=des_qs.values_list("owner", flat=True)
        )
        org_qs = IsOrganizationMember.filter_queryset_for_user(org_qs, user, "name")
        form.fields["destinations"].queryset = des_qs.filter(owner__in=org_qs)

    if form.fields.get("devices"):
        dev_qs = form.fields["devices"].queryset
        org_qs = Organization.objects.filter(
            id__in=dev_qs.values_list("inbound_configuration__owner", flat=True)
        )
        org_qs = IsOrganizationMember.filter_queryset_for_user(org_qs, user, "name")
        form.fields["devices"].queryset = dev_qs.filter(
            inbound_configuration__owner__in=org_qs
        )

    if form.fields.get("inbound_configuration"):
        ic_qs = form.fields["inbound_configuration"].queryset
        org_qs = Organization.objects.filter(
            id__in=ic_qs.values_list("owner", flat=True)
        )
        org_qs = IsOrganizationMember.filter_queryset_for_user(org_qs, user, "name")
        form.fields["inbound_configuration"].queryset = ic_qs.filter(owner__in=org_qs)

    return form


class DeviceGroupAddView(PermissionRequiredMixin, FormView):
    template_name = "integrations/device_group_add.html"
    form_class = DeviceGroupForm
    model = DeviceGroup
    permission_required = "integrations.add_devicegroup"

    def post(self, request, *args, **kwargs):
        form = DeviceGroupForm(request.POST)
        if form.is_valid():
            config = form.save()
            return redirect("device_group", str(config.id))

    def get_form(self, form_class=None):
        form = DeviceGroupForm()
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            # can only add if you are an admin of at least one organization
            if not IsOrganizationMember.filter_queryset_for_user(
                Organization.objects.all(), self.request.user, "name", admin_only=True
            ):
                raise PermissionDenied
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            form = filter_device_group_form_fields(form, self.request.user)
        return form


class DeviceGroupUpdateView(PermissionRequiredMixin, UpdateView):
    template_name = "integrations/device_group_update.html"
    form_class = DeviceGroupForm
    model = DeviceGroup
    permission_required = "integrations.change_devicegroup"

    def get(self, request, *args, **kwargs):
        form_class = self.get_form_class()
        self.object = self.get_object()
        form = form_class(instance=self.object)
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            form = filter_device_group_form_fields(form, self.request.user)
        return self.render_to_response(self.get_context_data(form=form))

    def get_object(self):
        device_group = get_object_or_404(
            DeviceGroup, pk=self.kwargs.get("device_group_id")
        )
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            if not IsOrganizationMember.is_object_owner(
                self.request.user, device_group.owner
            ):
                raise PermissionDenied
        return device_group

    def get_success_url(self):
        return reverse(
            "device_group", kwargs={"module_id": self.kwargs.get("device_group_id")}
        )


class DeviceGroupManagementUpdateView(LoginRequiredMixin, UpdateView):
    template_name = "integrations/device_group_update.html"
    form_class = DeviceGroupManagementForm
    model = DeviceGroup

    def get_object(self):
        device_group = get_object_or_404(
            DeviceGroup, pk=self.kwargs.get("device_group_id")
        )
        return device_group

    def get(self, request, *args, **kwargs):
        form_class = self.get_form_class()
        self.object = self.get_object()
        form = form_class(instance=self.object)
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            form = filter_device_group_form_fields(form, self.request.user)
        return self.render_to_response(self.get_context_data(form=form))

    def get_success_url(self):
        return reverse(
            "device_group", kwargs={"module_id": self.kwargs.get("device_group_id")}
        )


###
# DeviceState Methods/Classes
###


class DeviceStateList(LoginRequiredMixin, SingleTableMixin, FilterView):
    table_class = DeviceStateTable
    template_name = "integrations/device_state_list.html"
    paginate_by = default_paginate_by
    filterset_class = DeviceStateFilter

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        base_url = reverse("device_list")
        context["base_url"] = base_url
        return context


###
# Inbound Integration Type Methods/Classes
###
@permission_required("integrations.view_inboundintegrationtype", raise_exception=True)
def inbound_integration_type_detail(request, module_id):
    logger.info(f"Request for Integration Type: {module_id}")
    integration_module = get_object_or_404(InboundIntegrationType, pk=module_id)
    return render(
        request,
        "integrations/inbound_integration_type_detail.html",
        {"module": integration_module},
    )


@permission_required("integrations.add_inboundintegrationtype", raise_exception=True)
def inbound_integration_type_add(request):
    if request.method == "POST":
        form = InboundIntegrationTypeForm(request.POST)
        if form.is_valid():
            integration_type = form.save()
            return redirect("inbound_integration_type_detail", integration_type.id)
    else:
        form = InboundIntegrationTypeForm
    return render(
        request, "integrations/inbound_integration_type_add.html", {"form": form}
    )


@permission_required("integrations.change_inboundintegrationtype", raise_exception=True)
def inbound_integration_type_update(request, inbound_integration_type_id):
    integration_type = get_object_or_404(
        InboundIntegrationType, id=inbound_integration_type_id
    )
    form = InboundIntegrationTypeForm(request.POST or None, instance=integration_type)
    if form.is_valid():
        form.save()
        return redirect("inbound_integration_type_detail", inbound_integration_type_id)
    return render(
        request, "integrations/inbound_integration_type_update.html", {"form": form}
    )


class InboundIntegrationTypeListView(LoginRequiredMixin, ListView):
    template_name = "integrations/inbound_integration_type_list.html"
    queryset = InboundIntegrationType.objects.get_queryset().order_by("name")
    context_object_name = "integrations"
    paginate_by = default_paginate_by


###
# Outbound Integration Type Methods/Classes
###
@permission_required("integrations.view_outboundintegrationtype", raise_exception=True)
def outbound_integration_type_detail(request, module_id):
    integration = get_object_or_404(OutboundIntegrationType, pk=module_id)

    # permission_can_view(request, integration)

    return render(
        request,
        "integrations/outbound_integration_type_detail.html",
        {"module": integration},
    )


@permission_required("integrations.add_outboundintegrationtype", raise_exception=True)
def outbound_integration_type_add(request):
    if request.method == "POST":
        form = OutboundIntegrationTypeForm(request.POST)
        if form.is_valid():
            integration_type = form.save()
            return redirect("outbound_integration_type_detail", integration_type.id)

    form = OutboundIntegrationTypeForm
    return render(
        request, "integrations/outbound_integration_type_add.html", {"form": form}
    )


@permission_required("integrations.change_inboundintegrationtype", raise_exception=True)
def outbound_integration_type_update(request, outbound_integration_type_id):
    integration_type = get_object_or_404(
        OutboundIntegrationType, id=outbound_integration_type_id
    )
    form = OutboundIntegrationTypeForm(request.POST or None, instance=integration_type)
    if form.is_valid():
        form.save()
        return redirect(
            "outbound_integration_type_detail", outbound_integration_type_id
        )
    return render(
        request, "integrations/outbound_integration_type_update.html", {"form": form}
    )


class OutboundIntegrationTypeList(LoginRequiredMixin, ListView):
    template_name = "integrations/outbound_integration_type_list.html"
    queryset = OutboundIntegrationType.objects.get_queryset().order_by("name")
    context_object_name = "integrations"
    paginate_by = default_paginate_by


def permission_has_role(user, target, roles=("viewer",)):

    if not hasattr(target, "owner_id"):
        raise Exception(
            "Programming error. This method requires target to have owner_id."
        )

    if not user.accountprofile.organizations.filter(id=target.owner_id).exists():
        raise PermissionDenied

    if not AccountProfileOrganization.objects.filter(
        accountprofile__user=user, role__in=roles, organization__id=target.owner_id
    ):
        raise PermissionDenied


def permission_can_view(request, target):
    if IsGlobalAdmin.has_permission(None, request, None):
        return

    permission_has_role(request.user, target, roles=("viewer", "admin"))


def permission_can_administer(request, target):
    if IsGlobalAdmin.has_permission(None, request, None):
        return

    permission_has_role(request.user, target, roles=("admin"))


###
# Inbound Integration Configuration Methods/Classes
###
@permission_required(
    "integrations.view_inboundintegrationconfiguration", raise_exception=True
)
def inbound_integration_configuration_detail(request, id):

    integration = get_object_or_404(InboundIntegrationConfiguration, pk=id)

    permission_can_view(request, integration)

    form = KeyAuthForm()

    key = get_api_key(integration)
    if key:
        form.fields["key"].initial = key

    return render(
        request,
        "integrations/inbound_integration_configuration_detail.html",
        {
            "module": integration,
            "form": form,
        },
    )


class InboundIntegrationConfigurationAddView(PermissionRequiredMixin, FormView):
    template_name = "integrations/inbound_integration_configuration_add.html"
    form_class = InboundIntegrationConfigurationForm
    model = InboundIntegrationConfiguration
    permission_required = "integrations.add_inboundintegrationconfiguration"

    def post(self, request, *args, **kwargs):
        form = InboundIntegrationConfigurationForm(request.POST)
        if form.is_valid():
            config: InboundIntegrationConfiguration = form.save()
            device_group = config.default_devicegroup
            return redirect("device_group_update", device_group_id=device_group.id)

    def get_form(self, form_class=None):
        form = InboundIntegrationConfigurationForm()
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            form.fields[
                "owner"
            ].queryset = IsOrganizationMember.filter_queryset_for_user(
                form.fields["owner"].queryset, self.request.user, "name", True
            )
        return form


class InboundIntegrationConfigurationUpdateView(
    PermissionRequiredMixin,
    UpdateView,
):
    template_name = "integrations/inbound_integration_configuration_update.html"
    form_class = InboundIntegrationConfigurationForm
    model = InboundIntegrationConfiguration
    permission_required = "integrations.change_inboundintegrationconfiguration"

    def get_object(self):
        configuration = get_object_or_404(
            InboundIntegrationConfiguration, pk=self.kwargs.get("configuration_id")
        )
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            if not IsOrganizationMember.is_object_owner(
                self.request.user, configuration
            ):
                raise PermissionDenied
        return configuration

    def get(self, request, *args, **kwargs):
        form_class = self.get_form_class()
        self.object = self.get_object()
        # needed for model form field filtering
        form = form_class(request=request, instance=self.object)
        return self.render_to_response(self.get_context_data(form=form))

    def get_success_url(self):
        return reverse(
            "inbound_integration_configuration_detail",
            kwargs={"id": self.kwargs.get("configuration_id")},
        )


class InboundIntegrationConfigurationListView(
    LoginRequiredMixin, SingleTableMixin, FilterView
):
    table_class = InboundIntegrationConfigurationTable
    template_name = "integrations/inbound_integration_configuration_list.html"
    queryset = InboundIntegrationConfiguration.objects.get_queryset().order_by("id")
    paginate_by = default_paginate_by
    filterset_class = InboundIntegrationFilter

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        base_url = reverse("inbound_integration_configuration_list")
        context["base_url"] = base_url
        return context

    def get_queryset(self):
        qs = super(InboundIntegrationConfigurationListView, self).get_queryset()
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            return IsOrganizationMember.filter_queryset_for_user(
                qs, self.request.user, "owner__name"
            )
        else:
            return qs


###
# Outbound Integration Configuration Methods/Classes
###
@permission_required(
    "integrations.view_outboundintegrationconfiguration", raise_exception=True
)
def outbound_integration_configuration_detail(request, module_id):
    integration_module = get_object_or_404(
        OutboundIntegrationConfiguration, pk=module_id
    )

    permission_can_view(request, integration_module)

    return render(
        request,
        "integrations/outbound_integration_configuration_detail.html",
        {"module": integration_module},
    )


class OutboundIntegrationConfigurationAddView(PermissionRequiredMixin, FormView):
    template_name = "integrations/outbound_integration_configuration_add.html"
    form_class = OutboundIntegrationConfigurationForm
    model = OutboundIntegrationConfiguration
    permission_required = "integrations.add_outboundintegrationconfiguration"

    def post(self, request, *args, **kwargs):
        form = OutboundIntegrationConfigurationForm(request.POST)
        if form.is_valid():
            config = form.save()
            return redirect("outbound_integration_configuration_detail", config.id)

    def get_form(self, form_class=None):
        form = OutboundIntegrationConfigurationForm()
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            form.fields[
                "owner"
            ].queryset = IsOrganizationMember.filter_queryset_for_user(
                form.fields["owner"].queryset, self.request.user, "name", True
            )
        return form


class OutboundIntegrationConfigurationUpdateView(PermissionRequiredMixin, UpdateView):
    template_name = "integrations/outbound_integration_configuration_update.html"
    form_class = OutboundIntegrationConfigurationForm
    model = OutboundIntegrationConfiguration
    permission_required = "integrations.change_outboundintegrationconfiguration"

    def get_object(self):
        configuration = get_object_or_404(
            OutboundIntegrationConfiguration, pk=self.kwargs.get("configuration_id")
        )
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            if not IsOrganizationMember.is_object_owner(
                self.request.user, configuration
            ):
                raise PermissionDenied
        return configuration

    def get(self, request, *args, **kwargs):
        form_class = self.get_form_class()
        self.object = self.get_object()
        # needed for model form field filtering
        form = form_class(request=request, instance=self.object)
        return self.render_to_response(self.get_context_data(form=form))

    def get_success_url(self):
        return reverse(
            "outbound_integration_configuration_detail",
            kwargs={"module_id": self.kwargs.get("configuration_id")},
        )


class OutboundIntegrationConfigurationListView(
    LoginRequiredMixin, SingleTableMixin, FilterView
):
    table_class = OutboundIntegrationConfigurationTable
    template_name = "integrations/outbound_integration_configuration_list.html"
    queryset = OutboundIntegrationConfiguration.objects.get_queryset().order_by("id")
    paginate_by = default_paginate_by
    filterset_class = OutboundIntegrationFilter

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        base_url = reverse("outbound_integration_configuration_list")
        context["base_url"] = base_url
        return context

    def get_queryset(self):
        qs = super(OutboundIntegrationConfigurationListView, self).get_queryset()
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            return IsOrganizationMember.filter_queryset_for_user(
                qs, self.request.user, "owner__name"
            )
        else:
            return qs


class BridgeIntegrationListView(LoginRequiredMixin, SingleTableMixin, FilterView):
    table_class = BridgeIntegrationTable
    template_name = "integrations/bridge_integration_list.html"
    queryset = BridgeIntegration.objects.get_queryset().order_by("name")
    paginate_by = default_paginate_by
    filterset_class = BridgeIntegrationFilter

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["base_url"] = reverse("bridge_integration_list")
        return context

    def get_querset(self):
        qs = super(BridgeIntegrationListView, self).get_queryset()
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            return IsOrganizationMember.filter_queryset_for_user(
                qs, self.request.user, "owner__name"
            )
        else:
            return qs


@permission_required("integrations.view_bridgeintegration", raise_exception=True)
def bridge_integration_view(request, module_id):
    bridge = get_object_or_404(BridgeIntegration, pk=module_id)
    permission_can_view(request, bridge)
    form = KeyAuthForm()

    key = get_api_key(bridge)
    if key:
        form.fields["key"].initial = key

    return render(
        request,
        "integrations/bridge_integration_view.html",
        {"module": bridge, "form": form},
    )


class BridgeIntegrationAddView(PermissionRequiredMixin, FormView):
    template_name = "integrations/bridge_integration_add.html"
    form_class = BridgeIntegrationForm
    model = BridgeIntegration
    permission_required = "integrations.add_bridgeintegration"

    @staticmethod
    @requires_csrf_token
    def type_modal(request, integration_id):
        if request.GET.get("type") is not '':
            integration_type = request.GET.get("type")
            selected_type = BridgeIntegrationType.objects.get(id=integration_type)
        else:
            integration_type = "none"
            selected_type = "None"
        rendered = render_to_string('integrations/type_modal.html', {'selected_type': selected_type,
                                                                     'proceed_button': reverse("schema", kwargs={
                                                                         "integration_type": integration_type}),
                                                                     'cancel_button': reverse("dropdown_restore",
                                                                                              kwargs={
                                                                                                  "integration_id": integration_id})})
        return HttpResponse(rendered)

    @staticmethod
    @requires_csrf_token
    def dropdown_restore(request, integration_id):
        type_modal = reverse("type_modal", kwargs={"integration_id": integration_id})
        response = f"""<div id="div_id_type" class="form-group">
                            <label for="id_type" class=" requiredField">
                            Type
                            <button type="button" class="btn btn-light btn-sm py-0 mb-0 align-top" 
                                data-toggle="tooltip" data-placement="right" 
                                title="Integration component that can process the data.">?
                            </button>
                            <span class="asteriskField">*</span></label> 
                            <div class="">
                                <select name="type" hx-trigger="change" hx-target="body" hx-swap="beforeend"
                                hx-get={type_modal}
                                class="select form-control"
                                required id="id_type">
                                    <option value="" selected>-------</option>"""
        integration_types = BridgeIntegrationType.objects.values_list("id", "name", named=True)
        for option in integration_types:
            if str(option.id) == request.session["integration_type"]:
                response += """<option value="{}" selected>{}</option>""".format(option.id, option.name)
            else:
                response += """<option value="{}">{}</option>""".format(option.id, option.name)
        response += "</select></div> </div> </div> </div>"
        return HttpResponse(response)

    @staticmethod
    @requires_csrf_token
    def schema(request, integration_type):
        # TODO: We might need to find a way to provide an existing BridgeIntegration object here.
        form = BridgeIntegrationForm(request=request)
        request.session["integration_type"] = integration_type
        if integration_type != 'none':
            selected_type = BridgeIntegrationType.objects.get(id=integration_type)
            form.fields['additional'].widget.instance = selected_type.id
            return HttpResponse(as_crispy_field(form["additional"]))
        else:
            return HttpResponse("")

    def post(self, request, *args, **kwargs):
        form = BridgeIntegrationForm(request.POST)

        if form.is_valid():
            config = form.save()
            return redirect("bridge_integration_view", config.id)

        # Errors sends the user back to the form.
        return render(request, self.template_name, {'form': form})

    def get_form(self, form_class=None):
        form = BridgeIntegrationForm()
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            form.fields[
                "owner"
            ].queryset = IsOrganizationMember.filter_queryset_for_user(
                form.fields["owner"].queryset, self.request.user, "name", True
            )
        return form


class BridgeIntegrationUpdateView(PermissionRequiredMixin, UpdateView):
    template_name = "integrations/bridge_integration_update.html"
    form_class = BridgeIntegrationForm
    model = BridgeIntegration
    permission_required = "integrations.change_bridgeintegration"

    @staticmethod
    @requires_csrf_token
    def type_modal(request, integration_id):
        if request.GET.get("type") is not '':
            integration_type = request.GET.get("type")
            selected_type = BridgeIntegrationType.objects.get(id=integration_type)
        else:
            integration_type = "none"
            selected_type = "None"
        rendered = render_to_string('integrations/type_modal.html', {'selected_type': selected_type,
                                    'proceed_button': reverse("schema", kwargs={"integration_type": integration_type}),
                            'cancel_button': reverse("dropdown_restore", kwargs={"integration_id": integration_id})})
        return HttpResponse(rendered)

    @staticmethod
    @requires_csrf_token
    def dropdown_restore(request, integration_id):
        type_modal = reverse("type_modal", kwargs={"integration_id": integration_id})
        response = f"""<div id="div_id_type" class="form-group">
                        <label for="id_type" class=" requiredField">
                        Type
                        <button type="button" class="btn btn-light btn-sm py-0 mb-0 align-top" 
                            data-toggle="tooltip" data-placement="right" 
                            title="Integration component that can process the data.">?
                        </button>
                        <span class="asteriskField">*</span></label> 
                        <div class="">
                            <select name="type" hx-trigger="change" hx-target="body" hx-swap="beforeend"
                            hx-get={type_modal}
                            class="select form-control"
                            required id="id_type">
                                <option value="" selected>-------</option>"""
        integration_types = BridgeIntegrationType.objects.values_list("id", "name", named=True)
        for option in integration_types:
            if str(option.id) == request.session["integration_type"]:
                response += """<option value="{}" selected>{}</option>""".format(option.id, option.name)
            else:
                response += """<option value="{}">{}</option>""".format(option.id, option.name)
        response += "</select></div> </div> </div> </div>"
        return HttpResponse(response)

    @staticmethod
    @requires_csrf_token
    def schema(request, integration_type):
        # TODO: We might need to find a way to provide an existing BridgeIntegration object here.
        form = BridgeIntegrationForm(request=request)
        request.session["integration_type"] = integration_type
        if integration_type != 'none':
            selected_type = BridgeIntegrationType.objects.get(id=integration_type)
            form.fields['additional'].widget.instance = selected_type.id
            return HttpResponse(as_crispy_field(form["additional"]))
        else:
            return HttpResponse("")

    def get_object(self):
        configuration = get_object_or_404(BridgeIntegration, pk=self.kwargs.get("id"))
        permission_can_view(self.request, configuration)
        return configuration

    def get(self, request, *args, **kwargs):
        form_class = self.get_form_class()
        self.object = self.get_object()
        # needed for model form field filtering
        form = form_class(request=request, instance=self.object)
        return self.render_to_response(self.get_context_data(form=form))

    def get_success_url(self):
        return reverse(
            "bridge_integration_view", kwargs={"module_id": self.kwargs.get("id")}
        )

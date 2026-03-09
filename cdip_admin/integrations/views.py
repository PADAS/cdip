import json
import logging
import random

from django.contrib.auth.decorators import permission_required
from django.contrib.auth.mixins import PermissionRequiredMixin, LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST, require_GET
from django.views.generic import ListView, DetailView, UpdateView, FormView
from django_filters.views import FilterView
from django_tables2.views import SingleTableMixin
from django.db.models import Count, Case, When, Value, BooleanField

from cdip_admin import settings
from core.permissions import IsGlobalAdmin, IsOrganizationMember
from organizations.models import Organization
from accounts.models import AccountProfileOrganization
from .filters import (
    DeviceStateFilter,
    DeviceGroupFilter,
    DeviceFilter,
    InboundIntegrationTypeFilter,
    OutboundIntegrationTypeFilter,
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
    InboundIntegrationTypeTable,
    OutboundIntegrationTypeTable,
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
from core.widgets import FormattedJsonFieldWidget
from django.forms.fields import InvalidJSONInput
from django_jsonform.widgets import JSONFormWidget

logger = logging.getLogger(__name__)
default_paginate_by = settings.DEFAULT_PAGINATE_BY


@require_GET
@permission_required("integrations.change_inboundintegrationconfiguration")
def api_key_fragment(request, integration_id):
    """Return the API key form as an HTML fragment for lazy loading."""
    integration = get_object_or_404(
        InboundIntegrationConfiguration, pk=integration_id
    )
    if not IsGlobalAdmin.has_permission(None, request, None):
        if not IsOrganizationMember.is_object_owner(request.user, integration):
            raise PermissionDenied
    key_form = KeyAuthForm()
    key = get_api_key(integration)
    if key:
        key_form.fields["key"].initial = key
    return render(request, "integrations/_api_key_fragment.html", {"key_form": key_form})


@require_GET
@permission_required("integrations.change_bridgeintegration")
def bridge_api_key_fragment(request, integration_id):
    """Return the API key form as an HTML fragment for lazy loading."""
    integration = get_object_or_404(BridgeIntegration, pk=integration_id)
    if not IsGlobalAdmin.has_permission(None, request, None):
        if not IsOrganizationMember.is_object_owner(request.user, integration):
            raise PermissionDenied
    key_form = KeyAuthForm()
    key = get_api_key(integration)
    if key:
        key_form.fields["key"].initial = key
    return render(request, "integrations/_api_key_fragment.html", {"key_form": key_form})


def random_string(n=4):
    return "".join(random.sample([chr(x) for x in range(97, 97 + 26)], n))


def _preserve_state_on_error(form, request):
    """Fix two issues when re-rendering a form after validation failure:

    1. The owner field has hx-trigger="load" which auto-fetches the schema
       endpoint and replaces the state widget with the saved DB value,
       discarding the user's changes.  Strip those HTMX attrs on re-render.

    2. If the submitted state value is invalid JSON, the JSONFormWidget's
       inline script crashes on JSON.parse, leaving an empty container.
       Fall back to a plain textarea so the user can see and fix their input.
    """
    # 1) Stop owner from re-fetching the schema endpoint on load.
    #    Replace the attrs dict (don't mutate in-place) to avoid polluting
    #    the class-level widget definition shared across form instances.
    if "owner" in form.fields:
        owner_widget = form.fields["owner"].widget
        owner_widget.attrs = {
            k: v for k, v in owner_widget.attrs.items()
            if k not in ("hx-trigger", "hx-get", "hx-target", "hx-swap")
        }

    # 2) Fall back to textarea for invalid JSON so the editor doesn't vanish
    for field_name in ("state", "additional"):
        if field_name not in form.fields:
            continue
        bf = form[field_name]
        if isinstance(bf.value(), InvalidJSONInput):
            form.fields[field_name].widget = FormattedJsonFieldWidget()


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

    def get(self, request, *args, **kwargs):
        form = self.get_form()
        context = self.get_context_data(form=form)
        if request.headers.get("HX-Request"):
            self._configure_htmx_helper(form)
            return render(request, "integrations/device_add_partial.html", context)
        return self.render_to_response(context)

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
            if request.headers.get("HX-Request"):
                response = HttpResponse(status=204)
                response["HX-Trigger"] = "panelFormSaved"
                return response
            return redirect("device_list")
        else:
            logger.warning(f"Error saving device form: {form.errors}")
            if request.headers.get("HX-Request"):
                self._configure_htmx_helper(form)
                return render(request, "integrations/device_add_partial.html", {"form": form})
            return render(request, self.template_name, {"form": form})

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

    @staticmethod
    def _configure_htmx_helper(form):
        form_action = reverse("device_add")
        form.helper.form_action = form_action
        form.helper.inputs = []
        form.helper.attrs = {
            "hx-post": form_action,
            "hx-target": "#slide-panel-body",
            "hx-swap": "innerHTML",
            "novalidate": "",
        }


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
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            form = filter_device_group_form_fields(form, self.request.user)
        context = self.get_context_data(form=form)
        if request.headers.get("HX-Request"):
            self._configure_htmx_helper(form, self.object.pk)
            return render(request, "integrations/device_update_partial.html", context)
        return self.render_to_response(context)

    def form_valid(self, form):
        self.object = form.save()
        if self.request.headers.get("HX-Request"):
            response = HttpResponse(status=204)
            response["HX-Trigger"] = "panelFormSaved"
            return response
        return redirect(self.get_success_url())

    def form_invalid(self, form):
        if self.request.headers.get("HX-Request"):
            self._configure_htmx_helper(form, self.object.pk)
            context = self.get_context_data(form=form)
            return render(self.request, "integrations/device_update_partial.html", context)
        return super().form_invalid(form)

    @staticmethod
    def _configure_htmx_helper(form, pk):
        form_action = reverse("device_update", kwargs={"module_id": pk})
        form.helper.form_action = form_action
        form.helper.inputs = []
        form.helper.attrs = {
            "hx-post": form_action,
            "hx-target": "#slide-panel-body",
            "hx-swap": "innerHTML",
            "novalidate": "",
        }

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

    def get_template_names(self):
        if self.request.headers.get("HX-Request"):
            return ["integrations/table_partial.html"]
        return super().get_template_names()


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

    def get_template_names(self):
        if self.request.headers.get("HX-Request"):
            return ["integrations/table_partial.html"]
        return super().get_template_names()

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

    def get(self, request, *args, **kwargs):
        form = self.get_form()
        context = self.get_context_data(form=form)
        if request.headers.get("HX-Request"):
            self._configure_htmx_helper(form)
            return render(request, "integrations/device_group_add_partial.html", context)
        return self.render_to_response(context)

    def post(self, request, *args, **kwargs):
        form = DeviceGroupForm(request.POST)
        if form.is_valid():
            config = form.save()
            if request.headers.get("HX-Request"):
                response = HttpResponse(status=204)
                response["HX-Trigger"] = "panelFormSaved"
                return response
            return redirect("device_group", str(config.id))

        if request.headers.get("HX-Request"):
            self._configure_htmx_helper(form)
            return render(request, "integrations/device_group_add_partial.html", {"form": form})
        return render(request, self.template_name, {"form": form})

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

    @staticmethod
    def _configure_htmx_helper(form):
        form_action = reverse("device_group_add")
        form.helper.form_action = form_action
        form.helper.inputs = []
        form.helper.attrs = {
            "hx-post": form_action,
            "hx-target": "#slide-panel-body",
            "hx-swap": "innerHTML",
            "novalidate": "",
        }


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
        context = self.get_context_data(form=form)
        if request.headers.get("HX-Request"):
            self._configure_htmx_helper(form, self.object.pk)
            return render(request, "integrations/device_group_update_partial.html", context)
        return self.render_to_response(context)

    def form_valid(self, form):
        self.object = form.save()
        if self.request.headers.get("HX-Request"):
            response = HttpResponse(status=204)
            response["HX-Trigger"] = "panelFormSaved"
            return response
        return redirect(self.get_success_url())

    def form_invalid(self, form):
        if self.request.headers.get("HX-Request"):
            self._configure_htmx_helper(form, self.object.pk)
            context = self.get_context_data(form=form)
            return render(self.request, "integrations/device_group_update_partial.html", context)
        return super().form_invalid(form)

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

    @staticmethod
    def _configure_htmx_helper(form, pk):
        form_action = reverse("device_group_update", kwargs={"device_group_id": pk})
        form.helper.form_action = form_action
        form.helper.inputs = []
        form.helper.attrs = {
            "hx-post": form_action,
            "hx-target": "#slide-panel-body",
            "hx-swap": "innerHTML",
            "novalidate": "",
        }

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


class InboundIntegrationTypeAddView(PermissionRequiredMixin, FormView):
    template_name = "integrations/inbound_integration_type_add.html"
    form_class = InboundIntegrationTypeForm
    permission_required = "integrations.add_inboundintegrationtype"

    def get(self, request, *args, **kwargs):
        form = self.get_form()
        context = self.get_context_data(form=form)
        if request.headers.get("HX-Request"):
            self._configure_htmx_helper(form)
            return render(request, "integrations/inbound_integration_type_add_partial.html", context)
        return self.render_to_response(context)

    def post(self, request, *args, **kwargs):
        form = InboundIntegrationTypeForm(request.POST)
        if form.is_valid():
            integration_type = form.save()
            if request.headers.get("HX-Request"):
                response = HttpResponse(status=204)
                response["HX-Trigger"] = "panelFormSaved"
                return response
            return redirect("inbound_integration_type_detail", integration_type.id)
        if request.headers.get("HX-Request"):
            self._configure_htmx_helper(form)
            return render(request, "integrations/inbound_integration_type_add_partial.html", {"form": form})
        return render(request, self.template_name, {"form": form})

    @staticmethod
    def _configure_htmx_helper(form):
        form_action = reverse("inbound_integration_type_add")
        form.helper.form_action = form_action
        form.helper.inputs = []
        form.helper.attrs = {
            "hx-post": form_action,
            "hx-target": "#slide-panel-body",
            "hx-swap": "innerHTML",
            "novalidate": "",
        }


class InboundIntegrationTypeUpdateView(PermissionRequiredMixin, UpdateView):
    model = InboundIntegrationType
    form_class = InboundIntegrationTypeForm
    template_name = "integrations/inbound_integration_type_update.html"
    permission_required = "integrations.change_inboundintegrationtype"
    pk_url_kwarg = "inbound_integration_type_id"

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        context = self.get_context_data(form=form)
        if request.headers.get("HX-Request"):
            self._configure_htmx_helper(form, self.object.pk)
            return render(request, "integrations/inbound_integration_type_update_partial.html", context)
        return self.render_to_response(context)

    def form_valid(self, form):
        self.object = form.save()
        if self.request.headers.get("HX-Request"):
            response = HttpResponse(status=204)
            response["HX-Trigger"] = "panelFormSaved"
            return response
        return redirect("inbound_integration_type_detail", self.object.pk)

    def form_invalid(self, form):
        if self.request.headers.get("HX-Request"):
            self._configure_htmx_helper(form, self.object.pk)
            context = self.get_context_data(form=form)
            return render(self.request, "integrations/inbound_integration_type_update_partial.html", context)
        return super().form_invalid(form)

    @staticmethod
    def _configure_htmx_helper(form, pk):
        form_action = reverse("inbound_integration_type_update", kwargs={"inbound_integration_type_id": pk})
        form.helper.form_action = form_action
        form.helper.inputs = []
        form.helper.attrs = {
            "hx-post": form_action,
            "hx-target": "#slide-panel-body",
            "hx-swap": "innerHTML",
            "novalidate": "",
        }

    def get_success_url(self):
        return reverse("inbound_integration_type_list")


class InboundIntegrationTypeListView(LoginRequiredMixin, SingleTableMixin, FilterView):
    table_class = InboundIntegrationTypeTable
    template_name = "integrations/inbound_integration_type_list.html"
    queryset = InboundIntegrationType.objects.get_queryset().order_by("name")
    paginate_by = default_paginate_by
    filterset_class = InboundIntegrationTypeFilter

    def get_filterset(self, *args, **kwargs):
        fs = super().get_filterset(*args, **kwargs)
        fs.form.auto_id = "filter_%s"
        return fs

    def get_template_names(self):
        if self.request.headers.get("HX-Request"):
            return ["integrations/table_partial.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["base_url"] = reverse("inbound_integration_type_list")
        return context


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


class OutboundIntegrationTypeAddView(PermissionRequiredMixin, FormView):
    template_name = "integrations/outbound_integration_type_add.html"
    form_class = OutboundIntegrationTypeForm
    permission_required = "integrations.add_outboundintegrationtype"

    def get(self, request, *args, **kwargs):
        form = self.get_form()
        context = self.get_context_data(form=form)
        if request.headers.get("HX-Request"):
            self._configure_htmx_helper(form)
            return render(request, "integrations/outbound_integration_type_add_partial.html", context)
        return self.render_to_response(context)

    def post(self, request, *args, **kwargs):
        form = OutboundIntegrationTypeForm(request.POST)
        if form.is_valid():
            integration_type = form.save()
            if request.headers.get("HX-Request"):
                response = HttpResponse(status=204)
                response["HX-Trigger"] = "panelFormSaved"
                return response
            return redirect("outbound_integration_type_detail", integration_type.id)
        if request.headers.get("HX-Request"):
            self._configure_htmx_helper(form)
            return render(request, "integrations/outbound_integration_type_add_partial.html", {"form": form})
        return render(request, self.template_name, {"form": form})

    @staticmethod
    def _configure_htmx_helper(form):
        form_action = reverse("outbound_integration_type_add")
        form.helper.form_action = form_action
        form.helper.inputs = []
        form.helper.attrs = {
            "hx-post": form_action,
            "hx-target": "#slide-panel-body",
            "hx-swap": "innerHTML",
            "novalidate": "",
        }


class OutboundIntegrationTypeUpdateView(PermissionRequiredMixin, UpdateView):
    model = OutboundIntegrationType
    form_class = OutboundIntegrationTypeForm
    template_name = "integrations/outbound_integration_type_update.html"
    permission_required = "integrations.change_outboundintegrationtype"
    pk_url_kwarg = "outbound_integration_type_id"

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        context = self.get_context_data(form=form)
        if request.headers.get("HX-Request"):
            self._configure_htmx_helper(form, self.object.pk)
            return render(request, "integrations/outbound_integration_type_update_partial.html", context)
        return self.render_to_response(context)

    def form_valid(self, form):
        self.object = form.save()
        if self.request.headers.get("HX-Request"):
            response = HttpResponse(status=204)
            response["HX-Trigger"] = "panelFormSaved"
            return response
        return redirect("outbound_integration_type_detail", self.object.pk)

    def form_invalid(self, form):
        if self.request.headers.get("HX-Request"):
            self._configure_htmx_helper(form, self.object.pk)
            context = self.get_context_data(form=form)
            return render(self.request, "integrations/outbound_integration_type_update_partial.html", context)
        return super().form_invalid(form)

    @staticmethod
    def _configure_htmx_helper(form, pk):
        form_action = reverse("outbound_integration_type_update", kwargs={"outbound_integration_type_id": pk})
        form.helper.form_action = form_action
        form.helper.inputs = []
        form.helper.attrs = {
            "hx-post": form_action,
            "hx-target": "#slide-panel-body",
            "hx-swap": "innerHTML",
            "novalidate": "",
        }

    def get_success_url(self):
        return reverse("outbound_integration_type_list")


class OutboundIntegrationTypeListView(LoginRequiredMixin, SingleTableMixin, FilterView):
    table_class = OutboundIntegrationTypeTable
    template_name = "integrations/outbound_integration_type_list.html"
    queryset = OutboundIntegrationType.objects.get_queryset().order_by("name")
    paginate_by = default_paginate_by
    filterset_class = OutboundIntegrationTypeFilter

    def get_filterset(self, *args, **kwargs):
        fs = super().get_filterset(*args, **kwargs)
        fs.form.auto_id = "filter_%s"
        return fs

    def get_template_names(self):
        if self.request.headers.get("HX-Request"):
            return ["integrations/table_partial.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["base_url"] = reverse("outbound_integration_type_list")
        return context


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
class InboundIntegrationConfigurationAddView(PermissionRequiredMixin, FormView):
    template_name = "integrations/inbound_integration_configuration_add.html"
    form_class = InboundIntegrationConfigurationForm
    model = InboundIntegrationConfiguration
    permission_required = "integrations.add_inboundintegrationconfiguration"

    def get(self, request, *args, **kwargs):
        form = self.get_form()
        context = self.get_context_data(form=form)
        if request.headers.get("HX-Request"):
            self._configure_htmx_helper(form)
            return render(request, "integrations/inbound_integration_configuration_add_partial.html", context)
        return self.render_to_response(context)

    def post(self, request, *args, **kwargs):
        form = InboundIntegrationConfigurationForm(request.POST)
        if form.is_valid():
            config: InboundIntegrationConfiguration = form.save()
            if request.headers.get("HX-Request"):
                device_group = config.default_devicegroup
                device_group_url = reverse("device_group_update", kwargs={"device_group_id": device_group.id})
                return render(
                    request,
                    "integrations/inbound_integration_configuration_add_success.html",
                    {"config": config, "device_group_url": device_group_url},
                )
            device_group = config.default_devicegroup
            return redirect("device_group_update", device_group_id=device_group.id)
        if request.headers.get("HX-Request"):
            self._configure_htmx_helper(form)
            return render(request, "integrations/inbound_integration_configuration_add_partial.html", {"form": form})
        return render(request, self.template_name, {'form': form})

    def get_form(self, form_class=None):
        form = InboundIntegrationConfigurationForm()
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            form.fields[
                "owner"
            ].queryset = IsOrganizationMember.filter_queryset_for_user(
                form.fields["owner"].queryset, self.request.user, "name", True
            )
        return form

    @staticmethod
    def _configure_htmx_helper(form):
        form_action = reverse("inbound_integration_configuration_add")
        form.helper.form_action = form_action
        form.helper.include_media = False
        form.helper.inputs = []
        form.helper.attrs = {
            "hx-post": form_action,
            "hx-target": "#slide-panel-body",
            "hx-swap": "innerHTML",
            "novalidate": "",
        }


class InboundIntegrationConfigurationUpdateView(
    PermissionRequiredMixin,
    UpdateView,
):
    template_name = "integrations/inbound_integration_configuration_update.html"
    form_class = InboundIntegrationConfigurationForm
    model = InboundIntegrationConfiguration
    permission_required = "integrations.change_inboundintegrationconfiguration"

    @staticmethod
    @requires_csrf_token
    def type_modal(request, integration_id):
        if request.GET.get("type"):
            integration_type = request.GET.get("type")
            selected_type = InboundIntegrationType.objects.get(id=integration_type)
        else:
            integration_type = "none"
            selected_type = "None"
        rendered = render_to_string('integrations/type_modal.html', {'selected_type': selected_type,
                                                                     'target': '#div_id_state',
                                                                     'proceed_button':
                                                                         reverse("inboundconfigurations/schema",
                                                                                 kwargs={
                                                                                     "integration_type":
                                                                                         integration_type,
                                                                                     "integration_id":
                                                                                         integration_id,
                                                                                     "update": "true"}),
                                                                     'cancel_button':
                                                                         reverse(
                                                                             "inboundconfigurations/dropdown_restore",
                                                                             kwargs={
                                                                                 "integration_id":
                                                                                     integration_id}
                                                                         )})
        return HttpResponse(rendered)

    @staticmethod
    @requires_csrf_token
    def schema(request, integration_type, integration_id, update):

        form = InboundIntegrationConfigurationForm(request=request)
        selected_type = InboundIntegrationType.objects.get(id=integration_type)

        request.session["integration_type"] = integration_type
        # No type selected
        if integration_type == 'none':
            return HttpResponse("Please select an integration type")
        try:
            initial_state = InboundIntegrationConfiguration.objects.get(id=integration_id).state or {}
        except InboundIntegrationConfiguration.DoesNotExist:
            initial_state = {}
        # a new type is selected and schema needs to be updated
        if update == "true":
            if selected_type.configuration_schema != {}:
                request.session["integration_type"] = integration_type
                form.fields['state'].widget.instance = selected_type.id
            else:
                form.fields['state'].widget = FormattedJsonFieldWidget()
                form.fields['state'].initial = initial_state
            return HttpResponse(as_crispy_field(form["state"]))

        # loading the schema already associated with the form
        # load the proper schema populated with additional values from the integration

        form.fields['state'].initial = initial_state

        if selected_type.configuration_schema != {}:
            form.fields['state'].widget = JSONFormWidget(
                schema=selected_type.configuration_schema,
            )
        # load a textarea populated with json from the integration
        else:
            form.fields['state'].widget = FormattedJsonFieldWidget()
        return HttpResponse(as_crispy_field(form["state"]))

    @staticmethod
    @requires_csrf_token
    def dropdown_restore(request, integration_id):
        type_modal = reverse("inboundconfigurations/type_modal", kwargs={"integration_id": integration_id})
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
        integration_types = InboundIntegrationType.objects.values_list("id", "name", named=True)
        for option in integration_types:
            if str(option.id) == request.session["integration_type"]:
                response += """<option value="{}" selected>{}</option>""".format(option.id, option.name)
            else:
                response += """<option value="{}">{}</option>""".format(option.id, option.name)
        response += "</select></div> </div> </div> </div>"
        return HttpResponse(response)

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

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        return kwargs

    def get(self, request, *args, **kwargs):
        form_class = self.get_form_class()
        self.object = self.get_object()
        is_htmx = request.headers.get("HX-Request")
        form = form_class(request=request, instance=self.object)
        context = self.get_context_data(form=form)
        if is_htmx:
            self._configure_htmx_helper(
                form, "inbound_integration_configuration_update",
                {"configuration_id": self.object.pk},
            )
            return render(
                request,
                "integrations/inbound_integration_configuration_update_partial.html",
                context,
            )
        key_form = KeyAuthForm()
        key = get_api_key(self.object)
        if key:
            key_form.fields["key"].initial = key
        context["key_form"] = key_form
        return self.render_to_response(context)

    def form_valid(self, form):
        self.object = form.save()
        if self.request.headers.get("HX-Request"):
            response = HttpResponse(status=204)
            response["HX-Trigger"] = "panelFormSaved"
            return response
        return redirect(self.get_success_url())

    def form_invalid(self, form):
        _preserve_state_on_error(form, self.request)
        if self.request.headers.get("HX-Request"):
            self._configure_htmx_helper(
                form, "inbound_integration_configuration_update",
                {"configuration_id": self.object.pk},
            )
            context = self.get_context_data(form=form)
            return render(
                self.request,
                "integrations/inbound_integration_configuration_update_partial.html",
                context,
            )
        return super().form_invalid(form)

    @staticmethod
    def _configure_htmx_helper(form, url_name, url_kwargs):
        form_action = reverse(url_name, kwargs=url_kwargs)
        form.helper.form_action = form_action
        form.helper.include_media = False
        form.helper.inputs = []
        form.helper.attrs = {
            "hx-post": form_action,
            "hx-target": "#slide-panel-body",
            "hx-swap": "innerHTML",
            "novalidate": "",
        }

    def get_success_url(self):
        return reverse("inbound_integration_configuration_list")


class InboundIntegrationConfigurationListView(
    LoginRequiredMixin, SingleTableMixin, FilterView
):
    table_class = InboundIntegrationConfigurationTable
    template_name = "integrations/inbound_integration_configuration_list.html"
    queryset = InboundIntegrationConfiguration.objects.get_queryset().order_by("id")
    paginate_by = default_paginate_by
    filterset_class = InboundIntegrationFilter

    def get_filterset(self, *args, **kwargs):
        fs = super().get_filterset(*args, **kwargs)
        fs.form.auto_id = "filter_%s"
        return fs

    def get_template_names(self):
        if self.request.headers.get("HX-Request"):
            return ["integrations/table_partial.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        base_url = reverse("inbound_integration_configuration_list")
        context["base_url"] = base_url
        qs = self.filterset.qs
        context["error_count"] = qs.filter(state__has_key='error').count()
        context["total_count"] = qs.count()
        return context

    def get_queryset(self):
        qs = super(InboundIntegrationConfigurationListView, self).get_queryset()
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            qs = IsOrganizationMember.filter_queryset_for_user(
                qs, self.request.user, "owner__name"
            )
        return qs.annotate(
            _has_error=Case(
                When(state__has_key='error', then=Value(True)),
                default=Value(False),
                output_field=BooleanField(),
            )
        ).order_by('-_has_error', 'type__name', 'id')


###
# Outbound Integration Configuration Methods/Classes
###
class OutboundIntegrationConfigurationAddView(PermissionRequiredMixin, FormView):
    template_name = "integrations/outbound_integration_configuration_add.html"
    form_class = OutboundIntegrationConfigurationForm
    model = OutboundIntegrationConfiguration
    permission_required = "integrations.add_outboundintegrationconfiguration"

    def get(self, request, *args, **kwargs):
        form = self.get_form()
        context = self.get_context_data(form=form)
        if request.headers.get("HX-Request"):
            self._configure_htmx_helper(form)
            return render(request, "integrations/outbound_integration_configuration_add_partial.html", context)
        return self.render_to_response(context)

    def post(self, request, *args, **kwargs):
        form = OutboundIntegrationConfigurationForm(request.POST)
        if form.is_valid():
            config = form.save()
            if request.headers.get("HX-Request"):
                response = HttpResponse(status=204)
                response["HX-Trigger"] = "panelFormSaved"
                return response
            return redirect("outbound_integration_configuration_list")
        if request.headers.get("HX-Request"):
            self._configure_htmx_helper(form)
            return render(request, "integrations/outbound_integration_configuration_add_partial.html", {"form": form})
        return render(request, self.template_name, {'form': form})

    def get_form(self, form_class=None):
        form = OutboundIntegrationConfigurationForm()
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            form.fields[
                "owner"
            ].queryset = IsOrganizationMember.filter_queryset_for_user(
                form.fields["owner"].queryset, self.request.user, "name", True
            )
        return form

    @staticmethod
    def _configure_htmx_helper(form):
        form_action = reverse("outbound_integration_configuration_add")
        form.helper.form_action = form_action
        form.helper.include_media = False
        form.helper.inputs = []
        form.helper.attrs = {
            "hx-post": form_action,
            "hx-target": "#slide-panel-body",
            "hx-swap": "innerHTML",
            "novalidate": "",
        }


class OutboundIntegrationConfigurationUpdateView(PermissionRequiredMixin, UpdateView):
    template_name = "integrations/outbound_integration_configuration_update.html"
    form_class = OutboundIntegrationConfigurationForm
    model = OutboundIntegrationConfiguration
    permission_required = "integrations.change_outboundintegrationconfiguration"

    @staticmethod
    @requires_csrf_token
    def type_modal(request, configuration_id):
        if request.GET.get("type") is not '':
            integration_type = request.GET.get("type")
            selected_type = OutboundIntegrationType.objects.get(id=integration_type)
        else:
            integration_type = "none"
            selected_type = "None"
        rendered = render_to_string('integrations/type_modal.html', {'selected_type': selected_type,
                                                                     'target': '#div_id_state',
                                                                     'proceed_button':
                                                                         reverse("outboundconfigurations/schema",
                                                                                 kwargs={
                                                                                     "configuration_type":
                                                                                         integration_type,
                                                                                     "configuration_id":
                                                                                         configuration_id,
                                                                                     "update": "true"}),
                                                                     'cancel_button':
                                                                         reverse(
                                                                             "outboundconfigurations/dropdown_restore",
                                                                             kwargs={
                                                                                 "integration_id":
                                                                                     configuration_id}
                                                                         )})
        return HttpResponse(rendered)

    @staticmethod
    @requires_csrf_token
    def schema(request, configuration_type, configuration_id, update):

        form = OutboundIntegrationConfigurationForm(request=request)
        selected_type = OutboundIntegrationType.objects.get(id=configuration_type)

        request.session["integration_type"] = configuration_type
        # No type selected
        if configuration_type == 'none':
            return HttpResponse("Please select an integration type")
        try:
            initial_state = OutboundIntegrationConfiguration.objects.get(id=configuration_id).state or {}
        except OutboundIntegrationConfiguration.DoesNotExist:
            initial_state = {}

        # a new type is selected and schema needs to be updated
        if update == "true":
            if selected_type.configuration_schema != {}:
                request.session["integration_type"] = configuration_type
                form.fields['state'].widget.instance = selected_type.id
            else:
                form.fields['state'].widget = FormattedJsonFieldWidget()
                form.fields['state'].initial = initial_state
            return HttpResponse(as_crispy_field(form["state"]))

        # loading the schema already associated with the form
        # load the proper schema populated with additional values from the integration

        form.fields['state'].initial = initial_state

        if selected_type.configuration_schema != {}:
            form.fields['state'].widget = JSONFormWidget(
                schema=selected_type.configuration_schema,
            )
        # load a textarea populated with json from the integration
        else:
            form.fields['state'].widget = FormattedJsonFieldWidget()
        return HttpResponse(as_crispy_field(form["state"]))

    @staticmethod
    @requires_csrf_token
    def dropdown_restore(request, integration_id):
        type_modal = reverse("outboundconfigurations/type_modal", kwargs={"configuration_id": integration_id})
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
        integration_types = OutboundIntegrationType.objects.values_list("id", "name", named=True)
        for option in integration_types:
            if str(option.id) == request.session["integration_type"]:
                response += """<option value="{}" selected>{}</option>""".format(option.id, option.name)
            else:
                response += """<option value="{}">{}</option>""".format(option.id, option.name)
        response += "</select></div> </div> </div> </div>"
        return HttpResponse(response)

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

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        return kwargs

    def get(self, request, *args, **kwargs):
        form_class = self.get_form_class()
        self.object = self.get_object()
        is_htmx = request.headers.get("HX-Request")
        form = form_class(request=request, instance=self.object)
        context = self.get_context_data(form=form)
        if is_htmx:
            self._configure_htmx_helper(
                form, "outbound_integration_configuration_update",
                {"configuration_id": self.object.pk},
            )
            return render(
                request,
                "integrations/outbound_integration_configuration_update_partial.html",
                context,
            )
        return self.render_to_response(context)

    def form_valid(self, form):
        self.object = form.save()
        if self.request.headers.get("HX-Request"):
            response = HttpResponse(status=204)
            response["HX-Trigger"] = "panelFormSaved"
            return response
        return redirect(self.get_success_url())

    def form_invalid(self, form):
        _preserve_state_on_error(form, self.request)
        if self.request.headers.get("HX-Request"):
            self._configure_htmx_helper(
                form, "outbound_integration_configuration_update",
                {"configuration_id": self.object.pk},
            )
            context = self.get_context_data(form=form)
            return render(
                self.request,
                "integrations/outbound_integration_configuration_update_partial.html",
                context,
            )
        return super().form_invalid(form)

    @staticmethod
    def _configure_htmx_helper(form, url_name, url_kwargs):
        form_action = reverse(url_name, kwargs=url_kwargs)
        form.helper.form_action = form_action
        form.helper.include_media = False
        form.helper.inputs = []
        form.helper.attrs = {
            "hx-post": form_action,
            "hx-target": "#slide-panel-body",
            "hx-swap": "innerHTML",
            "novalidate": "",
        }

    def get_success_url(self):
        return reverse("outbound_integration_configuration_list")


class OutboundIntegrationConfigurationListView(
    LoginRequiredMixin, SingleTableMixin, FilterView
):
    table_class = OutboundIntegrationConfigurationTable
    template_name = "integrations/outbound_integration_configuration_list.html"
    queryset = OutboundIntegrationConfiguration.objects.get_queryset().order_by("id")
    paginate_by = default_paginate_by
    filterset_class = OutboundIntegrationFilter

    def get_filterset(self, *args, **kwargs):
        fs = super().get_filterset(*args, **kwargs)
        fs.form.auto_id = "filter_%s"
        return fs

    def get_template_names(self):
        if self.request.headers.get("HX-Request"):
            return ["integrations/table_partial.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        base_url = reverse("outbound_integration_configuration_list")
        context["base_url"] = base_url
        qs = self.filterset.qs
        context["error_count"] = qs.filter(state__has_key='error').count()
        context["total_count"] = qs.count()
        return context

    def get_queryset(self):
        qs = super(OutboundIntegrationConfigurationListView, self).get_queryset()
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            qs = IsOrganizationMember.filter_queryset_for_user(
                qs, self.request.user, "owner__name"
            )
        return qs.annotate(
            _has_error=Case(
                When(state__has_key='error', then=Value(True)),
                default=Value(False),
                output_field=BooleanField(),
            )
        ).order_by('-_has_error', 'type__name', 'id')


class BridgeIntegrationListView(LoginRequiredMixin, SingleTableMixin, FilterView):
    table_class = BridgeIntegrationTable
    template_name = "integrations/bridge_integration_list.html"
    queryset = BridgeIntegration.objects.get_queryset().order_by("name")
    paginate_by = default_paginate_by
    filterset_class = BridgeIntegrationFilter

    def get_filterset(self, *args, **kwargs):
        fs = super().get_filterset(*args, **kwargs)
        fs.form.auto_id = "filter_%s"
        return fs

    def get_template_names(self):
        if self.request.headers.get("HX-Request"):
            return ["integrations/table_partial.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["base_url"] = reverse("bridge_integration_list")
        qs = self.filterset.qs
        context["error_count"] = qs.filter(state__has_key='error').count()
        context["total_count"] = qs.count()
        return context

    def get_queryset(self):
        qs = super(BridgeIntegrationListView, self).get_queryset()
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            qs = IsOrganizationMember.filter_queryset_for_user(
                qs, self.request.user, "owner__name"
            )
        return qs.annotate(
            _has_error=Case(
                When(state__has_key='error', then=Value(True)),
                default=Value(False),
                output_field=BooleanField(),
            )
        ).order_by('-_has_error', 'name', 'id')


@permission_required("integrations.view_bridgeintegration", raise_exception=True)
def bridge_integration_view(request, module_id):
    return redirect("bridge_integration_update", id=module_id)


class BridgeIntegrationAddView(PermissionRequiredMixin, FormView):
    template_name = "integrations/bridge_integration_add.html"
    form_class = BridgeIntegrationForm
    model = BridgeIntegration
    permission_required = "integrations.add_bridgeintegration"

    def get(self, request, *args, **kwargs):
        form = self.get_form()
        context = self.get_context_data(form=form)
        if request.headers.get("HX-Request"):
            self._configure_htmx_helper(form)
            return render(request, "integrations/bridge_integration_add_partial.html", context)
        return self.render_to_response(context)

    def post(self, request, *args, **kwargs):
        form = BridgeIntegrationForm(request.POST)

        if form.is_valid():
            config = form.save()
            if request.headers.get("HX-Request"):
                response = HttpResponse(status=204)
                response["HX-Trigger"] = "panelFormSaved"
                return response
            return redirect("bridge_integration_update", id=config.id)

        if request.headers.get("HX-Request"):
            self._configure_htmx_helper(form)
            return render(request, "integrations/bridge_integration_add_partial.html", {"form": form})
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

    @staticmethod
    def _configure_htmx_helper(form):
        form_action = reverse("bridge_integration_add")
        form.helper.form_action = form_action
        form.helper.include_media = False
        form.helper.inputs = []
        form.helper.attrs = {
            "hx-post": form_action,
            "hx-target": "#slide-panel-body",
            "hx-swap": "innerHTML",
            "novalidate": "",
        }


class BridgeIntegrationUpdateView(PermissionRequiredMixin, UpdateView):
    template_name = "integrations/bridge_integration_update.html"
    form_class = BridgeIntegrationForm
    model = BridgeIntegration
    permission_required = "integrations.change_bridgeintegration"

    pk_url_kwarg = "id"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        return kwargs

    def get(self, request, *args, **kwargs):
        form_class = self.get_form_class()
        self.object = self.get_object()
        is_htmx = request.headers.get("HX-Request")
        form = form_class(request=request, instance=self.object)
        context = self.get_context_data(form=form)
        if is_htmx:
            self._configure_htmx_helper(form, "bridge_integration_update", {"id": self.object.pk})
            return render(
                request,
                "integrations/bridge_integration_update_partial.html",
                context,
            )
        key_form = KeyAuthForm()
        key = get_api_key(self.object)
        if key:
            key_form.fields["key"].initial = key
        context["key_form"] = key_form
        return self.render_to_response(context)

    def form_valid(self, form):
        self.object = form.save()
        if self.request.headers.get("HX-Request"):
            response = HttpResponse(status=204)
            response["HX-Trigger"] = "panelFormSaved"
            return response
        return redirect(self.get_success_url())

    def form_invalid(self, form):
        _preserve_state_on_error(form, self.request)
        if self.request.headers.get("HX-Request"):
            self._configure_htmx_helper(form, "bridge_integration_update", {"id": self.object.pk})
            context = self.get_context_data(form=form)
            return render(
                self.request,
                "integrations/bridge_integration_update_partial.html",
                context,
            )
        return super().form_invalid(form)

    @staticmethod
    def _configure_htmx_helper(form, url_name, url_kwargs):
        form_action = reverse(url_name, kwargs=url_kwargs)
        form.helper.form_action = form_action
        form.helper.include_media = False
        form.helper.inputs = []
        form.helper.attrs = {
            "hx-post": form_action,
            "hx-target": "#slide-panel-body",
            "hx-swap": "innerHTML",
            "novalidate": "",
        }

    def get_success_url(self):
        return reverse("bridge_integration_list")

    @staticmethod
    @requires_csrf_token
    def type_modal(request, integration_id):
        if request.GET.get("type"):
            integration_type = request.GET.get("type")
            selected_type = BridgeIntegrationType.objects.get(id=integration_type)
        else:
            integration_type = "none"
            selected_type = "None"
        rendered = render_to_string('integrations/type_modal.html', {'selected_type': selected_type,
                                                                     'target': '#div_id_additional',
                                                                     'proceed_button': reverse("bridges/schema",
                                                                                               kwargs={
                                                                                                   "integration_type":
                                                                                                       integration_type,
                                                                                                   "integration_id":
                                                                                                       integration_id,
                                                                                                   "update": "true"
                                                                                               }),
                                                                     'cancel_button': reverse(
                                                                         "bridges/dropdown_restore",
                                                                         kwargs={"integration_id": integration_id})})
        return HttpResponse(rendered)

    @staticmethod
    @requires_csrf_token
    def dropdown_restore(request, integration_id):
        type_modal = reverse("bridges/type_modal", kwargs={"integration_id": integration_id})
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
    def schema(request, integration_type, integration_id, update):
        # TODO: We might need to find a way to provide an existing BridgeIntegration object here.
        form = BridgeIntegrationForm(request=request)
        selected_type = BridgeIntegrationType.objects.get(id=integration_type)

        request.session["integration_type"] = integration_type
        # No type selected
        if integration_type == 'none':
            return HttpResponse("Please select an integration type")
        try:
            initial_additional = BridgeIntegration.objects.get(id=integration_id).state or {}
        except BridgeIntegration.DoesNotExist:
            initial_additional = {}        # a new type is selected and schema needs to be updated
        if update == "true":
            if selected_type.configuration_schema != {}:
                request.session["integration_type"] = integration_type
                form.fields['additional'].widget.instance = selected_type.id
            else:
                form.fields['additional'].widget = FormattedJsonFieldWidget()
                form.fields['additional'].initial = initial_additional
            return HttpResponse(as_crispy_field(form["additional"]))

        # loading the schema already associated with the form
        # load the proper schema populated with additional values from the integration

        form.fields['additional'].initial = initial_additional
        
        if selected_type.configuration_schema != {}:
            form.fields['additional'].widget = JSONFormWidget(
                schema=selected_type.configuration_schema,
            )
            form.fields['additional'].initial = selected_integration.additional
        # load a textarea populated with json from the integration
        else:
            form.fields['additional'].widget = FormattedJsonFieldWidget()
            form.fields['additional'].initial = selected_integration.additional
        return HttpResponse(as_crispy_field(form["additional"]))

    def get_object(self):
        configuration = get_object_or_404(BridgeIntegration, pk=self.kwargs.get("id"))
        permission_can_view(self.request, configuration)
        return configuration


def _enabled_icon_response(record, url_name, url_kwargs):
    if record.enabled:
        icon = '<span class="text-success" title="Enabled">&#10003;</span>'
    else:
        icon = '<span class="text-muted" title="Disabled">&#10005;</span>'
    response = HttpResponse(icon)
    response["HX-Trigger"] = json.dumps({
        "tableChanged": None,
        "toggleFeedback": {"enabled": record.enabled, "name": str(record.name)},
    })
    return response


@require_POST
@permission_required("integrations.change_inboundintegrationconfiguration", raise_exception=True)
def toggle_inbound_enabled(request, configuration_id):
    config = get_object_or_404(InboundIntegrationConfiguration, pk=configuration_id)
    permission_can_view(request, config)
    config.enabled = not config.enabled
    config.save(update_fields=["enabled"])
    return _enabled_icon_response(config, "inbound_toggle_enabled", {"configuration_id": config.id})


@require_POST
@permission_required("integrations.change_outboundintegrationconfiguration", raise_exception=True)
def toggle_outbound_enabled(request, configuration_id):
    config = get_object_or_404(OutboundIntegrationConfiguration, pk=configuration_id)
    permission_can_view(request, config)
    config.enabled = not config.enabled
    config.save(update_fields=["enabled"])
    return _enabled_icon_response(config, "outbound_toggle_enabled", {"configuration_id": config.id})


@require_POST
@permission_required("integrations.change_bridgeintegration", raise_exception=True)
def toggle_bridge_enabled(request, id):
    config = get_object_or_404(BridgeIntegration, pk=id)
    permission_can_view(request, config)
    config.enabled = not config.enabled
    config.save(update_fields=["enabled"])
    return _enabled_icon_response(config, "bridge_toggle_enabled", {"id": config.id})


###
# Connections views
###

def _inbound_connections_context(config):
    """Build context dict for the inbound connections partial."""
    default_dg = config.default_devicegroup
    connected_outbound = list(default_dg.destinations.all()) if default_dg else []
    connected_ids = [o.id for o in connected_outbound]

    available_outbound = OutboundIntegrationConfiguration.objects.filter(
        owner=config.owner,
    ).exclude(id__in=connected_ids).order_by("name")

    # Non-default device groups that contain devices from this inbound config
    advanced_groups = DeviceGroup.objects.filter(
        devices__inbound_configuration=config,
    ).exclude(
        id=default_dg.id if default_dg else None,
    ).distinct()

    return {
        "configuration_id": config.id,
        "connected_outbound": connected_outbound,
        "available_outbound": available_outbound,
        "advanced_groups": advanced_groups,
    }


@require_GET
@permission_required("integrations.view_inboundintegrationconfiguration", raise_exception=True)
def inbound_connections_list(request, configuration_id):
    config = get_object_or_404(InboundIntegrationConfiguration, pk=configuration_id)
    permission_can_view(request, config)
    context = _inbound_connections_context(config)
    return render(request, "integrations/inbound_connections_partial.html", context)


@require_POST
@permission_required("integrations.change_inboundintegrationconfiguration", raise_exception=True)
def inbound_connections_add(request, configuration_id):
    config = get_object_or_404(InboundIntegrationConfiguration, pk=configuration_id)
    permission_can_view(request, config)
    outbound_id = request.POST.get("outbound_id")
    outbound = get_object_or_404(OutboundIntegrationConfiguration, pk=outbound_id)
    default_dg = config.default_devicegroup
    default_dg.destinations.add(outbound)
    default_dg.save()
    context = _inbound_connections_context(config)
    return render(request, "integrations/inbound_connections_partial.html", context)


@require_POST
@permission_required("integrations.change_inboundintegrationconfiguration", raise_exception=True)
def inbound_connections_remove(request, configuration_id, outbound_id):
    config = get_object_or_404(InboundIntegrationConfiguration, pk=configuration_id)
    permission_can_view(request, config)
    default_dg = config.default_devicegroup
    default_dg.destinations.remove(outbound_id)
    default_dg.save()
    context = _inbound_connections_context(config)
    return render(request, "integrations/inbound_connections_partial.html", context)


def _device_group_destinations_context(device_group):
    """Build context dict for the device group destinations partial."""
    current_destinations = list(device_group.destinations.all())
    current_ids = [d.id for d in current_destinations]

    available_outbound = OutboundIntegrationConfiguration.objects.filter(
        owner=device_group.owner,
    ).exclude(id__in=current_ids).order_by("name")

    return {
        "device_group_id": device_group.id,
        "current_destinations": current_destinations,
        "available_outbound": available_outbound,
    }


@require_GET
@permission_required("integrations.view_devicegroup", raise_exception=True)
def device_group_destinations_list(request, device_group_id):
    device_group = get_object_or_404(DeviceGroup, pk=device_group_id)
    permission_can_view(request, device_group)
    context = _device_group_destinations_context(device_group)
    return render(request, "integrations/device_group_destinations_partial.html", context)


@require_POST
@permission_required("integrations.change_devicegroup", raise_exception=True)
def device_group_destinations_add(request, device_group_id):
    device_group = get_object_or_404(DeviceGroup, pk=device_group_id)
    permission_can_view(request, device_group)
    outbound_id = request.POST.get("outbound_id")
    outbound = get_object_or_404(OutboundIntegrationConfiguration, pk=outbound_id)
    device_group.destinations.add(outbound)
    device_group.save()
    context = _device_group_destinations_context(device_group)
    return render(request, "integrations/device_group_destinations_partial.html", context)


@require_POST
@permission_required("integrations.change_devicegroup", raise_exception=True)
def device_group_destinations_remove(request, device_group_id, outbound_id):
    device_group = get_object_or_404(DeviceGroup, pk=device_group_id)
    permission_can_view(request, device_group)
    device_group.destinations.remove(outbound_id)
    device_group.save()
    context = _device_group_destinations_context(device_group)
    return render(request, "integrations/device_group_destinations_partial.html", context)


def _outbound_connections_context(config):
    """Build context dict for the outbound connections partial."""
    # Inbound configs whose default_devicegroup routes to this outbound
    connected_inbound = InboundIntegrationConfiguration.objects.filter(
        default_devicegroup__destinations=config,
    ).distinct()

    # Non-default device groups that route to this outbound
    advanced_groups = DeviceGroup.objects.filter(
        destinations=config,
    ).exclude(
        id__in=InboundIntegrationConfiguration.objects.filter(
            default_devicegroup__destinations=config,
        ).values_list("default_devicegroup_id", flat=True),
    ).distinct()

    return {
        "configuration_id": config.id,
        "connected_inbound": connected_inbound,
        "advanced_groups": advanced_groups,
    }


@require_GET
@permission_required("integrations.view_outboundintegrationconfiguration", raise_exception=True)
def outbound_connections_list(request, configuration_id):
    config = get_object_or_404(OutboundIntegrationConfiguration, pk=configuration_id)
    permission_can_view(request, config)
    context = _outbound_connections_context(config)
    return render(request, "integrations/outbound_connections_partial.html", context)


@require_POST
@permission_required("integrations.change_outboundintegrationconfiguration", raise_exception=True)
def outbound_connections_remove(request, configuration_id, inbound_id):
    config = get_object_or_404(OutboundIntegrationConfiguration, pk=configuration_id)
    permission_can_view(request, config)
    inbound = get_object_or_404(InboundIntegrationConfiguration, pk=inbound_id)
    default_dg = inbound.default_devicegroup
    default_dg.destinations.remove(config)
    default_dg.save()
    context = _outbound_connections_context(config)
    return render(request, "integrations/outbound_connections_partial.html", context)


from django.utils.translation import ugettext_lazy as _

import django_filters

from core.permissions import IsGlobalAdmin, IsOrganizationMember
from integrations.models import (
    DeviceState,
    DeviceGroup,
    Device,
    Organization,
    InboundIntegrationType,
    InboundIntegrationConfiguration,
    OutboundIntegrationConfiguration,
    OutboundIntegrationType,
    BridgeIntegration
)
from core.widgets import CustomBooleanWidget
from django.db.models import Q


# set the organization filter options to the organizations that user is member of
def organization_filter(request):
    qs = Organization.objects.order_by("name")
    if not IsGlobalAdmin.has_permission(None, request, None):
        return IsOrganizationMember.filter_queryset_for_user(qs, request.user, "name")
    return qs


# set the type filter options to the types relevant to the organizations that user is member of
def inbound_type_filter(request):
    type_qs = InboundIntegrationType.objects.all()
    if not IsGlobalAdmin.has_permission(None, request, None):
        org_qs = IsOrganizationMember.filter_queryset_for_user(
            Organization.objects.all(), request.user, "name"
        )
        types = Device.objects.filter(
            inbound_configuration__owner__in=org_qs
        ).values_list("inbound_configuration__type")
        type_qs = type_qs.filter(
            inboundintegrationconfiguration__type__in=types
        ).distinct()
    return type_qs


def outbound_integration_filter(request):
    qs = OutboundIntegrationConfiguration.objects.order_by("name")
    if not IsGlobalAdmin.has_permission(None, request, None):
        return IsOrganizationMember.filter_queryset_for_user(qs, request.user, "name")
    return qs


# set the type filter options to the types relevant to the organizations that user is member of
def outbound_type_filter(request):
    type_qs = OutboundIntegrationType.objects.all()
    if not IsGlobalAdmin.has_permission(None, request, None):
        org_qs = IsOrganizationMember.filter_queryset_for_user(
            Organization.objects.all(), request.user, "name"
        )
        type_qs = type_qs.filter(
            outboundintegrationconfiguration__owner__in=org_qs
        ).distinct()
    return type_qs


class DeviceStateFilter(django_filters.FilterSet):

    external_id = django_filters.CharFilter(
        field_name="device__external_id",
        lookup_expr="icontains",
        label=_("External ID"),
    )

    organization = django_filters.ModelChoiceFilter(
        queryset=organization_filter,
        field_name="device__inbound_configuration__owner",
        to_field_name="name",
        empty_label=_("Owners"),
        distinct=True,
    )

    inbound_config_type = django_filters.ModelChoiceFilter(
        queryset=inbound_type_filter,
        field_name="device__inbound_configuration__type",
        to_field_name="name",
        empty_label=_("Types"),
        distinct=True,
    )

    class Meta:
        model = DeviceState
        fields = (
            "organization",
            "inbound_config_type",
            "external_id",
        )

    @property
    def qs(self):
        qs = super().qs
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            return IsOrganizationMember.filter_queryset_for_user(
                qs, self.request.user, "device__inbound_configuration__owner__name"
            )
        else:
            return qs


class DeviceGroupFilter(django_filters.FilterSet):

    device_group = django_filters.CharFilter(
        field_name="name", lookup_expr="icontains", label="Name"
    )

    organization = django_filters.ModelChoiceFilter(
        queryset=organization_filter,
        field_name="owner",
        to_field_name="name",
        empty_label=_("All Organizations"),
        distinct=True,
    )

    destinations = django_filters.ModelChoiceFilter(
        queryset=outbound_integration_filter,
        field_name="destinations",
        to_field_name="name",
        empty_label=_("All Destinations"),
        distinct=True,
    )

    class Meta:
        model = DeviceGroup
        fields = ("organization", "device_group", "destinations")

    def __init__(self, *args, **kwargs):
        # this can appropriately update the ui filter elements
        # check for stored values and set form values accordingly
        super(DeviceGroupFilter, self).__init__(*args, **kwargs)
        if "owner_filter" in self.request.session:
            self.form.initial["organization"] = self.request.session["owner_filter"]

    @property
    def qs(self):
        qs = super().qs
        if "organization" in self.data:
            if not self.data.get("organization"):
                self.request.session.pop("owner_filter", None)
            else:
                self.request.session["owner_filter"] = self.data["organization"]
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            return IsOrganizationMember.filter_queryset_for_user(
                qs, self.request.user, "owner__name"
            )
        if "owner_filter" in self.request.session:
            return qs.filter(owner__name=self.request.session["owner_filter"])
        return qs


class DeviceFilter(django_filters.FilterSet):

    external_id = django_filters.CharFilter(
        field_name="external_id", lookup_expr="icontains", label=_("External ID")
    )

    organization = django_filters.ModelChoiceFilter(
        queryset=organization_filter,
        field_name="inbound_configuration__owner",
        to_field_name="name",
        empty_label=_("Owners"),
        distinct=True,
    )

    inbound_config_type = django_filters.ModelChoiceFilter(
        queryset=inbound_type_filter,
        field_name="inbound_configuration__type",
        to_field_name="name",
        empty_label=_("Types"),
        distinct=True,
    )

    class Meta:
        model = Device
        fields = (
            "organization",
            "inbound_config_type",
            "external_id",
        )

    def __init__(self, *args, **kwargs):
        # this can appropriately update the ui filter elements
        # check for stored values and set form values accordingly
        super(DeviceFilter, self).__init__(*args, **kwargs)
        if "owner_filter" in self.request.session:
            self.form.initial["organization"] = self.request.session["owner_filter"]

    @property
    def qs(self):
        qs = super().qs
        if "organization" in self.data:
            if not self.data.get("organization"):
                self.request.session.pop("owner_filter", None)
            else:
                self.request.session["owner_filter"] = self.data["organization"]
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            return IsOrganizationMember.filter_queryset_for_user(
                qs, self.request.user, "owner__name"
            )
        if "owner_filter" in self.request.session:
            return qs.filter(
                inbound_configuration__owner__name=self.request.session["owner_filter"]
            )
        return qs


class InboundIntegrationFilter(django_filters.FilterSet):

    name = django_filters.CharFilter(
        field_name="name", lookup_expr="icontains", label=_("Name")
    )

    organization = django_filters.ModelChoiceFilter(
        queryset=organization_filter,
        field_name="owner",
        to_field_name="name",
        empty_label=_("All Owners"),
        distinct=True,
    )

    inbound_config_type = django_filters.ModelChoiceFilter(
        queryset=inbound_type_filter,
        field_name="type",
        to_field_name="name",
        empty_label=_("All Types"),
        distinct=True,
    )

    enabled = django_filters.BooleanFilter(widget=CustomBooleanWidget)

    class Meta:
        model = InboundIntegrationConfiguration
        fields = ("organization", "inbound_config_type", "name", "enabled")

    def __init__(self, *args, **kwargs):
        # this can appropriately update the ui filter elements
        # check for stored values and set form values accordingly
        super(InboundIntegrationFilter, self).__init__(*args, **kwargs)
        if "owner_filter" in self.request.session:
            self.form.initial["organization"] = self.request.session["owner_filter"]

    @property
    def qs(self):
        qs = super().qs
        if "organization" in self.data:
            if not self.data.get("organization"):
                self.request.session.pop("owner_filter", None)
            else:
                self.request.session["owner_filter"] = self.data["organization"]
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            return IsOrganizationMember.filter_queryset_for_user(
                qs, self.request.user, "owner__name"
            )
        if "owner_filter" in self.request.session:
            return qs.filter(owner__name=self.request.session["owner_filter"])
        return qs


class OutboundIntegrationFilter(django_filters.FilterSet):
    def affected_destinations_filter(self, request, name, value):
        return OutboundIntegrationConfiguration.objects.filter(
            Q(devicegroup__inbound_integration_configurations__type__name__icontains=value) |
            Q(devicegroup__devices__inbound_configuration__type__name__icontains=value)).order_by('id').distinct('id')

    name = django_filters.CharFilter(
        field_name="name", lookup_expr="icontains", label=_("Name")
    )

    organization = django_filters.ModelChoiceFilter(
        queryset=organization_filter,
        field_name="owner",
        to_field_name="name",
        empty_label=_("All Owners"),
        distinct=True,
    )

    outbound_config_type = django_filters.ModelChoiceFilter(
        queryset=outbound_type_filter,
        field_name="type",
        to_field_name="name",
        empty_label=_("All Outbound Types"),
        distinct=True,
    )

    enabled = django_filters.BooleanFilter(widget=CustomBooleanWidget)

    outbound_affected_destinations = django_filters.ModelChoiceFilter(
        queryset=inbound_type_filter,
        method='affected_destinations_filter',
        to_field_name="name",
        empty_label=_("Inbound Integration Type"),
        field_name="name",
        distinct=True,
    )

    class Meta:
        model = OutboundIntegrationConfiguration
        fields = ("organization", "name", "outbound_config_type", "outbound_affected_destinations", "enabled")

    def __init__(self, *args, **kwargs):
        # this can appropriately update the ui filter elements
        # check for stored values and set form values accordingly
        super(OutboundIntegrationFilter, self).__init__(*args, **kwargs)
        if "owner_filter" in self.request.session:
            self.form.initial["organization"] = self.request.session["owner_filter"]

    @property
    def qs(self):
        qs = super().qs
        if "organization" in self.data:
            if not self.data.get("organization"):
                self.request.session.pop("owner_filter", None)
            else:
                self.request.session["owner_filter"] = self.data["organization"]

        # if "outbound_affected_destinations" in self.data:
        #     # get all device groups associated with the selected inbound type
        #     selected_inbound_type = self.data["outbound_affected_destinations"]
        #     associated_device_groups = InboundIntegrationConfiguration.objects.filter_by(selected_inbound_type)
        #     # get all destination(s) associated with the device groups
        #     self.data["outbound_affected_destinations"] = associated_device_groups

        if not IsGlobalAdmin.has_permission(None, self.request, None):
            return IsOrganizationMember.filter_queryset_for_user(
                qs, self.request.user, "owner__name"
            )
        if "owner_filter" in self.request.session:
            return qs.filter(owner__name=self.request.session["owner_filter"])
        return qs


class BridgeIntegrationFilter(django_filters.FilterSet):
    enabled = django_filters.BooleanFilter(widget=CustomBooleanWidget)

    class Meta:
        model = BridgeIntegration
        fields = ("enabled",)

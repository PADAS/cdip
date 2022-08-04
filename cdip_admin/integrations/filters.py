from django.utils.translation import ugettext_lazy as _

import django_filters

# use this for caching
from django.core.cache import cache

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
)


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
        # check for cached values and set form values accordingly
        super(DeviceGroupFilter, self).__init__(*args, **kwargs)
        org_data = cache.get('org_filter')
        if 'org_data':
            self.form.initial['organization'] = org_data

    @property
    def qs(self):
        qs = super().qs
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            return IsOrganizationMember.filter_queryset_for_user(
                qs, self.request.user, "owner__name"
            )
        # update the cached values if changes were just made
        if 'organization' in self.data:
            cache.set('org_filter', self.data['organization'], None)
        # use qs.filter with organization saved in DeviceFilter
        if cache.get('org_filter'):
            return qs.filter(owner__name=cache.get('org_filter'))

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
        # check for cached values and set form values accordingly
        super(DeviceFilter, self).__init__(*args, **kwargs)
        org_data = cache.get('org_filter')
        if 'org_data':
            self.form.initial['organization'] = org_data

    @property
    def qs(self):
        qs = super().qs
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            return IsOrganizationMember.filter_queryset_for_user(
                qs, self.request.user, "inbound_configuration__owner__name"
            )
        # update the cached values if changes were just made
        if 'organization' in self.data:
            cache.set('org_filter', self.data['organization'], None)
        # use qs.filter with organization saved in DeviceFilter
        if cache.get('org_filter'):
            return qs.filter(inbound_configuration__owner__name=cache.get('org_filter'))

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

    class Meta:
        model = InboundIntegrationConfiguration
        fields = ("organization", "inbound_config_type", "name")

    def __init__(self, *args, **kwargs):
        # this can appropriately update the ui filter elements
        # check for cached values and set form values accordingly
        super(InboundIntegrationFilter, self).__init__(*args, **kwargs)
        org_data = cache.get('org_filter')
        if 'org_data':
            self.form.initial['organization'] = org_data

    @property
    def qs(self):
        qs = super().qs
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            return IsOrganizationMember.filter_queryset_for_user(
                qs, self.request.user, "owner__name"
            )
        # update the cached values if changes were just made
        if 'organization' in self.data:
            cache.set('org_filter', self.data['organization'], None)
        # use qs.filter with organization saved in DeviceFilter
        if cache.get('org_filter'):
            return qs.filter(owner__name=cache.get('org_filter'))

        return qs


class OutboundIntegrationFilter(django_filters.FilterSet):

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
        empty_label=_("All Types"),
        distinct=True,
    )

    class Meta:
        model = OutboundIntegrationConfiguration
        fields = ("organization", "outbound_config_type", "name")

    def __init__(self, *args, **kwargs):
        # this can appropriately update the ui filter elements
        # check for cached values and set form values accordingly
        super(OutboundIntegrationFilter, self).__init__(*args, **kwargs)
        org_data = cache.get('org_filter')
        if 'org_data':
            self.form.initial['organization'] = org_data

    @property
    def qs(self):
        qs = super().qs
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            return IsOrganizationMember.filter_queryset_for_user(
                qs, self.request.user, "owner__name"
            )
        # update the cached values if changes were just made
        if 'organization' in self.data:
            cache.set('org_filter', self.data['organization'], None)
        # use qs.filter with organization saved in DeviceFilter
        if cache.get('org_filter'):
            return qs.filter(owner__name=cache.get('org_filter'))

        return qs

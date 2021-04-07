from django.utils.translation import ugettext_lazy as _

import django_filters

from core.permissions import IsGlobalAdmin, IsOrganizationAdmin
from integrations.models import DeviceState, DeviceGroup, Device, Organization, InboundIntegrationType


def organization_filter(request):
    qs = Organization.objects.order_by('name')
    if not IsGlobalAdmin.has_permission(None, request, None):
        return IsOrganizationAdmin.filter_queryset_for_user(qs, request.user, 'name')
    return qs


def type_filter(request):
    org_qs = Organization.objects.order_by('name')
    if not IsGlobalAdmin.has_permission(None, request, None):
        org_qs = IsOrganizationAdmin.filter_queryset_for_user(org_qs, request.user, 'name')
    # set the type filter options to the types relevant to the organizations that user is member of
    type_qs = DeviceState.objects.filter(device__inbound_configuration__owner__in=org_qs).values_list(
        'device__inbound_configuration__type__name', flat=True).distinct().order_by()
    return type_qs


class DeviceStateFilter(django_filters.FilterSet):

    external_id = django_filters.CharFilter(
        field_name='device__external_id',
        lookup_expr='icontains',
        label=_('External ID'),
    )

    organization = django_filters.ModelChoiceFilter(
        queryset=organization_filter,
        field_name='device__inbound_configuration__owner',
        to_field_name='name',
        empty_label=_('Owners'),
        distinct=True,
    )

    inbound_config_type = django_filters.ModelChoiceFilter(
        queryset=type_filter,
        field_name='device__inbound_configuration__type',
        to_field_name='name',
        empty_label=_('Types'),
        distinct=True,
    )

    class Meta:
        model = DeviceState
        fields = ('organization', 'inbound_config_type', 'external_id',)

    @property
    def qs(self):
        qs = super().qs
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            return IsOrganizationAdmin.filter_queryset_for_user(qs, self.request.user,
                                                                'device__inbound_configuration__owner__name')
        else:
            return qs


class DeviceGroupFilter(django_filters.FilterSet):

    device_group = django_filters.CharFilter(
        field_name='name',
        lookup_expr='icontains',
        label='Name'
    )

    organization = django_filters.ModelChoiceFilter(
        queryset=organization_filter,
        field_name='owner',
        to_field_name='name',
        empty_label=_('Owners'),
        distinct=True,
    )

    class Meta:
        model = DeviceGroup
        fields = ('organization', 'device_group',)

    @property
    def qs(self):
        qs = super().qs
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            return IsOrganizationAdmin.filter_queryset_for_user(qs, self.request.user,
                                                                'owner__name')
        else:
            return qs


class DeviceFilter(django_filters.FilterSet):

    external_id = django_filters.CharFilter(
        field_name='external_id',
        lookup_expr='icontains',
        label=_('External ID')
    )

    organization = django_filters.ModelChoiceFilter(
        queryset = Organization.objects.all().order_by('name'),
        field_name='inbound_configuration__owner',
        to_field_name='name',
        empty_label=_('All Owners'),
        distinct=True,
    )

    inbound_config_type = django_filters.ModelChoiceFilter(
        queryset = InboundIntegrationType.objects.all().order_by('name'),
        field_name='inbound_configuration__type',
        to_field_name='name',
        empty_label=_('All Types'),
        distinct=True,
     )

    class Meta:
        model = Device
        fields = ('organization', 'inbound_config_type', 'external_id',)

from django.utils.translation import ugettext_lazy as _

import django_filters

from integrations.models import DeviceState, DeviceGroup, Device, Organization, InboundIntegrationType


class DeviceStateFilter(django_filters.FilterSet):

    external_id = django_filters.CharFilter(
        field_name='device__external_id',
        lookup_expr='icontains',
        label=_('External ID'),
    )

    organization = django_filters.ModelChoiceFilter(
        queryset = Organization.objects.all().order_by('name'),
        field_name='device__inbound_configuration__owner',
        to_field_name='name',
        empty_label=_('All Owners'),
        distinct=True,
    )

    inbound_config_type = django_filters.ModelChoiceFilter(
        queryset=InboundIntegrationType.objects.all().order_by('name'),
        field_name='device__inbound_configuration__type',
        to_field_name='name',
        empty_label=_('All Types'),
        distinct=True,
    )

    class Meta:
        model = DeviceState
        fields = ('organization', 'inbound_config_type', 'external_id',)


class DeviceGroupFilter(django_filters.FilterSet):

    device_group = django_filters.CharFilter(
        field_name='name',
        lookup_expr='icontains',
        label='Name'
    )

    organization = django_filters.ModelChoiceFilter(
        queryset = Organization.objects.all().order_by('name'),
        field_name='owner',
        to_field_name='name',
        empty_label=_('All Owners'),
        distinct=True,
    )

    class Meta:
        model = DeviceGroup
        fields = ('organization', 'device_group',)


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

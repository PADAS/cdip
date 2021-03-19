import django_filters

from integrations.models import DeviceState, DeviceGroup, Device, Organization, InboundIntegrationType


class DeviceStateFilter(django_filters.FilterSet):

    external_id = django_filters.CharFilter(
        field_name='device__external_id',
        lookup_expr='icontains',
        label="External ID"
    )

    organization = django_filters.ModelChoiceFilter(
        queryset = Organization.objects.all(),
        field_name='device__inbound_configuration__owner',
        to_field_name='name',
        empty_label='All Owners',
    )

    inbound_config_type = django_filters.ModelChoiceFilter(
        queryset=InboundIntegrationType.objects.all(),
        field_name='device__inbound_configuration__type',
        to_field_name='name',
        empty_label='All Types',
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
        queryset = Organization.objects.all(),
        field_name='owner',
        to_field_name='name',
        empty_label='All Owners',
    )

    class Meta:
        model = DeviceGroup
        fields = ('organization', 'device_group',)


class DeviceFilter(django_filters.FilterSet):


    external_id = django_filters.CharFilter(
        field_name='external_id',
        lookup_expr='icontains',
        label="External ID"
    )

    organization = django_filters.ModelChoiceFilter(
        queryset = Organization.objects.all(),
        field_name='inbound_configuration__owner',
        to_field_name='name',
        empty_label='All Owners',
    )

    inbound_config_type = django_filters.ModelChoiceFilter(
        queryset = InboundIntegrationType.objects.all(),
        field_name='inbound_configuration__type',
        to_field_name='name',
        empty_label='All Types',
    )

    class Meta:
        model = Device
        fields = ('organization', 'inbound_config_type', 'external_id',)

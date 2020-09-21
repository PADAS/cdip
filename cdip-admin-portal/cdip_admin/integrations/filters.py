import django_filters

from integrations.models import DeviceState


class DeviceStateFilter(django_filters.FilterSet):

    external_id = django_filters.CharFilter(
        field_name='device__external_id',
        lookup_expr='exact',
        label="External ID"
    )

    inbound_config_type_name = django_filters.CharFilter(
        field_name='device__inbound_configuration__type__name',
        lookup_expr='contains',
        label='Type'
    )

    class Meta:
        model = DeviceState
        fields = ()
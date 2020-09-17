import django_filters

from integrations.models import InboundIntegrationConfiguration, DeviceState


class InboundIntegrationConfigurationFilter(django_filters.FilterSet):
    defaultConfiguration = django_filters.UUIDFilter(
        field_name='defaultConfiguration__id',
        lookup_expr='exact'
    )

    type_slug = django_filters.CharFilter(
        field_name='type__slug',
        lookup_expr='exact'
    )

    type_id = django_filters.UUIDFilter(
        field_name='type__id',
        lookup_expr='exact'
    )

    owner_id = django_filters.UUIDFilter(
        field_name='owner__id',
        lookup_expr='exact'
    )

    class Meta:
        model = InboundIntegrationConfiguration
        fields = ()


class DeviceStateFilter(django_filters.FilterSet):

    # inbound_config_slug = django_filters.CharFilter(
    #     field_name='device__inbound_configuration__slug',
    #     lookup_expr='exact'
    # )

    inbound_config_id = django_filters.UUIDFilter(
        field_name='device__inbound_configuration__id',
        lookup_expr='exact'
    )

    class Meta:
        model = DeviceState
        fields = ()

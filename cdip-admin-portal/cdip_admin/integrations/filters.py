import django_filters

from integrations.models import DeviceState, DeviceGroup


class DeviceStateFilter(django_filters.FilterSet):

    def get_choices(model, field):
        choices = []
        for k in model.objects.values_list(field).distinct():
            choices.append((k[0], k[0]))
        return choices

    external_id = django_filters.CharFilter(
        field_name='device__external_id',
        lookup_expr='icontains',
        label="External ID"
    )

    organization = django_filters.ChoiceFilter(
        choices=get_choices(DeviceState, 'device__inbound_configuration__owner__name'),
        field_name='device__inbound_configuration__owner__name',
        empty_label='All',
    )

    # organization = django_filters.ModelChoiceFilter(
    #     field_name='device__inbound_configuration__owner__name',
    #     queryset=DeviceState.device.get_queryset().model.inbound_configuration.get_queryset().model.owner.get_queryset()
    # )

    inbound_config_type_name = django_filters.CharFilter(
        field_name='device__inbound_configuration__type__name',
        lookup_expr='icontains',
        label='Type'
    )

    class Meta:
        model = DeviceState
        fields = ()


class DeviceGroupFilter(django_filters.FilterSet):

    def get_choices(model, field):
        choices = []
        for k in model.objects.values_list(field).distinct():
            choices.append((k[0], k[0]))
        return choices

    device_group = django_filters.CharFilter(
        field_name='name',
        lookup_expr='icontains',
        label='Name'
    )


    organization = django_filters.ChoiceFilter(
        choices=get_choices(DeviceGroup, 'owner__name'),
        field_name='owner__name',
        empty_label='All',
    )

    class Meta:
        model = DeviceGroup
        fields = ()

import django_filters

from integrations.models import DeviceState, DeviceGroup, Device


def get_choices(model, field):
    """Get choices for a ChoiceFilter dropdown

    Keyword arguments:
    model -- the model to access values on
    field -- the field relative to the model we want to populate dropdown from
    """
    choices = []
    for k in model.objects.values_list(field).distinct():
        choices.append((k[0], k[0]))
    return choices


class DeviceStateFilter(django_filters.FilterSet):

    external_id = django_filters.CharFilter(
        field_name='device__external_id',
        lookup_expr='icontains',
        label="External ID"
    )

    organization = django_filters.ChoiceFilter(
        choices=get_choices(DeviceState, 'device__inbound_configuration__owner__name'),
        field_name='device__inbound_configuration__owner__name',
        empty_label='All Owners',
    )

    inbound_config_type_name = django_filters.ChoiceFilter(
        choices=get_choices(DeviceState, 'device__inbound_configuration__type__name'),
        field_name='device__inbound_configuration__type__name',
        empty_label='All Types',
    )

    class Meta:
        model = DeviceState
        fields = ()


class DeviceGroupFilter(django_filters.FilterSet):

    device_group = django_filters.CharFilter(
        field_name='name',
        lookup_expr='icontains',
        label='Name'
    )


    organization = django_filters.ChoiceFilter(
        choices=get_choices(DeviceGroup, 'owner__name'),
        field_name='owner__name',
        empty_label='All Owners',
    )

    class Meta:
        model = DeviceGroup
        fields = ()


class DeviceFilter(django_filters.FilterSet):

    organization = django_filters.ChoiceFilter(
        choices=get_choices(Device, 'inbound_configuration__owner__name'),
        field_name='inbound_configuration__owner__name',
        empty_label='All Owners',
    )

    inbound_config_type_name = django_filters.ChoiceFilter(
        choices=get_choices(Device, 'inbound_configuration__type__name'),
        field_name='inbound_configuration__type__name',
        empty_label='All Types',
    )

    class Meta:
        model = Device
        fields = ()

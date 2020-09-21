import django_tables2 as tables

from .models import DeviceState


class DeviceStateTable(tables.Table):
    class Meta:
        model = DeviceState
        template_name = "django_tables2/bootstrap4.html"
        fields = ('device__external_id', 'device__inbound_configuration__owner__name',
                  'device__inbound_configuration__type__name', 'end_state', 'created_at')


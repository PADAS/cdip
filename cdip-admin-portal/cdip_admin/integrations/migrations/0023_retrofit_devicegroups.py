# Generated by Django 3.1 on 2021-02-23 00:58

from django.db import migrations


def forward_f(apps, schema_editor):

    DeviceGroup = apps.get_model('integrations', 'DeviceGroup')
    Device = apps.get_model('integrations', 'Device')
    InboundIntegrationConfiguration = apps.get_model('integrations', 'InboundIntegrationConfiguration')

    db_alias = schema_editor.connection.alias

    for iic in InboundIntegrationConfiguration.objects.all():

        # calculate a sensible name
        name = iic.name or str(iic.id)
        dg = DeviceGroup.objects.create(name=f'Default Group for {name}',
                                        owner=iic.owner,
                                        inbound_configuration=iic,
                                        )

        dg.devices.add(*[x for x in Device.objects.filter(inbound_configuration=iic)])

class Migration(migrations.Migration):

    dependencies = [
        ('integrations', '0022_devicegroups'),
    ]

    operations = [
        migrations.RunPython(forward_f, reverse_code=migrations.RunPython.noop),
    ]

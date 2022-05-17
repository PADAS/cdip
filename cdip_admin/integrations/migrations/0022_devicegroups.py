# Generated by Django 3.1 on 2021-02-23 00:58

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("integrations", "0021_insert_devicestate_state_from_end_state"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="device",
            name="outbound_configuration",
        ),
        migrations.RemoveField(
            model_name="inboundintegrationconfiguration",
            name="useAdvancedConfiguration",
        ),
        migrations.RemoveField(
            model_name="inboundintegrationconfiguration",
            name="useDefaultConfiguration",
        ),
        migrations.AddField(
            model_name="inboundintegrationconfiguration",
            name="default_devicegroup",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="inbound_integration_configuration",
                related_query_name="inbound_integration_configurations",
                to="integrations.devicegroup",
                verbose_name="Default Device Group",
            ),
        ),
        migrations.AlterField(
            model_name="devicegroup",
            name="destinations",
            field=models.ManyToManyField(
                blank=True,
                related_name="devicegroups",
                related_query_name="devicegroup",
                to="integrations.OutboundIntegrationConfiguration",
            ),
        ),
        migrations.DeleteModel(
            name="DeviceGroupConfiguration",
        ),
    ]

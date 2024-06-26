# Generated by Django 3.1 on 2021-02-10 23:16

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("integrations", "0018_auto_20210210_1509"),
    ]

    operations = [
        migrations.AddField(
            model_name="devicegroup",
            name="destinations",
            field=models.ManyToManyField(
                blank=True,
                related_name="destinations",
                to="integrations.OutboundIntegrationConfiguration",
            ),
        ),
        migrations.AddField(
            model_name="devicegroup",
            name="inbound_configuration",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="integrations.inboundintegrationconfiguration",
            ),
        ),
        migrations.AlterField(
            model_name="device",
            name="outbound_configuration",
            field=models.ManyToManyField(
                blank=True, to="integrations.OutboundIntegrationConfiguration"
            ),
        ),
        migrations.AlterField(
            model_name="devicegroup",
            name="devices",
            field=models.ManyToManyField(blank=True, to="integrations.Device"),
        ),
    ]

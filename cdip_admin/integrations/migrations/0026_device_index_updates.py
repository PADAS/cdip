# Generated by Django 3.1 on 2021-03-18 15:43

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("integrations", "0025_remove_dg_ic"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="device",
            options={"ordering": ("inbound_configuration", "external_id")},
        ),
        migrations.AlterUniqueTogether(
            name="device",
            unique_together={("inbound_configuration", "external_id")},
        ),
    ]

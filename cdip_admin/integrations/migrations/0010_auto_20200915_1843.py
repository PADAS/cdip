# Generated by Django 3.1 on 2020-09-15 18:43

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("integrations", "0009_auto_20200915_1833"),
    ]

    operations = [
        migrations.RenameField(
            model_name="devicestate",
            old_name="device_id",
            new_name="device",
        ),
    ]

# Generated by Django 3.1 on 2021-02-27 01:21

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("integrations", "0023_retrofit_devicegroups"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="devicegroup",
            name="end_date",
        ),
        migrations.RemoveField(
            model_name="devicegroup",
            name="end_time",
        ),
        migrations.RemoveField(
            model_name="devicegroup",
            name="organization_group",
        ),
        migrations.RemoveField(
            model_name="devicegroup",
            name="start_date",
        ),
        migrations.RemoveField(
            model_name="devicegroup",
            name="start_time",
        ),
    ]

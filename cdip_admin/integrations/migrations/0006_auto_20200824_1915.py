# Generated by Django 3.1 on 2020-08-24 19:15

import django.contrib.postgres.fields.jsonb
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("integrations", "0005_auto_20200824_1913"),
    ]

    operations = [
        migrations.AlterField(
            model_name="device",
            name="cursor",
            field=django.contrib.postgres.fields.jsonb.JSONField(default="{}"),
        ),
        migrations.AlterField(
            model_name="inboundintegrationconfiguration",
            name="cursor",
            field=django.contrib.postgres.fields.jsonb.JSONField(default="{}"),
        ),
        migrations.AlterField(
            model_name="outboundintegrationconfiguration",
            name="cursor",
            field=django.contrib.postgres.fields.jsonb.JSONField(default="{}"),
        ),
    ]

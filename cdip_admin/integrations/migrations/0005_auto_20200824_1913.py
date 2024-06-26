# Generated by Django 3.1 on 2020-08-24 19:13

import django.contrib.postgres.fields.jsonb
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("integrations", "0004_auto_20200712_1046"),
    ]

    operations = [
        migrations.AddField(
            model_name="inboundintegrationtype",
            name="slug",
            field=models.SlugField(default="savannah_tracker", max_length=200),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="outboundintegrationconfiguration",
            name="cursor",
            field=django.contrib.postgres.fields.jsonb.JSONField(default=dict),
        ),
        migrations.AddField(
            model_name="outboundintegrationtype",
            name="slug",
            field=models.SlugField(default="EarthRanger", max_length=200),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="device",
            name="cursor",
            field=django.contrib.postgres.fields.jsonb.JSONField(default=dict),
        ),
        migrations.AlterField(
            model_name="inboundintegrationconfiguration",
            name="cursor",
            field=django.contrib.postgres.fields.jsonb.JSONField(default=dict),
        ),
    ]

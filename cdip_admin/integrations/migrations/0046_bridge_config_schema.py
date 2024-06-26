# Generated by Django 3.2 on 2022-09-21 23:29

from django.db import migrations, models
import django_jsonform.models.fields


class Migration(migrations.Migration):

    dependencies = [
        ('integrations', '0045_help_text_updates'),
    ]

    operations = [
        migrations.AddField(
            model_name='bridgeintegrationtype',
            name='configuration_schema',
            field=models.JSONField(blank=True, default=dict, verbose_name='JSON Schema for configuration value'),
        ),
        migrations.AddField(
            model_name='historicalbridgeintegrationtype',
            name='configuration_schema',
            field=models.JSONField(blank=True, default=dict, verbose_name='JSON Schema for configuration value'),
        ),
        migrations.AlterField(
            model_name='bridgeintegration',
            name='additional',
            field=django_jsonform.models.fields.JSONField(),
        ),
        migrations.AlterField(
            model_name='historicalbridgeintegration',
            name='additional',
            field=django_jsonform.models.fields.JSONField(),
        ),
    ]

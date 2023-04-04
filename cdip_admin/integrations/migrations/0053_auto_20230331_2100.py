# Generated by Django 3.2.15 on 2023-03-31 21:00

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('integrations', '0052_remove_gfw_proxy'),
    ]

    operations = [
        migrations.AddField(
            model_name='historicaloutboundintegrationconfiguration',
            name='configuration',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='outboundintegrationconfiguration',
            name='configuration',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
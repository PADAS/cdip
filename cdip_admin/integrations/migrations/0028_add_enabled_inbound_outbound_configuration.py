# Generated by Django 3.1 on 2021-03-17 17:48

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('integrations', '0027_integrations_meta_options'),
    ]

    operations = [
        migrations.AddField(
            model_name='inboundintegrationconfiguration',
            name='enabled',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='outboundintegrationconfiguration',
            name='enabled',
            field=models.BooleanField(default=True),
        ),
    ]
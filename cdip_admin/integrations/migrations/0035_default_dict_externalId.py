# Generated by Django 3.1.5 on 2021-11-24 14:45

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('integrations', '0034_device_additional'),
    ]

    operations = [
        migrations.AlterField(
            model_name='device',
            name='additional',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]

# Generated by Django 3.2.25 on 2025-02-03 12:36

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('integrations', '0110_integrationaction_crontab_schedule'),
    ]

    operations = [
        migrations.AddField(
            model_name='integrationtype',
            name='help_center_url',
            field=models.URLField(blank=True, default='', null=True),
        ),
    ]

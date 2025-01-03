# Generated by Django 3.2.25 on 2024-10-25 18:51

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('integrations', '0102_integrationaction_ui_schema'),
    ]

    operations = [
        migrations.AddField(
            model_name='integrationwebhook',
            name='ui_schema',
            field=models.JSONField(blank=True, default=dict, verbose_name='UI Schema'),
        ),
    ]
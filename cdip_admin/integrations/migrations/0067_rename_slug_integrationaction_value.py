# Generated by Django 3.2.15 on 2023-04-27 22:25

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('integrations', '0066_integrationaction_type'),
    ]

    operations = [
        migrations.RenameField(
            model_name='integrationaction',
            old_name='slug',
            new_name='value',
        ),
    ]

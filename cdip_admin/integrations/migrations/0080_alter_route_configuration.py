# Generated by Django 3.2.15 on 2023-05-30 21:01

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('integrations', '0079_rename_default_routing_rule_integration_default_route'),
    ]

    operations = [
        migrations.AlterField(
            model_name='route',
            name='configuration',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='routing_rules_by_configuration', to='integrations.routeconfiguration', verbose_name='Route Configuration'),
        ),
    ]

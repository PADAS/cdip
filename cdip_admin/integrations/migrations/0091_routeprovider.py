# Generated by Django 3.2.15 on 2023-11-06 16:29

import activity_log.mixins
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('integrations', '0090_integrationaction_is_periodic_action'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="ALTER TABLE integrations_route_data_providers RENAME TO integrations_routeprovider",
                    reverse_sql="ALTER TABLE integrations_routeprovider RENAME TO integrations_route_data_providers",
                ),
            ],
            state_operations=[
                migrations.CreateModel(
                    name='RouteProvider',
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('integration',
                         models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='integrations.integration')),
                        ('route',
                         models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='integrations.route')),
                    ],
                    options={
                        'abstract': False,
                    },
                    bases=(activity_log.mixins.ChangeLogMixin, models.Model),
                ),
                migrations.AlterField(
                    model_name='route',
                    name='data_providers',
                    field=models.ManyToManyField(
                        blank=True,
                        related_name='routing_rules_by_provider',
                        through='integrations.RouteProvider',
                        to='integrations.Integration',
                        verbose_name='Data Providers',
                    ),
                ),
            ],
        ),
    ]

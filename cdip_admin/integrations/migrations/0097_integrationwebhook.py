# Generated by Django 3.2.25 on 2024-06-03 14:34

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('integrations', '0096_rename_actions_endpoint_integrationtype_service_url'),
    ]

    operations = [
        migrations.CreateModel(
            name='IntegrationWebhook',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=200)),
                ('value', models.SlugField(max_length=200, verbose_name='Value (Identifier)')),
                ('description', models.TextField(blank=True)),
                ('schema', models.JSONField(blank=True, default=dict, verbose_name='JSON Schema')),
                ('integration_type', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='webhook', to='integrations.integrationtype', verbose_name='Integration Type')),
            ],
            options={
                'ordering': ('name',),
            },
        ),
    ]

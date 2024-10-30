# Generated by Django 3.2.25 on 2024-10-30 14:04

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('integrations', '0103_integrationwebhook_ui_schema'),
    ]

    operations = [
        migrations.CreateModel(
            name='IntegrationStatus',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('status', models.CharField(choices=[('healthy', 'Healthy'), ('unhealthy', 'Unhealthy'), ('inactive', 'Inactive')], db_index=True, default='healthy', max_length=20)),
                ('last_delivery', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('integration', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='status', to='integrations.integration')),
            ],
            options={
                'ordering': ('-updated_at',),
            },
        ),
    ]

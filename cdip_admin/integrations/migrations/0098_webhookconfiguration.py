# Generated by Django 3.2.25 on 2024-06-04 21:52

import activity_log.mixins
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('integrations', '0097_integrationwebhook'),
    ]

    operations = [
        migrations.CreateModel(
            name='WebhookConfiguration',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('data', models.JSONField(blank=True, default=dict, verbose_name='JSON Configuration')),
                ('integration', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='webhook_config_by_integration', to='integrations.integration')),
                ('webhook', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='webhook_config_by_webhook', to='integrations.integrationwebhook')),
            ],
            options={
                'ordering': ('-updated_at',),
            },
            bases=(activity_log.mixins.ChangeLogMixin, models.Model),
        ),
    ]
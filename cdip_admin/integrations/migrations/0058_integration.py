# Generated by Django 3.2.15 on 2023-05-02 12:23

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0009_organization_ordering'),
        ('integrations', '0057_integrationaction'),
    ]

    operations = [
        migrations.CreateModel(
            name='Integration',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(blank=True, max_length=200)),
                ('base_url', models.URLField(blank=True, verbose_name='Base URL')),
                ('enabled', models.BooleanField(default=True)),
                ('additional', models.JSONField(blank=True, default=dict, verbose_name='Additional JSON Configuration')),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='integrations_by_owner', to='organizations.organization', verbose_name='Organization')),
                ('type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='integrations_by_type', to='integrations.integrationtype', verbose_name='Integration Type')),
            ],
            options={
                'ordering': ('owner', 'name'),
            },
        ),
    ]

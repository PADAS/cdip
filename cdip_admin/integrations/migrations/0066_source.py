# Generated by Django 3.2.15 on 2023-05-02 12:37

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('integrations', '0065_sourceconfiguration'),
    ]

    operations = [
        migrations.CreateModel(
            name='Source',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(blank=True, max_length=200)),
                ('external_id', models.CharField(max_length=200, verbose_name='External Source ID')),
                ('additional', models.JSONField(blank=True, default=dict, verbose_name='Additional JSON Configuration')),
                ('configuration', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='sources_by_configuration', to='integrations.source', verbose_name='Source Configuration')),
                ('integration', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sources_by_integration', to='integrations.integration')),
            ],
            options={
                'ordering': ('integration', 'external_id'),
                'unique_together': {('integration', 'external_id')},
            },
        ),
    ]

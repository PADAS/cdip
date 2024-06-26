# Generated by Django 3.2.15 on 2023-05-04 19:01

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('integrations', '0071_remove_routingrule_source_filter'),
    ]

    operations = [
        migrations.CreateModel(
            name='SourceFilter',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('type', models.CharField(choices=[('list', 'Select Sources By ID'), ('geoboundary', 'GEO Boundary'), ('time', 'Timeframe')], default='list', max_length=20)),
                ('order_number', models.PositiveIntegerField(db_index=True, default=0)),
                ('name', models.CharField(blank=True, max_length=200)),
                ('description', models.TextField(blank=True)),
                ('selector', models.JSONField(blank=True, default=dict, verbose_name='JSON Selector')),
                ('routing_rule', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='source_filters', to='integrations.routingrule', verbose_name='Routing Rule')),
            ],
            options={
                'ordering': ('order_number',),
            },
        ),
    ]

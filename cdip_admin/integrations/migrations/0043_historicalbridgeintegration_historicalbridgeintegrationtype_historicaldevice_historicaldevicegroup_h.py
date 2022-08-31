# Generated by Django 3.2 on 2022-08-09 21:40

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import fernet_fields.fields
import simple_history.models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('organizations', '0008_auto_20220804_1846'),
        ('integrations', '0042_historicaloutboundintegrationtype'),
    ]

    operations = [
        migrations.CreateModel(
            name='HistoricalSubjectType',
            fields=[
                ('created_at', models.DateTimeField(blank=True, editable=False)),
                ('updated_at', models.DateTimeField(blank=True, editable=False)),
                ('id', models.UUIDField(db_index=True, default=uuid.uuid4)),
                ('value', models.SlugField(max_length=200)),
                ('display_name', models.CharField(max_length=200)),
                ('history_id', models.AutoField(primary_key=True, serialize=False)),
                ('history_date', models.DateTimeField(db_index=True)),
                ('history_change_reason', models.CharField(max_length=100, null=True)),
                ('history_type', models.CharField(choices=[('+', 'Created'), ('~', 'Changed'), ('-', 'Deleted')], max_length=1)),
                ('history_user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'historical subject type',
                'verbose_name_plural': 'historical subject types',
                'ordering': ('-history_date', '-history_id'),
                'get_latest_by': ('history_date', 'history_id'),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name='HistoricalOutboundIntegrationConfiguration',
            fields=[
                ('created_at', models.DateTimeField(blank=True, editable=False)),
                ('updated_at', models.DateTimeField(blank=True, editable=False)),
                ('id', models.UUIDField(db_index=True, default=uuid.uuid4)),
                ('name', models.CharField(blank=True, max_length=200)),
                ('state', models.JSONField(blank=True, null=True)),
                ('endpoint', models.URLField(blank=True)),
                ('login', models.CharField(blank=True, max_length=200)),
                ('password', fernet_fields.fields.EncryptedCharField(blank=True, max_length=200)),
                ('token', fernet_fields.fields.EncryptedCharField(blank=True, max_length=200)),
                ('additional', models.JSONField(blank=True, default=dict)),
                ('enabled', models.BooleanField(default=True)),
                ('history_id', models.AutoField(primary_key=True, serialize=False)),
                ('history_date', models.DateTimeField(db_index=True)),
                ('history_change_reason', models.CharField(max_length=100, null=True)),
                ('history_type', models.CharField(choices=[('+', 'Created'), ('~', 'Changed'), ('-', 'Deleted')], max_length=1)),
                ('history_user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('owner', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='organizations.organization')),
                ('type', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='integrations.outboundintegrationtype')),
            ],
            options={
                'verbose_name': 'historical outbound integration configuration',
                'verbose_name_plural': 'historical outbound integration configurations',
                'ordering': ('-history_date', '-history_id'),
                'get_latest_by': ('history_date', 'history_id'),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name='HistoricalGFWInboundConfiguration',
            fields=[
                ('created_at', models.DateTimeField(blank=True, editable=False)),
                ('updated_at', models.DateTimeField(blank=True, editable=False)),
                ('id', models.UUIDField(db_index=True, default=uuid.uuid4)),
                ('name', models.CharField(blank=True, max_length=200)),
                ('endpoint', models.URLField(blank=True)),
                ('state', models.JSONField(blank=True, null=True)),
                ('login', models.CharField(blank=True, max_length=200)),
                ('password', fernet_fields.fields.EncryptedCharField(blank=True, max_length=200)),
                ('token', fernet_fields.fields.EncryptedCharField(blank=True, max_length=200)),
                ('provider', models.CharField(blank=True, help_text="This value will be used as the 'provider_key' when sending data to EarthRanger.", max_length=200, verbose_name='Provider_key')),
                ('enabled', models.BooleanField(default=True)),
                ('consumer_id', models.CharField(blank=True, max_length=200)),
                ('history_id', models.AutoField(primary_key=True, serialize=False)),
                ('history_date', models.DateTimeField(db_index=True)),
                ('history_change_reason', models.CharField(max_length=100, null=True)),
                ('history_type', models.CharField(choices=[('+', 'Created'), ('~', 'Changed'), ('-', 'Deleted')], max_length=1)),
                ('default_devicegroup', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', related_query_name='inbound_integration_configurations', to='integrations.devicegroup', verbose_name='Default Device Group')),
                ('history_user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('owner', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='organizations.organization')),
                ('type', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='integrations.inboundintegrationtype')),
            ],
            options={
                'verbose_name': 'historical gfw inbound configuration',
                'verbose_name_plural': 'historical gfw inbound configurations',
                'ordering': ('-history_date', '-history_id'),
                'get_latest_by': ('history_date', 'history_id'),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name='HistoricalDeviceState',
            fields=[
                ('created_at', models.DateTimeField(blank=True, editable=False)),
                ('updated_at', models.DateTimeField(blank=True, editable=False)),
                ('id', models.UUIDField(db_index=True, default=uuid.uuid4)),
                ('end_state', models.CharField(max_length=200)),
                ('state', models.JSONField(blank=True, null=True)),
                ('history_id', models.AutoField(primary_key=True, serialize=False)),
                ('history_date', models.DateTimeField(db_index=True)),
                ('history_change_reason', models.CharField(max_length=100, null=True)),
                ('history_type', models.CharField(choices=[('+', 'Created'), ('~', 'Changed'), ('-', 'Deleted')], max_length=1)),
                ('device', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='integrations.device')),
                ('history_user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'historical device state',
                'verbose_name_plural': 'historical device states',
                'ordering': ('-history_date', '-history_id'),
                'get_latest_by': ('history_date', 'history_id'),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name='HistoricalDeviceGroup',
            fields=[
                ('created_at', models.DateTimeField(blank=True, editable=False)),
                ('updated_at', models.DateTimeField(blank=True, editable=False)),
                ('id', models.UUIDField(db_index=True, default=uuid.uuid4)),
                ('name', models.CharField(max_length=200)),
                ('history_id', models.AutoField(primary_key=True, serialize=False)),
                ('history_date', models.DateTimeField(db_index=True)),
                ('history_change_reason', models.CharField(max_length=100, null=True)),
                ('history_type', models.CharField(choices=[('+', 'Created'), ('~', 'Changed'), ('-', 'Deleted')], max_length=1)),
                ('default_subject_type', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='integrations.subjecttype')),
                ('history_user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('owner', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='organizations.organization')),
            ],
            options={
                'verbose_name': 'historical device group',
                'verbose_name_plural': 'historical device groups',
                'ordering': ('-history_date', '-history_id'),
                'get_latest_by': ('history_date', 'history_id'),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name='HistoricalDevice',
            fields=[
                ('created_at', models.DateTimeField(blank=True, editable=False)),
                ('updated_at', models.DateTimeField(blank=True, editable=False)),
                ('id', models.UUIDField(db_index=True, default=uuid.uuid4)),
                ('name', models.CharField(blank=True, max_length=200)),
                ('external_id', models.CharField(max_length=200)),
                ('additional', models.JSONField(blank=True, default=dict)),
                ('history_id', models.AutoField(primary_key=True, serialize=False)),
                ('history_date', models.DateTimeField(db_index=True)),
                ('history_change_reason', models.CharField(max_length=100, null=True)),
                ('history_type', models.CharField(choices=[('+', 'Created'), ('~', 'Changed'), ('-', 'Deleted')], max_length=1)),
                ('history_user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('inbound_configuration', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='integrations.inboundintegrationconfiguration')),
                ('subject_type', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='integrations.subjecttype')),
            ],
            options={
                'verbose_name': 'historical device',
                'verbose_name_plural': 'historical devices',
                'ordering': ('-history_date', '-history_id'),
                'get_latest_by': ('history_date', 'history_id'),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name='HistoricalBridgeIntegrationType',
            fields=[
                ('created_at', models.DateTimeField(blank=True, editable=False)),
                ('updated_at', models.DateTimeField(blank=True, editable=False)),
                ('id', models.UUIDField(db_index=True, default=uuid.uuid4)),
                ('name', models.CharField(max_length=200, verbose_name='Type')),
                ('slug', models.SlugField(max_length=200)),
                ('description', models.TextField(blank=True)),
                ('history_id', models.AutoField(primary_key=True, serialize=False)),
                ('history_date', models.DateTimeField(db_index=True)),
                ('history_change_reason', models.CharField(max_length=100, null=True)),
                ('history_type', models.CharField(choices=[('+', 'Created'), ('~', 'Changed'), ('-', 'Deleted')], max_length=1)),
                ('history_user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'historical bridge integration type',
                'verbose_name_plural': 'historical bridge integration types',
                'ordering': ('-history_date', '-history_id'),
                'get_latest_by': ('history_date', 'history_id'),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name='HistoricalBridgeIntegration',
            fields=[
                ('created_at', models.DateTimeField(blank=True, editable=False)),
                ('updated_at', models.DateTimeField(blank=True, editable=False)),
                ('id', models.UUIDField(db_index=True, default=uuid.uuid4)),
                ('name', models.CharField(blank=True, max_length=200)),
                ('state', models.JSONField(blank=True, null=True)),
                ('additional', models.JSONField(blank=True, default=dict)),
                ('enabled', models.BooleanField(default=True)),
                ('consumer_id', models.CharField(blank=True, max_length=200)),
                ('history_id', models.AutoField(primary_key=True, serialize=False)),
                ('history_date', models.DateTimeField(db_index=True)),
                ('history_change_reason', models.CharField(max_length=100, null=True)),
                ('history_type', models.CharField(choices=[('+', 'Created'), ('~', 'Changed'), ('-', 'Deleted')], max_length=1)),
                ('history_user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('owner', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='organizations.organization')),
                ('type', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='integrations.bridgeintegrationtype')),
            ],
            options={
                'verbose_name': 'historical bridge integration',
                'verbose_name_plural': 'historical bridge integrations',
                'ordering': ('-history_date', '-history_id'),
                'get_latest_by': ('history_date', 'history_id'),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
    ]

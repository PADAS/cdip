# Generated by Django 3.1 on 2020-09-15 18:33

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('integrations', '0008_auto_20200826_1907'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='device',
            name='state',
        ),
        migrations.AddField(
            model_name='device',
            name='outbound_configuration',
            field=models.ManyToManyField(to='integrations.OutboundIntegrationConfiguration'),
        ),
        migrations.AlterField(
            model_name='device',
            name='type',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='integrations.inboundintegrationconfiguration'),
        ),
        migrations.CreateModel(
            name='DeviceState',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('end_state', models.CharField(max_length=200)),
                ('device_id', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='integrations.device')),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
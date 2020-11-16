# Generated by Django 3.1 on 2020-11-11 22:02

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('integrations', '0013_inboundintegrationconfiguration_encrypted_password_field'),
        ('clients', '0002_auto_20200827_1718'),
    ]

    operations = [
        migrations.CreateModel(
            name='ClientScope',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('scope', models.CharField(max_length=200)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.AddField(
            model_name='clientprofile',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='clientprofile',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.CreateModel(
            name='OutboundClientResource',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('resource', models.CharField(max_length=200)),
                ('scopes', models.ManyToManyField(to='clients.ClientScope')),
                ('type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='integrations.outboundintegrationtype')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='InboundClientResource',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('resource', models.CharField(max_length=200)),
                ('scopes', models.ManyToManyField(to='clients.ClientScope')),
                ('type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='integrations.inboundintegrationtype')),
            ],
            options={
                'abstract': False,
            },
        ),
    ]

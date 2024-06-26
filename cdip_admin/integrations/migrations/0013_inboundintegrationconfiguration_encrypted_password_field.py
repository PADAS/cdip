# NOT auto-generated by Django

from django.db import migrations, models
import fernet_fields.fields


class Migration(migrations.Migration):

    dependencies = [
        ("integrations", "0012_device_state_index"),
    ]

    operations = [
        migrations.AlterField(
            model_name="inboundintegrationtype",
            name="name",
            field=models.CharField(max_length=200, verbose_name="Type"),
        ),
        migrations.RemoveField(
            model_name="inboundintegrationconfiguration",
            name="password",
        ),
        migrations.RemoveField(
            model_name="inboundintegrationconfiguration",
            name="token",
        ),
        migrations.RemoveField(
            model_name="outboundintegrationconfiguration",
            name="password",
        ),
        migrations.RemoveField(
            model_name="outboundintegrationconfiguration",
            name="token",
        ),
        migrations.AddField(
            model_name="inboundintegrationconfiguration",
            name="password",
            field=fernet_fields.fields.EncryptedCharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="inboundintegrationconfiguration",
            name="token",
            field=fernet_fields.fields.EncryptedCharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="outboundintegrationconfiguration",
            name="password",
            field=fernet_fields.fields.EncryptedCharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="outboundintegrationconfiguration",
            name="token",
            field=fernet_fields.fields.EncryptedCharField(blank=True, max_length=200),
        ),
    ]

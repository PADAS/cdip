# Generated by Django 3.1 on 2020-08-26 19:07

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('integrations', '0008_auto_20200826_1907'),
    ]

    operations = [
        migrations.CreateModel(
            name='ClientProfile',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=200)),
                ('client_id', models.CharField(max_length=200)),
                ('type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='integrations.inboundintegrationtype')),
            ],
        ),
    ]
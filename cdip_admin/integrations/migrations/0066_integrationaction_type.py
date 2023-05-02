# Generated by Django 3.2.15 on 2023-04-26 13:16

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('integrations', '0065_alter_integrationaction_slug'),
    ]

    operations = [
        migrations.AddField(
            model_name='integrationaction',
            name='type',
            field=models.CharField(choices=[('auth', 'Authentication'), ('pull', 'Pull Data'), ('push', 'Push Data'), ('generic', 'Generic Action')], default='generic', max_length=20),
        ),
    ]
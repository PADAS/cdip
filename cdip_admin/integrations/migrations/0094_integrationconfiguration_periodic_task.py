# Generated by Django 3.2.15 on 2024-01-30 15:47

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('django_celery_beat', '0018_improve_crontab_helptext'),
        ('integrations', '0093_alter_integration_default_route'),
    ]

    operations = [
        migrations.AddField(
            model_name='integrationconfiguration',
            name='periodic_task',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='configurations_by_periodic_task', to='django_celery_beat.periodictask'),
        ),
    ]

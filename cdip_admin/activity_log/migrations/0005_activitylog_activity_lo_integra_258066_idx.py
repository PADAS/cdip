# Generated by Django 3.2.25 on 2024-10-24 13:38

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('activity_log', '0004_activitylog_partitions_idx'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='activitylog',
            index=models.Index(fields=['integration', '-created_at'], name='activity_lo_integra_258066_idx'),
        ),
    ]

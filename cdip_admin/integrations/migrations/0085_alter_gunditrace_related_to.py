# Generated by Django 3.2.15 on 2023-07-13 21:29

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('integrations', '0084_alter_gunditrace_delivered_at'),
    ]

    operations = [
        migrations.AlterField(
            model_name='gunditrace',
            name='related_to',
            field=models.UUIDField(blank=True, db_index=True, null=True),
        ),
    ]

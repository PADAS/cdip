# Generated by Django 3.2.15 on 2023-05-03 14:54

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('integrations', '0067_auto_20230502_1240'),
    ]

    operations = [
        migrations.RenameField(
            model_name='routingruletype',
            old_name='slug',
            new_name='value',
        ),
    ]

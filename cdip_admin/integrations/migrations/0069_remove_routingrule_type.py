# Generated by Django 3.2.15 on 2023-05-04 18:12

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('integrations', '0068_rename_slug_routingruletype_value'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='routingrule',
            name='type',
        ),
    ]
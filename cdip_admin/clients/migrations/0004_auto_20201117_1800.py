# Generated by Django 3.1 on 2020-11-17 18:00

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("clients", "0003_auto_20201111_2202"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="ClientScope",
            new_name="AuthorizationScope",
        ),
    ]

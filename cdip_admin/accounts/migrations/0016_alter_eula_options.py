# Generated by Django 3.2.25 on 2024-05-06 13:16

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0015_eula_unique_active_eula'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='eula',
            options={'ordering': ['-created_at']},
        ),
    ]
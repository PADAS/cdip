# Generated by Django 3.2.15 on 2023-08-09 20:01

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('deployments', '0007_dispatcherdeployment_topic_path'),
    ]

    operations = [
        migrations.RenameField(
            model_name='dispatcherdeployment',
            old_name='topic_path',
            new_name='topic_name',
        ),
    ]

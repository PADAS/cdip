# Generated by Django 3.2.15 on 2023-08-09 19:40

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('deployments', '0006_alter_dispatcherdeployment_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='dispatcherdeployment',
            name='topic_path',
            field=models.CharField(blank=True, default='', max_length=500, null=True),
        ),
    ]

# Generated by Django 3.2.15 on 2023-07-19 14:56

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('deployments', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='dispatcherdeployment',
            name='status_details',
            field=models.CharField(blank=True, default='', max_length=500, null=True),
        ),
    ]

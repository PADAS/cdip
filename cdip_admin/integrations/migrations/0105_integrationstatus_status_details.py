# Generated by Django 3.2.25 on 2024-10-30 14:16

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('integrations', '0104_integrationstatus'),
    ]

    operations = [
        migrations.AddField(
            model_name='integrationstatus',
            name='status_details',
            field=models.CharField(blank=True, default='', max_length=200),
        ),
    ]
# Generated by Django 3.2.15 on 2023-05-01 18:51

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('integrations', '0078_auto_20230428_1403'),
    ]

    operations = [
        migrations.AlterField(
            model_name='source',
            name='configuration',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='sources_by_configuration', to='integrations.source'),
        ),
    ]

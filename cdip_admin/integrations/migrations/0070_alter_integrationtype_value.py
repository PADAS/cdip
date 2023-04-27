# Generated by Django 3.2.15 on 2023-04-27 22:26

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('integrations', '0069_rename_slug_integrationtype_value'),
    ]

    operations = [
        migrations.AlterField(
            model_name='integrationtype',
            name='value',
            field=models.SlugField(max_length=200, unique=True, verbose_name='Value (Identifier)'),
        ),
    ]

# Generated by Django 3.2.15 on 2023-04-26 12:36

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('integrations', '0064_alter_integrationaction_name'),
    ]

    operations = [
        migrations.AlterField(
            model_name='integrationaction',
            name='slug',
            field=models.SlugField(max_length=200, verbose_name='Slug Identifier'),
        ),
    ]

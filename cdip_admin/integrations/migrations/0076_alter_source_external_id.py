# Generated by Django 3.2.15 on 2023-05-16 13:39

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('integrations', '0075_alter_source_configuration'),
    ]

    operations = [
        migrations.AlterField(
            model_name='source',
            name='external_id',
            field=models.CharField(db_index=True, max_length=200, verbose_name='External Source ID'),
        ),
    ]
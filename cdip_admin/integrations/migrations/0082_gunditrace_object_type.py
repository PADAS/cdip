# Generated by Django 3.2.15 on 2023-06-09 12:18

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('integrations', '0081_auto_20230608_1303'),
    ]

    operations = [
        migrations.AddField(
            model_name='gunditrace',
            name='object_type',
            field=models.CharField(blank=True, db_index=True, max_length=5),
        ),
    ]

# Generated by Django 3.1 on 2021-02-10 12:56

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('integrations', '0015_auto_20210121_1533'),
    ]

    operations = [
        migrations.AlterField(
            model_name='devicegroup',
            name='end_date',
            field=models.DateField(null=True),
        ),
        migrations.AlterField(
            model_name='devicegroup',
            name='end_time',
            field=models.TimeField(null=True),
        ),
        migrations.AlterField(
            model_name='devicegroup',
            name='start_date',
            field=models.DateField(null=True),
        ),
        migrations.AlterField(
            model_name='devicegroup',
            name='start_time',
            field=models.TimeField(null=True),
        ),
    ]
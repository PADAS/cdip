# Generated by Django 3.2.15 on 2023-05-04 21:21

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('integrations', '0072_sourcefilter'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='sourcefilter',
            options={'ordering': ('routing_rule', 'order_number')},
        ),
    ]

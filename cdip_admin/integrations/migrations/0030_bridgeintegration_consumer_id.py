# Generated by Django 3.1 on 2021-05-10 18:50

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("integrations", "0029_bridge"),
    ]

    operations = [
        migrations.AddField(
            model_name="bridgeintegration",
            name="consumer_id",
            field=models.CharField(blank=True, max_length=200),
        ),
    ]

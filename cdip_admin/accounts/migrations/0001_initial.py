# Generated by Django 3.0.7 on 2020-08-18 17:06

from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("organizations", "0003_auto_20200701_1357"),
    ]

    operations = [
        migrations.CreateModel(
            name="AccountProfile",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, primary_key=True, serialize=False
                    ),
                ),
                ("user_id", models.CharField(max_length=200)),
                (
                    "organizations",
                    models.ManyToManyField(to="organizations.Organization"),
                ),
            ],
        ),
    ]

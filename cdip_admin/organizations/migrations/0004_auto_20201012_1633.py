# Generated by Django 3.1 on 2020-10-12 16:33

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("organizations", "0003_auto_20200701_1357"),
    ]

    operations = [
        migrations.AlterField(
            model_name="organization",
            name="name",
            field=models.CharField(max_length=200, verbose_name="Owner"),
        ),
        migrations.AlterField(
            model_name="userprofile",
            name="organizations",
            field=models.ManyToManyField(
                related_name="user_profiles",
                related_query_name="user_profile",
                to="organizations.Organization",
            ),
        ),
        migrations.AlterField(
            model_name="userprofile",
            name="user",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="user_profiles",
                related_query_name="user_profile",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('integrations', '0125_sourcefilter_include_default_source'),
    ]

    operations = [
        migrations.AddField(
            model_name='gunditrace',
            name='is_destination_copy',
            field=models.BooleanField(
                blank=True,
                help_text=(
                    "True on rows the event consumers add for each additional destination of an item; "
                    "null or false marks the original row. Exclude copies when counting received items."
                ),
                null=True,
            ),
        ),
    ]

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Finish SourceFilter: per-destination scope, whitelist/blacklist mode, and the
    Source references the rule needs.

    `integrations_sourcefilter` is empty in production, verified before writing this, so
    the new non-nullable columns land without a backfill. `destination` is added nullable
    and then altered to NOT NULL rather than given a one-off default, so that if the table
    ever stops being empty the migration fails loudly instead of inventing a foreign key.
    """

    dependencies = [
        ("integrations", "0117_alter_integrationaction_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="sourcefilter",
            name="mode",
            field=models.CharField(
                choices=[("whitelist", "Whitelist"), ("blacklist", "Blacklist")],
                default="",
                max_length=20,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="sourcefilter",
            name="destination",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="source_filters_by_destination",
                to="integrations.integration",
                verbose_name="Destination",
            ),
        ),
        migrations.AlterField(
            model_name="sourcefilter",
            name="destination",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="source_filters_by_destination",
                to="integrations.integration",
                verbose_name="Destination",
            ),
        ),
        migrations.AddField(
            model_name="sourcefilter",
            name="sources",
            field=models.ManyToManyField(
                blank=True,
                related_name="source_filters_by_source",
                to="integrations.source",
                verbose_name="Sources",
            ),
        ),
        migrations.AddField(
            model_name="sourcefilter",
            name="enabled",
            field=models.BooleanField(default=True),
        ),
        migrations.AddConstraint(
            model_name="sourcefilter",
            constraint=models.UniqueConstraint(
                fields=("routing_rule", "destination", "type"),
                name="unique_source_filter_per_route_destination_type",
            ),
        ),
    ]

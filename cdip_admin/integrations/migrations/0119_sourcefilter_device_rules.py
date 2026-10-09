import django.db.models.deletion
from django.db import migrations, models


def drop_pre_feature_rows(apps, schema_editor):
    # Any row that exists before this migration predates the feature: it has no
    # destination (the column lands here), so it cannot satisfy the NOT NULL below
    # and was never readable by the routing block. Production is verified empty;
    # dev/stage may hold prototype leftovers, and main deploys straight to dev,
    # so they are removed explicitly instead of failing the deploy.
    SourceFilter = apps.get_model("integrations", "SourceFilter")
    deleted, _ = SourceFilter.objects.all().delete()
    if deleted:
        print(f"0119: removed {deleted} pre-feature SourceFilter row(s)")


class Migration(migrations.Migration):
    """Finish SourceFilter: per-destination scope, whitelist/blacklist mode, and the
    Source references the rule needs.

    `integrations_sourcefilter` is empty in production (verified) and any earlier row
    is unusable prototype data — `destination` did not exist, so nothing ever routed
    by it — hence the explicit cleanup instead of inventing a foreign key to backfill
    the new NOT NULL column.
    """

    dependencies = [
        ("integrations", "0118_integration_default_route_on_delete"),
    ]

    operations = [
        migrations.RunPython(drop_pre_feature_rows, migrations.RunPython.noop),
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

from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models


class Migration(migrations.Migration):
    # CONCURRENTLY cannot run inside a transaction; on the largest table a
    # regular build would block ingestion writes for its duration. Partial:
    # discarded rows are the rare, selective side (isnull=true matches most of
    # the table and would not use an index anyway).
    atomic = False

    dependencies = [
        ("integrations", "0119_gunditrace_discard_fields"),
    ]

    operations = [
        AddIndexConcurrently(
            model_name="gunditrace",
            index=models.Index(
                fields=["discarded_at"],
                name="gunditrace_discarded_idx",
                condition=models.Q(discarded_at__isnull=False),
            ),
        ),
    ]

from django.db import migrations, models


def dedupe_integration_configurations(apps, schema_editor):
    # Defensively remove any existing duplicate (integration, action) pairs
    # before adding the unique constraint. The previous create_missing_configurations
    # had a non-atomic exists+create that could race under concurrent calls,
    # so production may have stray duplicates.
    #
    # Winner-selection priority (preserve the meaningful row):
    #   1. row with non-empty `data`
    #   2. row with a periodic_task attached
    #   3. most recently updated row
    # Loser rows have their PeriodicTask manually deleted before the row
    # itself goes — historical-model `delete()` does not fire the
    # pre_delete signal that normally cleans the task up.
    IntegrationConfiguration = apps.get_model("integrations", "IntegrationConfiguration")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    duplicate_keys = (
        IntegrationConfiguration.objects.values("integration_id", "action_id")
        .annotate(row_count=models.Count("id"))
        .filter(row_count__gt=1)
    )

    for key in duplicate_keys:
        rows = list(
            IntegrationConfiguration.objects.filter(
                integration_id=key["integration_id"],
                action_id=key["action_id"],
            )
        )

        def winner_score(row):
            return (
                bool(row.data),                 # has meaningful payload
                row.periodic_task_id is not None,  # has scheduled task
                row.updated_at,                 # most recent edit
            )

        winner = max(rows, key=winner_score)

        # If the winner has no PeriodicTask but a loser does, that's the only
        # live schedule for this (integration, action) pair — move it onto the
        # winner before the delete loop runs, so we don't drop a periodic
        # action's scheduler. The OneToOne constraint requires we null the
        # donor's FK first.
        if not winner.periodic_task_id:
            donor = next(
                (r for r in rows if r.pk != winner.pk and r.periodic_task_id),
                None,
            )
            if donor:
                task_id = donor.periodic_task_id
                donor.periodic_task_id = None
                donor.save(update_fields=["periodic_task"])
                winner.periodic_task_id = task_id
                winner.save(update_fields=["periodic_task"])

        for row in rows:
            if row.pk == winner.pk:
                continue
            row.refresh_from_db()
            if row.periodic_task_id:
                # pre_delete on the historical IntegrationConfiguration is not
                # wired up, so clean its PeriodicTask explicitly. Any loser
                # task remaining here is a stale duplicate (the winner already
                # took its preferred schedule above).
                PeriodicTask.objects.filter(pk=row.periodic_task_id).delete()
            row.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("integrations", "0114_auto_20250207_1254"),
    ]

    operations = [
        migrations.RunPython(
            dedupe_integration_configurations,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name="integrationconfiguration",
            constraint=models.UniqueConstraint(
                fields=["integration", "action"],
                name="unique_integration_action_configuration",
            ),
        ),
    ]

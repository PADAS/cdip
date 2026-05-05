from django.db import migrations, models


def dedupe_integration_configurations(apps, schema_editor):
    # Defensively remove any existing duplicate (integration, action) pairs
    # before adding the unique constraint. The previous create_missing_configurations
    # had a non-atomic exists+create that could race under concurrent calls,
    # so production may have stray duplicates. Keep the oldest row (smallest
    # created_at) since downstream PeriodicTask references hang off it.
    IntegrationConfiguration = apps.get_model("integrations", "IntegrationConfiguration")
    duplicates = (
        IntegrationConfiguration.objects.values("integration_id", "action_id")
        .annotate(row_count=models.Count("id"))
        .filter(row_count__gt=1)
    )
    for dup in duplicates:
        rows = IntegrationConfiguration.objects.filter(
            integration_id=dup["integration_id"],
            action_id=dup["action_id"],
        ).order_by("created_at", "id")
        keep = rows.first()
        rows.exclude(pk=keep.pk).delete()


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

from django.db import migrations

GROUP_NAME = "MetricsViewer"  # mirror core.enums.DjangoGroups.METRICS_VIEWER


def create_metrics_viewer_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name=GROUP_NAME)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0007_create_access_groups"),
        ("auth", "0001_initial"),
    ]

    operations = [
        # The reverse keeps the group: deleting it would drop its memberships.
        migrations.RunPython(create_metrics_viewer_group, migrations.RunPython.noop),
    ]

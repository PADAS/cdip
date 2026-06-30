from django.db import migrations

GROUP_NAMES = ("GlobalAdmin", "OrganizationMember")  # mirror core.enums.DjangoGroups


def create_access_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    for name in GROUP_NAMES:
        Group.objects.get_or_create(name=name)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0006_alter_task_id"),
        ("auth", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_access_groups, migrations.RunPython.noop),
    ]

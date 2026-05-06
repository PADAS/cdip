from django.core.management.base import BaseCommand, CommandError

from integrations.models import Integration, IntegrationType


class Command(BaseCommand):
    help = (
        "Backfill missing IntegrationConfiguration rows for integrations whose "
        "IntegrationType has gained actions since they were created."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--integration",
            type=str,
            help="Repair a single integration by ID.",
        )
        parser.add_argument(
            "--integration-type",
            type=str,
            help="Repair all integrations of a given type (by slug value).",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help=(
                "Repair every integration in the database. Required to opt in "
                "explicitly when neither --integration nor --integration-type is "
                "given, since this mutates production data globally."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be created without writing.",
        )

    def handle(self, *args, **options):
        integration_id = options.get("integration")
        integration_type_slug = options.get("integration_type")
        repair_all = options.get("all", False)
        dry_run = options.get("dry_run", False)

        selector_count = sum(
            1 for sel in (integration_id, integration_type_slug, repair_all) if sel
        )
        if selector_count == 0:
            raise CommandError(
                "Refusing to run without a target. Pass --integration <uuid>, "
                "--integration-type <slug>, or --all to repair every integration."
            )
        if selector_count > 1:
            raise CommandError(
                "Pass exactly one of --integration, --integration-type, or --all. "
                "Combining selectors is rejected so a mistyped flag can't silently "
                "mutate a different scope than intended."
            )

        qs = Integration.objects.all().select_related("type")
        if integration_id:
            qs = qs.filter(id=integration_id)
            if not qs.exists():
                raise CommandError(f"Integration '{integration_id}' not found.")
        elif integration_type_slug:
            try:
                integration_type = IntegrationType.objects.get(value=integration_type_slug)
            except IntegrationType.DoesNotExist:
                raise CommandError(
                    f"Integration type '{integration_type_slug}' not found."
                )
            qs = qs.filter(type=integration_type)

        # Cache actions per type so iterating across many integrations of the
        # same type doesn't re-query the action set every time. The
        # configurations query is per-integration by necessity (each row is
        # unique to that integration), but type.actions is shared.
        actions_by_type = {}
        total_created = 0
        integrations_touched = 0
        for integration in qs.iterator():
            if integration.type_id not in actions_by_type:
                actions_by_type[integration.type_id] = list(integration.type.actions.all())
            actions = actions_by_type[integration.type_id]

            existing_action_ids = set(
                integration.configurations.values_list("action_id", flat=True)
            )
            missing = [a for a in actions if a.id not in existing_action_ids]
            if not missing:
                continue
            integrations_touched += 1
            self.stdout.write(
                f"{integration.id} ({integration.name}): missing "
                f"{[a.value for a in missing]}"
            )
            if not dry_run:
                integration.create_missing_configurations(actions=actions)
            total_created += len(missing)

        verb = "Would create" if dry_run else "Created"
        self.stdout.write(
            f"{verb} {total_created} configuration(s) across "
            f"{integrations_touched} integration(s)."
        )

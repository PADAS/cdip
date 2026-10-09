from django.core.management.base import BaseCommand, CommandError

from integrations.models import Integration, IntegrationAction, IntegrationType


class Command(BaseCommand):
    help = (
        "Set the missing `additional.topic` / `additional.broker` that cdip-routing publishes to, "
        "on integrations whose type has a push action and is served by an action runner. "
        "Never overwrites an existing value; safe to re-run."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="List the changes without saving them.")
        parser.add_argument("--type", type=str, dest="type_value", help="Only integrations of this type (value/slug).")

    def handle(self, *args, **options):
        queryset = Integration.objects.filter(
            type__actions__type=IntegrationAction.ActionTypes.PUSH_DATA
        ).distinct().select_related("type", "owner").order_by("type__value", "owner__name", "name")
        if type_value := options["type_value"]:
            if not IntegrationType.objects.filter(value=type_value).exists():
                raise CommandError(f"Integration type '{type_value}' not found.")
            queryset = queryset.filter(type__value=type_value)

        dry_run = options["dry_run"]
        changed = 0
        for integration in queryset:
            if dry_run:
                missing = integration.missing_push_data_broker_config()
            else:
                missing = integration.ensure_push_data_broker_config()
            if not missing:
                continue
            changed += 1
            self.stdout.write(
                f"{'[dry-run] ' if dry_run else ''}{integration.type.value} | {integration.owner.name} - "
                f"{integration.name} ({integration.id}): set {missing}"
            )

        verb = "would be updated" if dry_run else "updated"
        self.stdout.write(self.style.SUCCESS(f"{changed} integration(s) {verb}."))

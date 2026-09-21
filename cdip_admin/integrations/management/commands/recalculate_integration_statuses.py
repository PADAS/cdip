from django.core.management.base import BaseCommand

from integrations.models import Integration
from integrations.models.v2 import calculate_integration_status


class Command(BaseCommand):
    help = (
        "Recalculate the health status of integrations. By default every integration is "
        "recalculated synchronously; pass --integration-id to limit the scope, or --async "
        "to enqueue the Celery task instead of running inline. This is the same calculation "
        "the hourly 'Calculate Integration Statuses' beat task performs."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--integration-id",
            action="append",
            dest="integration_ids",
            default=None,
            help="Integration id to recalculate. Repeat to pass several. Defaults to all integrations.",
        )
        parser.add_argument(
            "--async",
            action="store_true",
            dest="run_async",
            default=False,
            help="Enqueue the Celery task(s) instead of recalculating inline.",
        )

    def handle(self, *args, **options):
        integration_ids = options["integration_ids"]
        run_async = options["run_async"]

        if integration_ids:
            # Validate the ids so a typo fails loudly instead of silently doing nothing.
            found = set(
                str(i) for i in Integration.objects.filter(
                    id__in=integration_ids
                ).values_list("id", flat=True)
            )
            missing = [i for i in integration_ids if str(i) not in found]
            if missing:
                self.stderr.write(f"Unknown integration id(s): {', '.join(missing)}")
            integration_ids = list(found)
        else:
            integration_ids = [
                str(i) for i in Integration.objects.values_list("id", flat=True)
            ]

        if not integration_ids:
            self.stdout.write("No integrations to recalculate.")
            return

        if run_async:
            from integrations.tasks import calculate_integration_statuses
            calculate_integration_statuses.delay(integration_ids=integration_ids)
            self.stdout.write(
                f"Enqueued recalculation for {len(integration_ids)} integration(s)."
            )
            return

        self.stdout.write(f"Recalculating status for {len(integration_ids)} integration(s)...")
        for integration_id in integration_ids:
            try:
                status = calculate_integration_status(integration_id)
            except Exception as e:
                self.stderr.write(f"Error recalculating {integration_id}: {e}")
                continue
            self.stdout.write(f"{integration_id}: {status}")
        self.stdout.write("Done!")

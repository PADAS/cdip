"""Audit — and with --fix, repair — providers whose default route violates the invariant.

Spec: docs/superpowers/specs/2026-09-18-default-route-invariant-design.md §5.2.
Dry by default. Exit code 1 while any violator remains, so it works as a
post-deploy gate. Run it, READ the output, then run --fix.
"""
import json

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count

from integrations.models import (
    AmbiguousDefaultRouteError,
    Integration,
    Route,
    get_default_route_state,
    providers_without_valid_default_route,
    resolve_default_route,
)


class Command(BaseCommand):
    help = (
        "List providers whose default_route is missing, not one of their routes, or empty while "
        "another route delivers. --fix repairs the unambiguous ones (logged to ActivityLog) and "
        "lists the rest. Exit code 1 while violators remain."
    )

    def add_arguments(self, parser):
        parser.add_argument("--fix", action="store_true", help="Repair unambiguous violators.")
        parser.add_argument("--integration", type=str, help="Only this integration (UUID).")
        parser.add_argument("--json", action="store_true", dest="as_json", help="Machine-readable output.")

    def handle(self, *args, **options):
        queryset = providers_without_valid_default_route().select_related("type", "owner", "default_route")
        if options["integration"]:
            try:
                exists = Integration.objects.filter(pk=options["integration"]).exists()
            except (ValueError, ValidationError):
                exists = False
            if not exists:
                raise CommandError(f"Integration '{options['integration']}' not found.")
            queryset = queryset.filter(pk=options["integration"])
        queryset = queryset.order_by("owner__name", "name")

        report = []
        for integration in queryset:
            entry = self._describe(integration)
            if options["fix"]:
                entry["repair"] = self._repair(integration)
            report.append(entry)

        remaining = [entry for entry in report if entry.get("repair", {}).get("result") != "fixed"]

        if options["as_json"]:
            self.stdout.write(json.dumps(report, indent=2))
        elif not report:
            self.stdout.write(self.style.SUCCESS("No default route violations found."))
        else:
            for entry in report:
                self.stdout.write(self._format(entry))
            fixed = len(report) - len(remaining)
            self.stdout.write(f"\n{len(report)} violator(s) found" + (f", {fixed} fixed" if options["fix"] else ""))

        if remaining:
            raise CommandError(
                f"{len(remaining)} provider(s) without a valid default route"
                + ("" if options["fix"] else " (dry run; pass --fix to repair the unambiguous ones)")
            )

    @staticmethod
    def _describe(integration):
        state = get_default_route_state(integration)
        candidates = (
            Route.objects.filter(data_providers=integration.pk)
            .annotate(destination_count=Count("destinations"))
            .order_by("name")
        )
        return {
            "id": str(integration.pk),
            "name": integration.name,
            "type": integration.type.value,
            "owner": integration.owner.name,
            "default_route": (
                {"id": str(integration.default_route_id), "name": integration.default_route.name}
                if integration.default_route_id else None
            ),
            "violation": state.value if state else None,
            "candidates": [
                {"id": str(route.pk), "name": route.name, "destination_count": route.destination_count}
                for route in candidates
            ],
        }

    @staticmethod
    def _repair(integration):
        # Each repair in its own transaction so one ambiguous case cannot roll back the others.
        try:
            with transaction.atomic():
                route = resolve_default_route(integration, via="check_default_routes")
        except AmbiguousDefaultRouteError as error:
            return {
                "result": "ambiguous",
                "candidates": [{"id": str(r.pk), "name": r.name} for r in error.candidates],
            }
        return {
            "result": "fixed",
            "default_route": {"id": str(route.pk), "name": route.name} if route else None,
        }

    @staticmethod
    def _format(entry):
        default = entry["default_route"]
        lines = [
            f"{entry['id']}  {entry['name']}  [{entry['type']}]  owner={entry['owner']}",
            f"    violation: {entry['violation']}   default_route: "
            + (f"{default['name']} ({default['id']})" if default else "NULL"),
        ]
        for candidate in entry["candidates"]:
            lines.append(
                f"    candidate: {candidate['name']} ({candidate['id']})  destinations={candidate['destination_count']}"
            )
        repair = entry.get("repair")
        if repair:
            if repair["result"] == "fixed":
                fixed_to = repair["default_route"]
                lines.append(
                    "    -> fixed: default_route = "
                    + (fixed_to["name"] if fixed_to else "NULL (no longer a provider on any route)")
                )
            else:
                names = ", ".join(c["name"] for c in repair["candidates"])
                lines.append(f"    -> ambiguous, left alone. Choose one of: {names}")
        return "\n".join(lines)

"""Audit for GUNDI-5730 §2's "no precedence system needed" decision: are there any
(provider, destination) pairs covered by more than one enabled Route today?

Read-only. Exit code 1 if any overlap is found, so it can gate the decision
before merging the "deliver through all overlapping Routes, log a warning"
behavior in cdip-routing.
"""
import json
from collections import defaultdict

from django.core.management.base import BaseCommand

from integrations.models import Route


class Command(BaseCommand):
    help = (
        "List (provider, destination) pairs covered by more than one enabled Route. "
        "Read-only. Exit code 1 if any overlap is found."
    )

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", dest="as_json", help="Machine-readable output.")

    def handle(self, *args, **options):
        routes_by_pair = defaultdict(set)
        names_by_route = {}
        providers_and_destinations = Route.objects.filter(enabled=True).prefetch_related(
            "data_providers", "destinations"
        )
        for route in providers_and_destinations:
            names_by_route[route.pk] = route.name
            for provider in route.data_providers.all():
                for destination in route.destinations.all():
                    routes_by_pair[(provider.pk, destination.pk)].add(route.pk)

        overlaps = {
            pair: route_ids for pair, route_ids in routes_by_pair.items() if len(route_ids) > 1
        }

        if options["as_json"]:
            report = [
                {
                    "provider_id": str(provider_id),
                    "destination_id": str(destination_id),
                    "routes": [
                        {"id": str(route_id), "name": names_by_route[route_id]}
                        for route_id in route_ids
                    ],
                }
                for (provider_id, destination_id), route_ids in overlaps.items()
            ]
            self.stdout.write(json.dumps(report, indent=2))
        elif not overlaps:
            self.stdout.write(self.style.SUCCESS("No (provider, destination) pair is covered by more than one enabled Route."))
        else:
            for (provider_id, destination_id), route_ids in overlaps.items():
                names = ", ".join(f"{names_by_route[rid]} ({rid})" for rid in route_ids)
                self.stdout.write(f"provider={provider_id}  destination={destination_id}  routes: {names}")
            self.stdout.write(f"\n{len(overlaps)} overlapping pair(s) found")

        if overlaps:
            exit_code = 1
            raise SystemExit(exit_code)

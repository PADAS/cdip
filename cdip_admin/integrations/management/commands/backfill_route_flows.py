"""Backfill flow_id for forward Routes, and link old return Routes -- the ones
the portal's pre-GUNDI-5730 "arrow back" feature created, with no real link to
their forward Route, just a stamped name -- to the flow they actually belong to.

Spec: docs/superpowers/specs referenced in the GUNDI-5730 Implementation Plan,
§2 backfill heuristic. Dry by default. Run it, READ the output, then run --fix.
"""
import json

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count

from integrations.models import Route

SEPARATOR = " → "


class Command(BaseCommand):
    help = (
        "Backfill flow_id on forward Routes, and link old name-matched return "
        "Routes to their forward Route's flow. Dry run by default; pass --fix "
        "to apply. A candidate only gets linked when BOTH its stamped name AND "
        "its structure (exactly one provider, one destination, one matching "
        "forward Route) agree -- anything less certain is reported, not guessed."
    )

    def add_arguments(self, parser):
        parser.add_argument("--fix", action="store_true", help="Apply the backfill.")
        parser.add_argument("--json", action="store_true", dest="as_json", help="Machine-readable output.")

    def handle(self, *args, **options):
        forward_missing_flow_id = list(
            Route.objects.filter(direction=Route.Direction.FORWARD, flow_id__isnull=True)
        )

        matched, skipped = self._find_return_leg_matches()

        if options["fix"]:
            for route in forward_missing_flow_id:
                route.flow_id = route.id
                route.save(update_fields=["flow_id"])
            for pair in matched:
                candidate = pair["candidate"]
                forward_route = pair["forward_route"]
                candidate.flow_id = forward_route.flow_id or forward_route.id
                candidate.direction = Route.Direction.RETURN
                candidate.return_for_destination = pair["leg_provider"]
                candidate.save(update_fields=["flow_id", "direction", "return_for_destination"])

        report = {
            "forward_routes_missing_flow_id": [
                {"id": str(r.id), "name": r.name} for r in forward_missing_flow_id
            ],
            "matched_return_legs": [
                {
                    "id": str(pair["candidate"].id),
                    "name": pair["candidate"].name,
                    "forward_route": {
                        "id": str(pair["forward_route"].id),
                        "name": pair["forward_route"].name,
                    },
                    "return_for_destination": {
                        "id": str(pair["leg_provider"].id),
                        "name": pair["leg_provider"].name,
                    },
                }
                for pair in matched
            ],
            "skipped": [
                {
                    "id": str(s["candidate"].id),
                    "name": s["candidate"].name,
                    "name_matches": s["name_matches"],
                    "forward_candidate_count": len(s["forward_candidates"]),
                    "forward_candidates": [
                        {"id": str(f.id), "name": f.name} for f in s["forward_candidates"]
                    ],
                }
                for s in skipped
            ],
        }

        if options["as_json"]:
            self.stdout.write(json.dumps(report, indent=2))
        else:
            self._print_report(report, fixed=options["fix"])

        if skipped and not options["fix"]:
            raise CommandError(
                f"{len(skipped)} candidate(s) need manual review before --fix "
                "(ambiguous structural match, or name doesn't match either)"
            )
        if skipped:
            raise CommandError(
                f"{len(skipped)} candidate(s) could not be linked automatically "
                "and still need manual review"
            )

    @staticmethod
    def _find_return_leg_matches():
        candidates = (
            Route.objects.filter(direction=Route.Direction.FORWARD)
            .annotate(
                n_providers=Count("data_providers", distinct=True),
                n_destinations=Count("destinations", distinct=True),
            )
            .filter(n_providers=1, n_destinations=1)
            .prefetch_related("data_providers", "destinations")
        )

        matched = []
        skipped = []
        for candidate in candidates:
            # An ordinary one-destination Route (the common case) never looked
            # like a return leg in the first place -- same gate the portal's
            # own looksLikeReverseRouteName uses. Without this, a Route's own
            # structural mirror (its genuine forward counterpart) would get
            # evaluated as if IT might be a return leg too, and flagged for
            # review for no reason.
            if SEPARATOR not in candidate.name:
                continue

            leg_provider = candidate.data_providers.first()
            leg_destination = candidate.destinations.first()
            expected_name = f"{leg_provider.name}{SEPARATOR}{leg_destination.name}"
            name_matches = candidate.name == expected_name

            forward_candidates = list(
                Route.objects.filter(
                    direction=Route.Direction.FORWARD,
                    data_providers=leg_destination,
                    destinations=leg_provider,
                )
                .exclude(pk=candidate.pk)
                .distinct()
            )

            if name_matches and len(forward_candidates) == 1:
                matched.append({
                    "candidate": candidate,
                    "forward_route": forward_candidates[0],
                    "leg_provider": leg_provider,
                })
            else:
                # Already passed the "looks like a return leg" name gate above,
                # so this is worth a human's time: either the exact name stamp
                # doesn't line up, or the structural match is missing/ambiguous.
                skipped.append({
                    "candidate": candidate,
                    "name_matches": name_matches,
                    "forward_candidates": forward_candidates,
                })
        return matched, skipped

    def _print_report(self, report, fixed):
        verb = "Backfilled" if fixed else "Would backfill"
        self.stdout.write(f"{verb} flow_id on {len(report['forward_routes_missing_flow_id'])} forward Route(s)")
        for r in report["forward_routes_missing_flow_id"]:
            self.stdout.write(f"    {r['name']} ({r['id']})")

        verb = "Linked" if fixed else "Would link"
        self.stdout.write(f"\n{verb} {len(report['matched_return_legs'])} return leg(s) to their flow")
        for m in report["matched_return_legs"]:
            self.stdout.write(
                f"    {m['name']} ({m['id']}) -> forward Route {m['forward_route']['name']} "
                f"({m['forward_route']['id']}), return_for_destination={m['return_for_destination']['name']}"
            )

        self.stdout.write(f"\n{len(report['skipped'])} candidate(s) need manual review")
        for s in report["skipped"]:
            reason = (
                "ambiguous forward match" if s["forward_candidate_count"] > 1
                else "no forward match" if s["forward_candidate_count"] == 0
                else "name doesn't match the expected stamp"
            )
            self.stdout.write(f"    {s['name']} ({s['id']}) -- {reason}")
            for f in s["forward_candidates"]:
                self.stdout.write(f"        candidate forward Route: {f['name']} ({f['id']})")

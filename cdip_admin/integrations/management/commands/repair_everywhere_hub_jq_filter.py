"""Repair the alertType fallback in live Everywhere Hub webhook filters.

The Everywhere Hub jq filter shipped with an expression that falls back to the
whole input when an alert type is not in the rename map::

    | .alertType = (if $am[.alertType] then $am[.alertType] else . end)

``.`` there is the entire payload object, so any unmapped alert produced an
object as ``event_type`` instead of the alert-type string. The fallback should
be ``.alertType``. convert_bridge_integration creates new configurations with
the corrected expression; this command repairs the ones already in the database.

It is deliberately narrow: only ``generic_json_webhook`` configurations whose
filter carries the Everywhere Hub alert map are considered, because
``else . end`` is ordinary jq that is correct in other filters.
"""

import json

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from integrations.models import Integration, WebhookConfiguration

from .convert_bridge_integration import WEBHOOK_GENERIC_JSON


# Identifies a filter as an Everywhere Hub one: this value only appears in the
# alert-type rename map at the top of that filter.
EVERYWHERE_HUB_MARKER = "ew_check_in_im_ok"

BUGGY_EXPRESSION = (
    "| .alertType = (if $am[.alertType] then $am[.alertType] else . end)"
)
FIXED_EXPRESSION = (
    "| .alertType = (if $am[.alertType] then $am[.alertType] else .alertType end)"
)


def needs_repair(jq_filter):
    """True when this filter is an Everywhere Hub one carrying the bug."""
    if not isinstance(jq_filter, str):
        return False
    return EVERYWHERE_HUB_MARKER in jq_filter and BUGGY_EXPRESSION in jq_filter


class Command(BaseCommand):
    help = (
        "Repair the alertType fallback in existing Everywhere Hub webhook "
        "configurations. Reports without writing unless --apply is given."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help=(
                "Write the repaired filters. Without this the command only "
                "reports what it would change."
            ),
        )
        parser.add_argument(
            "--integration",
            type=str,
            help="Repair only the configuration of this integration, by ID.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        configurations = self._select_configurations(options.get("integration"))

        repaired = []
        with transaction.atomic():
            for config in configurations:
                jq_filter = (config.data or {}).get("jq_filter")
                if not needs_repair(jq_filter):
                    continue
                repaired.append(
                    {
                        "webhook_configuration": str(config.id),
                        "integration": str(config.integration_id),
                        "integration_name": config.integration.name,
                        "previous_jq_filter": jq_filter,
                    }
                )
                if apply_changes:
                    # Replace only the one expression: these filters are edited
                    # by hand in the portal, and the rest may be customised.
                    config.data = {
                        **config.data,
                        "jq_filter": jq_filter.replace(
                            BUGGY_EXPRESSION, FIXED_EXPRESSION
                        ),
                    }
                    config.save()

        verb = "Repaired" if apply_changes else "Would repair"
        self.stderr.write(
            f"{verb} {len(repaired)} Everywhere Hub webhook configuration(s)."
        )
        if repaired and not apply_changes:
            self.stderr.write("Re-run with --apply to write these changes.")
        self.stdout.write(
            json.dumps({"applied": apply_changes, "repaired": repaired}, indent=2)
        )

    def _select_configurations(self, integration_id):
        configurations = WebhookConfiguration.objects.filter(
            webhook__value=WEBHOOK_GENERIC_JSON
        ).select_related("integration")
        if not integration_id:
            return configurations

        try:
            exists = Integration.objects.filter(id=integration_id).exists()
        except (ValidationError, ValueError):
            exists = False
        if not exists:
            raise CommandError(f"Integration '{integration_id}' not found.")
        return configurations.filter(integration_id=integration_id)

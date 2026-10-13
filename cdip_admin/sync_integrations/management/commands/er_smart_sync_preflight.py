"""Check every SMART -> EarthRanger sync pair before the v2 event type rollout.

For each pair the Beat schedule would chain (same query as the sync task):
the ER site's version against the first release with the migrate endpoint,
and optionally a dry run of that endpoint, reporting event types with error
codes and choice values ER could not persist (its Choice value column is
varchar(100)). Exits non-zero when any check fails.

This runs on the image deployed *before* the er-smart-sync switch, so it
depends only on Django, requests and the integration models: no erclient,
no er-smart-sync, and a local copy of the pair query when the shared helper
is not yet present.
"""
import re
from urllib.parse import urlparse

import requests
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from integrations.models import (
    Device,
    InboundIntegrationConfiguration,
    InboundIntegrationType,
    OutboundIntegrationConfiguration,
    OutboundIntegrationType,
)

try:
    from sync_integrations.tasks import er_integrations_for
except ImportError:  # image predates the shared helper; same query as the sync task
    def er_integrations_for(smart_integration):
        device_groups = smart_integration.devicegroups.all()
        devices = Device.objects.filter(
            devicegroup__in=device_groups,
            inbound_configuration__type__slug=InboundIntegrationType.EARTHRANGER,
        ).order_by("inbound_configuration_id").distinct("inbound_configuration_id").values("inbound_configuration_id")
        idlist = [dev.get("inbound_configuration_id") for dev in devices]
        return InboundIntegrationConfiguration.objects.filter(
            enabled=True, type__slug=InboundIntegrationType.EARTHRANGER
        ).filter(Q(default_devicegroup__in=device_groups) | Q(id__in=idlist))

TIMEOUT = 120
CLIENT_ID = "das_web_client"
# "already v2" from ER's migrator: nothing to convert, not a failure.
ALREADY_V2 = "version_validation"
# SMART-derived event type values start with the conservation area UUID; only
# those are sent to the migrate endpoint by the portal, so only those block.
SMART_DERIVED = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)


def sync_pairs(smart_integration_id=None):
    smart_integrations = OutboundIntegrationConfiguration.objects.filter(
        enabled=True, type__slug=OutboundIntegrationType.SMARTCONNECT
    )
    if smart_integration_id:
        smart_integrations = smart_integrations.filter(id=smart_integration_id)
    return [
        (smart, er)
        for smart in smart_integrations.order_by("name")
        for er in er_integrations_for(smart).order_by("name")
    ]


def er_base_url(endpoint: str) -> str:
    """https://site.pamdas.org from either the site root or a /api/v1.0 root."""
    parsed = urlparse(endpoint)
    return f"{parsed.scheme}://{parsed.netloc}"


def auth_headers(er) -> dict:
    """Bearer header from the integration's token, else a password grant."""
    token = er.token
    if not token:
        response = requests.post(
            f"{er_base_url(er.endpoint)}/oauth2/token",
            data={
                "grant_type": "password",
                "username": er.login,
                "password": er.password,
                "client_id": CLIENT_ID,
            },
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def er_version(base_url: str, headers: dict) -> str:
    response = requests.get(f"{base_url}/api/v1.0/status", headers=headers, timeout=TIMEOUT)
    response.raise_for_status()
    data = response.json().get("data") or {}
    return str(data.get("version") or "")


def migrate_dry_run(base_url: str, headers: dict) -> list:
    response = requests.post(
        f"{base_url}/api/v2.0/activity/eventtypes/migrate/",
        json={"dry_run": True, "event_types": []},
        headers=headers,
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    data = response.json().get("data")
    return data if isinstance(data, list) else []


def version_tuple(version: str) -> tuple:
    """Numeric tuple of the first dotted number in an ER version string.

    ER reports strings like ``release-2.148.1-a15e403``; only ``2.148.1``
    matters.
    """
    match = re.search(r"\d+(?:\.\d+)+", version or "")
    return tuple(int(n) for n in match.group(0).split(".")) if match else ()


def summarize_dry_run(results: list, max_value_length: int) -> dict:
    """Per-type problems from a dry run: error codes and over-long choice values.

    ``problems`` holds SMART-derived types (the ones the portal migrates);
    ``other_problems`` holds hand-made v1 types, reported but not counted.
    """
    problems, other_problems = {}, {}
    already_v2 = 0
    for result in results:
        value = result.get("event_type") or ""
        codes = [e.get("code") for e in result.get("errors") or []]
        if codes == [ALREADY_V2]:
            already_v2 += 1
            continue
        long_values = [
            choice.get("value")
            for hc in result.get("hardcoded_choices") or []
            for choice in hc.get("choices") or []
            if len(choice.get("value") or "") > max_value_length
        ]
        if codes or long_values:
            bucket = problems if SMART_DERIVED.match(value) else other_problems
            bucket[value] = {"errors": codes, "long_values": long_values}
    return {
        "evaluated": len(results),
        "already_v2": already_v2,
        "problems": problems,
        "other_problems": other_problems,
    }


class Command(BaseCommand):
    help = "Check ER versions (and optionally dry-run the event type migration) for every SMART sync pair."

    def add_arguments(self, parser):
        parser.add_argument("--smart-integration-id", help="Limit to one SMART integration.")
        parser.add_argument(
            "--migrate-dry-run", action="store_true",
            help="Also POST a dry-run migrate of every v1 event type on each site (writes nothing).",
        )
        parser.add_argument("--min-er-version", default="2.146.1")
        parser.add_argument("--max-choice-value-length", type=int, default=100)
        parser.add_argument(
            "--show-values", action="store_true",
            help="Print the over-long choice values themselves (distinct, per site).",
        )

    def handle(self, *args, **options):
        pairs = sync_pairs(options["smart_integration_id"])
        if not pairs:
            raise CommandError("No enabled SMART -> EarthRanger sync pairs found.")
        minimum = version_tuple(options["min_er_version"])
        failures = 0
        checked_sites = {}
        for smart, er in pairs:
            self.stdout.write(f"{smart.name} ({smart.id}) -> {er.name} ({er.id}) {er.endpoint}")
            if er.id in checked_sites:
                self.stdout.write(f"  (site already checked: {checked_sites[er.id]})")
                continue
            try:
                base_url = er_base_url(er.endpoint)
                headers = auth_headers(er)
                version = er_version(base_url, headers)
                ok = bool(version) and version_tuple(version) >= minimum
                verdict = "OK" if ok else f"LOW (need >= {options['min_er_version']})"
                line = f"  ER {version or '?'}: {verdict}"
                failures += 0 if ok else 1
                if options["migrate_dry_run"]:
                    summary = summarize_dry_run(
                        migrate_dry_run(base_url, headers), options["max_choice_value_length"]
                    )
                    line += (
                        f"; dry run: {summary['evaluated']} v1 types evaluated, "
                        f"{summary['already_v2']} already v2, "
                        f"{len(summary['problems'])} SMART-derived with problems, "
                        f"{len(summary['other_problems'])} other v1 types with problems (not migrated by the portal)"
                    )
                    long_values_seen = set()
                    for label, bucket in (("", summary["problems"]), ("(other) ", summary["other_problems"])):
                        for value, problem in bucket.items():
                            detail = []
                            if problem["errors"]:
                                detail.append("errors=" + ",".join(problem["errors"]))
                            if problem["long_values"]:
                                detail.append(
                                    f"{len(problem['long_values'])} choice value(s) over "
                                    f"{options['max_choice_value_length']} chars"
                                )
                                long_values_seen.update(problem["long_values"])
                            self.stdout.write(f"    {label}{value}: " + "; ".join(detail))
                    if options["show_values"] and long_values_seen:
                        self.stdout.write(f"    {len(long_values_seen)} distinct over-long choice value(s):")
                        for long_value in sorted(long_values_seen):
                            self.stdout.write(f"      [{len(long_value)}] {long_value}")
                    failures += len(summary["problems"])
                self.stdout.write(line)
                checked_sites[er.id] = line.strip()
            except Exception as e:  # noqa: BLE001 - report every site, then fail
                failures += 1
                self.stdout.write(f"  ERROR {type(e).__name__}: {e}")
                checked_sites[er.id] = f"ERROR {type(e).__name__}"
        self.stdout.write(f"{len(pairs)} pair(s), {len(checked_sites)} site(s), {failures} failure(s)")
        if failures:
            raise CommandError(f"{failures} preflight failure(s)")

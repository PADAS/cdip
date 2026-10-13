"""Check every SMART -> EarthRanger sync pair before the v2 event type rollout.

For each pair the Beat schedule would chain (same query as the sync task):
the ER site's version against the first release with the migrate endpoint,
and optionally a dry run of that endpoint, reporting event types with error
codes and choice values ER could not persist (its Choice value column is
varchar(100)). Exits non-zero when any check fails.
"""
from django.core.management.base import BaseCommand, CommandError
from erclient import ERClient
from packaging.version import InvalidVersion, Version

from integrations.models import OutboundIntegrationConfiguration, OutboundIntegrationType
from sync_integrations.er_smart_sync import build_sync_config
from sync_integrations.tasks import er_integrations_for

MIGRATE_PATH = "activity/eventtypes/migrate/"
# "already v2" from ER's migrator: nothing to convert, not a failure.
ALREADY_V2 = "version_validation"


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


def er_client_for(smart, er) -> ERClient:
    config = build_sync_config(smart_config=smart, er_config=er)
    return ERClient(
        service_root=config.earthranger.endpoint,
        username=config.earthranger.login,
        password=config.earthranger.password,
        token=config.earthranger.token,
        client_id=config.earthranger.client_id,
        provider_key=config.smart.provider_key,
    )


def migrate_dry_run(client: ERClient) -> list[dict]:
    results = client._post(
        path=MIGRATE_PATH,
        payload={"dry_run": True, "event_types": []},
        base_url=client._api_root("v2.0"),
    )
    return results if isinstance(results, list) else []


def summarize_dry_run(results: list[dict], max_value_length: int) -> dict:
    """Per-type problems from a dry run: error codes and over-long choice values."""
    problems = {}
    already_v2 = 0
    for result in results:
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
            problems[result.get("event_type")] = {"errors": codes, "long_values": long_values}
    return {"evaluated": len(results), "already_v2": already_v2, "problems": problems}


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

    def handle(self, *args, **options):
        pairs = sync_pairs(options["smart_integration_id"])
        if not pairs:
            raise CommandError("No enabled SMART -> EarthRanger sync pairs found.")
        minimum = Version(options["min_er_version"])
        failures = 0
        checked_sites = {}
        for smart, er in pairs:
            self.stdout.write(f"{smart.name} ({smart.id}) -> {er.name} ({er.id}) {er.endpoint}")
            if er.id in checked_sites:
                self.stdout.write(f"  (site already checked: {checked_sites[er.id]})")
                continue
            try:
                client = er_client_for(smart, er)
                status = client._get("status") or {}
                version = str(status.get("version") or "")
                try:
                    ok = Version(version) >= minimum
                except InvalidVersion:
                    ok = False
                line = f"  ER {version or '?'}: {'OK' if ok else f'LOW (need >= {minimum})'}"
                failures += 0 if ok else 1
                if options["migrate_dry_run"]:
                    summary = summarize_dry_run(migrate_dry_run(client), options["max_choice_value_length"])
                    line += (
                        f"; dry run: {summary['evaluated']} v1 types evaluated, "
                        f"{summary['already_v2']} already v2, {len(summary['problems'])} with problems"
                    )
                    for value, problem in summary["problems"].items():
                        detail = []
                        if problem["errors"]:
                            detail.append("errors=" + ",".join(problem["errors"]))
                        if problem["long_values"]:
                            detail.append(f"{len(problem['long_values'])} choice value(s) over "
                                          f"{options['max_choice_value_length']} chars")
                        self.stdout.write(f"    {value}: " + "; ".join(detail))
                    failures += len(summary["problems"])
                self.stdout.write(line)
                checked_sites[er.id] = line.strip()
            except Exception as e:  # noqa: BLE001 - report every site, then fail
                failures += 1
                self.stdout.write(f"  ERROR {type(e).__name__}: {e}")
                checked_sites[er.id] = f"ERROR {type(e).__name__}"
        self.stdout.write(
            f"{len(pairs)} pair(s), {len(checked_sites)} site(s), {failures} failure(s)"
        )
        if failures:
            raise CommandError(f"{failures} preflight failure(s)")

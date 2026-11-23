import datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_datetime

from stats import services


def _parse(value, option):
    moment = parse_datetime(value)
    if moment is None:
        raise CommandError(f"{option} must be an ISO 8601 datetime, e.g. 2026-11-20T00:00:00Z.")
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=datetime.timezone.utc)
    return moment


class Command(BaseCommand):
    help = (
        "Re-aggregate the stats rollups for an explicit time range. Use it when "
        "deliveries arrived later than the daily reconcile window. It does not "
        "change the freshness times reported by the stats endpoints."
    )

    def add_arguments(self, parser):
        parser.add_argument("--from", dest="start", required=True, help="Start (ISO 8601, UTC if no offset).")
        parser.add_argument("--to", dest="end", required=True, help="End, exclusive (ISO 8601, UTC if no offset).")

    def handle(self, *args, **options):
        start, end = _parse(options["start"], "--from"), _parse(options["end"], "--to")
        if start >= end:
            raise CommandError("--from must be earlier than --to.")
        buckets = services.hour_buckets(start, end)
        self.stdout.write(f"Re-aggregating {len(buckets)} hour bucket(s) from {buckets[0]:%Y-%m-%d %H:%M} UTC.")

        result = services.aggregate_buckets(buckets)

        self.stdout.write(self.style.SUCCESS(f"Aggregated {len(result.aggregated)} bucket(s)."))
        for label, skipped in (
            ("Throughput not aggregated (before STATS_THROUGHPUT_START, or it is not set)", result.skipped_throughput),
            ("Errors not aggregated (older than the activity log retention)", result.skipped_errors),
        ):
            if skipped:
                self.stdout.write(self.style.WARNING(
                    f"{label}: {len(skipped)} bucket(s), "
                    f"{skipped[0]:%Y-%m-%d %H:%M} to {skipped[-1]:%Y-%m-%d %H:%M} UTC."
                ))

from django.core.management.base import BaseCommand
from django.db.models.expressions import Func
from django.db.models import F, ExpressionWrapper, fields, Aggregate
from integrations.models import GundiTrace


class Microseconds(Func):
    template = 'EXTRACT(MICROSECONDS FROM %(expressions)s)::INTEGER'
    output_field = fields.BigIntegerField()


class Percentile(Aggregate):
    function = "PERCENTILE_CONT"
    name = "Percentile"
    output_field = fields.BigIntegerField()
    template = "%(function)s (%(percentile)s) WITHIN GROUP (ORDER BY %(expressions)s)"

    def __init__(self, percentile, expressions, **extra):
        super().__init__(expressions, percentile=percentile, **extra)


def get_latency(traces):
    # Annotate the queryset with the latency column
    traces_with_latency = traces.annotate(
        latency=ExpressionWrapper(
            Microseconds(F('delivered_at') - F('created_at')) / 1000,
            output_field=fields.BigIntegerField()
        )
    )
    percentiles = traces_with_latency.aggregate(
        p50=Percentile(0.50, 'latency'),
        p95=Percentile(0.95, 'latency'),
        p99=Percentile(0.99, 'latency')
    )
    return percentiles


def get_data_loss(traces):
    errors = traces.filter(has_error=True).count()
    return float(errors) / float(traces.count() or 1)


class Command(BaseCommand):
    help = "Get performance metrics in Gundi v2"

    def add_arguments(self, parser):
        parser.add_argument("--start", type=str, help="Start datetime")
        parser.add_argument("--end", type=str, help="End datetime")

    def handle(self, *args, **options):
        start = options["start"]
        end = options["end"]
        self.stdout.write(f"Computing metrics between: {start} and {end}...")
        unique_traces_in_range = GundiTrace.objects.filter(
            created_at__gte=start,
            created_at__lte=end,
            is_duplicate=False,
        )
        self.stdout.write(f"Received observations (without duplicates): {unique_traces_in_range.count()}")
        dispatched_observations = unique_traces_in_range.filter(
            has_error=False,
            delivered_at__isnull=False
        )
        self.stdout.write(f"Dispatched observations: {dispatched_observations.count()}")
        data_loss = get_data_loss(unique_traces_in_range)
        self.stdout.write(f"Data loss: {data_loss}")
        percentiles = get_latency(traces=dispatched_observations)
        self.stdout.write(f"Latency p50 [ms]: {percentiles['p50']}")
        self.stdout.write(f"Latency p95 [ms]: {percentiles['p95']}")
        self.stdout.write(f"Latency p99 [ms]: {percentiles['p99']}")
        self.stdout.write("Done!")

"""
Read side of the stats endpoints.

Everything here reads the rollup tables and the (small) integration,
integration type and organization tables. It never touches GundiTrace or
ActivityLog: those are only read by the rollup job (stats.services).
"""
import datetime

from django.conf import settings
from django.db import connection

from activity_log.models import ActivityLog
from integrations.models import Integration
from organizations.models import Organization

from .models import RollupRunState

UTC = datetime.timezone.utc

INTERVALS = ("hour", "day")
# Longest range served per interval, and the most rows in one response.
MAX_RANGE = {"hour": datetime.timedelta(days=31), "day": datetime.timedelta(days=366)}
MAX_ROWS = 5000
DEFAULT_RANGE = datetime.timedelta(hours=24)
DEFAULT_RANKING_LIMIT = 10
MAX_RANKING_LIMIT = 100

UNKNOWN = "unknown"  # label of an integration that no longer exists


class StatsQueryError(ValueError):
    """The request is valid in shape but cannot be served (for example, too large)."""


class Dimension:
    """A column a result can be grouped by and filtered on."""

    def __init__(self, label_sql, id_sql=None, filter_sql=None):
        self.label_sql = label_sql
        self.id_sql = id_sql
        # Filters compare ids where the dimension has one, labels otherwise.
        self.filter_sql = filter_sql or id_sql or label_sql


# Rollup rows keep integration ids without a foreign key, so the joins are
# LEFT joins and a deleted integration shows up as "unknown".
THROUGHPUT_FROM = """
    FROM stats_throughputrollup r
    LEFT JOIN integrations_integration p ON p.id = r.data_provider_id
    LEFT JOIN integrations_integrationtype pt ON pt.id = p.type_id
    LEFT JOIN organizations_organization o ON o.id = p.owner_id
    LEFT JOIN integrations_integration d ON d.id = r.destination_id
"""
THROUGHPUT_DIMENSIONS = {
    "integration_type": Dimension(f"COALESCE(pt.value, '{UNKNOWN}')", filter_sql="pt.value"),
    "organization": Dimension(f"COALESCE(o.name, '{UNKNOWN}')", id_sql="o.id"),
    "data_provider": Dimension(f"COALESCE(p.name, '{UNKNOWN}')", id_sql="r.data_provider_id"),
    # Received, duplicate and some discarded counts have no destination.
    "destination": Dimension(
        f"CASE WHEN r.destination_id IS NULL THEN NULL ELSE COALESCE(d.name, '{UNKNOWN}') END",
        id_sql="r.destination_id",
    ),
    "data_type": Dimension("r.object_type"),
}
THROUGHPUT_METRICS = ("received", "delivered", "discarded", "duplicate")

ERRORS_FROM = """
    FROM stats_errorrollup r
    LEFT JOIN integrations_integration p ON p.id = r.integration_id
    LEFT JOIN integrations_integrationtype pt ON pt.id = p.type_id
    LEFT JOIN organizations_organization o ON o.id = p.owner_id
"""
ERRORS_DIMENSIONS = {
    "integration_type": Dimension(f"COALESCE(pt.value, '{UNKNOWN}')", filter_sql="pt.value"),
    "organization": Dimension(f"COALESCE(o.name, '{UNKNOWN}')", id_sql="o.id"),
    "integration": Dimension(f"COALESCE(p.name, '{UNKNOWN}')", id_sql="r.integration_id"),
    "origin": Dimension("r.origin"),
    "kind": Dimension("r.value"),
}


def resolve_range(from_date, to_date, interval, now=None):
    """
    Default and align the requested range, and check it against the limit.
    Returns (start, end): start is floored to the interval, end is exclusive.
    """
    now = now or datetime.datetime.now(UTC)
    end = (to_date or now).astimezone(UTC)
    requested_start = (from_date or end - DEFAULT_RANGE).astimezone(UTC)
    start = requested_start.replace(minute=0, second=0, microsecond=0)
    if interval == "day":
        start = start.replace(hour=0)
    if start >= end:
        raise StatsQueryError("from_date must be earlier than to_date.")
    limit = MAX_RANGE[interval]
    # The limit applies to the range as requested: flooring the start to the
    # interval must not turn a request for exactly the limit into a rejection.
    if end - requested_start > limit:
        raise StatsQueryError(
            f"The range is too long for interval '{interval}': the limit is {limit.days} days."
        )
    return start, end


def _freshness(throughput=False):
    state = RollupRunState.objects.filter(pk=RollupRunState.SINGLETON_PK).first()
    freshness = {
        "data_as_of": state.frequent_run_completed_at if state else None,
        "reconciled_as_of": state.daily_run_completed_at if state else None,
    }
    if throughput:
        # The job aggregates throughput only from this time on, and not at all
        # while it is unset. A run that aggregated errors alone must not make
        # throughput look fresh.
        available_from = settings.STATS_THROUGHPUT_START
        freshness["throughput_available_from"] = available_from
        if available_from is None:
            freshness["data_as_of"] = freshness["reconciled_as_of"] = None
    return freshness


def _envelope(start, end, interval, group_by, results, throughput=False, **extra):
    return {
        "from": start,
        "to": end,
        "interval": interval,
        "group_by": list(group_by),
        **_freshness(throughput),
        **extra,
        "results": results,
    }


def _fetch(sql, params):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        columns = [column.name for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _bucketed(from_sql, dimensions, metrics, start, end, interval, group_by, filters, where=()):
    """
    Sum rollup rows per interval bucket and requested dimension.

    `dimensions`, `metrics` and `interval` come from the constants in this
    module, never from the request, so they are safe to interpolate. Request
    values only ever travel as query parameters.
    """
    select = ["date_trunc(%s, r.bucket, 'UTC') AS bucket"]
    params = [interval]
    group_positions = [1]
    for name in group_by:
        dimension = dimensions[name]
        if dimension.id_sql:
            select.append(f"{dimension.id_sql} AS {name}_id")
            group_positions.append(len(select))
        select.append(f"{dimension.label_sql} AS {name}")
        group_positions.append(len(select))
    for name, condition in metrics.items():
        select.append(f"COALESCE(SUM(r.count) FILTER (WHERE {condition}), 0)::bigint AS {name}")

    conditions = ["r.bucket >= %s", "r.bucket < %s", *where]
    params += [start, end]
    for name, value in filters.items():
        conditions.append(f"{dimensions[name].filter_sql} = %s")
        params.append(value)

    positions = ", ".join(str(position) for position in group_positions)
    sql = (
        f"SELECT {', '.join(select)} {from_sql} WHERE {' AND '.join(conditions)} "
        f"GROUP BY {positions} ORDER BY {positions} LIMIT %s"
    )
    rows = _fetch(sql, params + [MAX_ROWS + 1])
    if len(rows) > MAX_ROWS:
        raise StatsQueryError(
            f"The result is too large: the limit is {MAX_ROWS} rows. "
            "Narrow the range, use interval=day, or group by fewer dimensions."
        )
    return rows


def throughput(start, end, interval, group_by=(), filters=None):
    metrics = {name: f"r.metric = '{name}'" for name in THROUGHPUT_METRICS}
    rows = _bucketed(
        THROUGHPUT_FROM, THROUGHPUT_DIMENSIONS, metrics, start, end, interval, group_by, filters or {}
    )
    return _envelope(start, end, interval, group_by, rows, throughput=True)


def errors(start, end, interval, group_by=(), filters=None, include_retriable=False):
    levels = ActivityLog.LogLevels
    metrics = {"errors": f"r.log_level = {int(levels.ERROR)}"}
    where = []
    if include_retriable:
        metrics["retriable"] = f"r.log_level = {int(levels.WARNING)}"
    else:
        where.append(f"r.log_level = {int(levels.ERROR)}")
    rows = _bucketed(
        ERRORS_FROM, ERRORS_DIMENSIONS, metrics, start, end, interval, group_by, filters or {}, where
    )
    return _envelope(start, end, interval, group_by, rows)


def _ranking(dimension, id_sql, label_sql, order_metric, start, end, limit, where=""):
    sql = f"""
        SELECT {id_sql} AS id, {label_sql} AS name,
            COALESCE(SUM(r.count) FILTER (WHERE r.metric = 'received'), 0)::bigint AS received,
            COALESCE(SUM(r.count) FILTER (WHERE r.metric = 'delivered'), 0)::bigint AS delivered
        {THROUGHPUT_FROM}
        WHERE r.bucket >= %s AND r.bucket < %s AND r.metric IN ('received', 'delivered') {where}
        GROUP BY 1, 2
        ORDER BY {order_metric} DESC, 2
        LIMIT %s
    """
    return [{"dimension": dimension, **row} for row in _fetch(sql, [start, end, limit])]


def usage(start, end, interval, limit=DEFAULT_RANKING_LIMIT):
    """
    Totals are live counts. "Active" and the rankings come from the rollups:
    - an active connection is a data provider with at least one received item
      in the window;
    - an active organization owns at least one of them;
    - an active integration received items as a data provider or had items
      delivered to it as a destination.
    """
    active = _fetch(
        """
        SELECT
            COUNT(DISTINCT r.data_provider_id) FILTER (WHERE r.metric = 'received') AS connections,
            COUNT(DISTINCT p.owner_id) FILTER (WHERE r.metric = 'received') AS organizations
        FROM stats_throughputrollup r
        LEFT JOIN integrations_integration p ON p.id = r.data_provider_id
        WHERE r.bucket >= %s AND r.bucket < %s
        """,
        [start, end],
    )[0]
    active_integrations = _fetch(
        """
        SELECT COUNT(*) AS n FROM (
            SELECT r.data_provider_id FROM stats_throughputrollup r
            WHERE r.bucket >= %s AND r.bucket < %s AND r.metric = 'received'
            UNION
            SELECT r.destination_id FROM stats_throughputrollup r
            WHERE r.bucket >= %s AND r.bucket < %s AND r.metric = 'delivered'
                AND r.destination_id IS NOT NULL
        ) active
        """,
        [start, end, start, end],
    )[0]["n"]
    totals = {
        "organizations": Organization.objects.count(),
        "integrations": Integration.objects.count(),
        # A connection is a data provider integration with at least one route.
        "connections": Integration.objects.filter(routing_rules_by_provider__isnull=False).distinct().count(),
        "active_organizations": active["organizations"],
        "active_integrations": active_integrations,
        "active_connections": active["connections"],
    }
    dimensions = THROUGHPUT_DIMENSIONS
    results = [
        *_ranking("integration_type", "NULL::uuid", dimensions["integration_type"].label_sql,
                  "received", start, end, limit),
        *_ranking("organization", "o.id", dimensions["organization"].label_sql,
                  "received", start, end, limit),
        *_ranking("destination", "r.destination_id", dimensions["destination"].label_sql,
                  "delivered", start, end, limit, where="AND r.destination_id IS NOT NULL"),
    ]
    return _envelope(start, end, interval, (), results, throughput=True, totals=totals)

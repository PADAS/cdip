from drf_yasg.utils import swagger_auto_schema
from rest_framework import exceptions as drf_exceptions
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsMetricsViewer
from stats import queries

from . import serializers as v2_serializers
from .permissions import IsSuperuser


class StatsView(APIView):
    """
    Base for the system-wide stats endpoints.

    Read-only, served from hourly rollups: a request never queries the trace
    or activity-log tables. Only superusers and members of the MetricsViewer
    group may read them, and they see all organizations. Do not add IsOrgAdmin
    or IsOrgViewer here: they allow every safe method.
    """

    permission_classes = [IsSuperuser | IsMetricsViewer]
    http_method_names = ["get", "head", "options"]
    query_serializer_class = None

    def get_params(self, request):
        serializer = self.query_serializer_class(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def run_query(self, params):
        raise NotImplementedError

    def get(self, request, *args, **kwargs):
        params = self.get_params(request)
        try:
            return Response(self.run_query(params))
        except queries.StatsQueryError as e:
            raise drf_exceptions.ValidationError({"detail": str(e)})


class ThroughputStatsView(StatsView):
    """
    Items moving through Gundi, per time bucket.

    Each result has `bucket` (start of the hour or day, UTC), one key per
    `group_by` dimension (plus `<dimension>_id` where the dimension is an
    organization or integration) and four counts:

    - `received`: items received from data providers, duplicates included.
    - `delivered`: deliveries to destinations. One item sent to two
      destinations counts twice. Text messages may have no delivery event.
    - `discarded`: items dropped on purpose by a routing rule.
    - `duplicate`: received items that were recognized as duplicates.

    Buckets with no data are omitted. The response also states the range it
    served (`from`, `to`), `data_as_of` (last successful refresh of recent
    hours) and `reconciled_as_of` (last successful daily reconcile, which
    picks up deliveries reported up to 48 hours late); both are null until
    that job has run. A deleted integration is labelled `unknown`.

    Limits: 31 days with `interval=hour`, 366 days with `interval=day`, and
    5000 result rows. A request over a limit gets 400.
    """

    query_serializer_class = v2_serializers.ThroughputStatsQuerySerializer

    def run_query(self, params):
        return queries.throughput(
            params["start"], params["end"], params["interval"], params.get("group_by", []), params["filters"]
        )

    @swagger_auto_schema(query_serializer=v2_serializers.ThroughputStatsQuerySerializer)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class ErrorsStatsView(StatsView):
    """
    Failures recorded in the activity log, per time bucket.

    Each result has `bucket`, one key per `group_by` dimension and `errors`:
    the number of log entries at ERROR level (failed actions, webhooks,
    deliveries and updates, and other errors logged by integrations). A count
    is a number of logged failures, not a number of distinct failed items.

    With `include_retriable=true` each result also has `retriable`: delivery
    and update failures the dispatcher logged as warnings because it retries
    them. They are not included in `errors`.

    Delivery failures are attributed to the data provider, not the
    destination. `kind` is the log value, e.g. `observation_delivery_failed`.
    Infrastructure errors (gateway, auth, pods) are not part of these counts.

    Range, freshness fields and limits are the same as for throughput.
    """

    query_serializer_class = v2_serializers.ErrorsStatsQuerySerializer

    def run_query(self, params):
        return queries.errors(
            params["start"], params["end"], params["interval"], params.get("group_by", []),
            params["filters"], include_retriable=params["include_retriable"],
        )

    @swagger_auto_schema(query_serializer=v2_serializers.ErrorsStatsQuerySerializer)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class UsageStatsView(StatsView):
    """
    How much of Gundi is in use.

    `totals` has the current number of `organizations`, `integrations` and
    `connections` (data provider integrations with at least one route), and
    how many were active in the range: an active connection received at least
    one item, an active organization owns one, and an active integration
    received items as a data provider or had items delivered to it.

    `results` holds three rankings, told apart by `dimension`:
    `integration_type` and `organization` (of the data provider, ordered by
    `received`) and `destination` (ordered by `delivered`). Each entry has
    `id`, `name`, `received` and `delivered`; `limit` sets the entries per
    ranking (default 10, at most 100).

    The range and freshness fields are the same as for throughput. Results
    are totals over the whole range: `interval` only sets the range limit.
    """

    query_serializer_class = v2_serializers.UsageStatsQuerySerializer

    def run_query(self, params):
        return queries.usage(params["start"], params["end"], params["interval"], limit=params["limit"])

    @swagger_auto_schema(query_serializer=v2_serializers.UsageStatsQuerySerializer)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

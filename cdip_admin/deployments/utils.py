import logging
import json
import time
from urllib.parse import urlparse
from google.api_core import exceptions as gcp_exceptions
from google.cloud import secretmanager, monitoring_v3
from django.conf import settings
from core.utils import generate_short_id_milliseconds


logger = logging.getLogger(__name__)


# Failure-reason values mirror DispatcherDeployment.FailureReason choices.
# Kept as plain strings here to avoid a circular import from models.
FAILURE_REASON_QUOTA_EXHAUSTED = "quota_exhausted"
FAILURE_REASON_TRANSIENT = "transient"
FAILURE_REASON_CONFIG_ERROR = "config_error"
FAILURE_REASON_UNKNOWN = "unknown"


_QUOTA_MESSAGE_MARKERS = (
    "insufficient quota",
    "quota exceeded",
    "resource_exhausted",
    "resourceexhausted",
)

_TRANSIENT_MESSAGE_MARKERS = (
    "deadline exceeded",
    "service unavailable",
    "internal error",
    "connection reset",
    "temporarily unavailable",
)


def classify_deployment_error(exc):
    """Map a deployment exception to a DispatcherDeployment.FailureReason value.

    Quota failures (HTTP 429 / ResourceExhausted) come back in two shapes from
    the GCP client libs: a typed ``google.api_core.exceptions`` instance, or a
    plain ``Exception`` whose string contains "insufficient quota" (this is
    what we see when an LRO ``operation.result()`` resolves to a failed
    operation). Both are treated as ``QUOTA_EXHAUSTED`` so callers can clean
    up orphaned topics and back off instead of thrashing.
    """
    message = str(exc) if exc is not None else ""
    lowered = message.lower()

    if isinstance(exc, gcp_exceptions.ResourceExhausted):
        return FAILURE_REASON_QUOTA_EXHAUSTED
    if isinstance(exc, gcp_exceptions.TooManyRequests):
        return FAILURE_REASON_QUOTA_EXHAUSTED
    if any(marker in lowered for marker in _QUOTA_MESSAGE_MARKERS):
        return FAILURE_REASON_QUOTA_EXHAUSTED

    if isinstance(exc, (
        gcp_exceptions.InvalidArgument,
        gcp_exceptions.FailedPrecondition,
        gcp_exceptions.PermissionDenied,
        gcp_exceptions.NotFound,
        gcp_exceptions.Unauthenticated,
    )):
        return FAILURE_REASON_CONFIG_ERROR

    if isinstance(exc, (
        gcp_exceptions.DeadlineExceeded,
        gcp_exceptions.ServiceUnavailable,
        gcp_exceptions.InternalServerError,
        gcp_exceptions.Aborted,
    )):
        return FAILURE_REASON_TRANSIENT
    if any(marker in lowered for marker in _TRANSIENT_MESSAGE_MARKERS):
        return FAILURE_REASON_TRANSIENT

    return FAILURE_REASON_UNKNOWN


class PubSubDummyClient:

    def create_topic(
            self,
            request=None,
            *,
            name=None,
            retry=None,
            timeout=None,
            metadata=(),
    ) -> None:
        logger.warning(f"Using PubSubDummyClient. Topic creation ignored.")
        return None

    def delete_topic(
            self,
            request=None,
            *,
            topic=None,
            retry=None,
            timeout=None,
            metadata=(),
    ) -> None:
        logger.warning(f"Using PubSubDummyClient. Topic deletion ignored.")
        return None


class FunctionsDummyClient:

    def create_function(
            self,
            request=None,
            *,
            parent=None,
            function=None,
            function_id=None,
            retry=None,
            timeout=None,
            metadata=(),
    ) -> None:
        logger.warning(f"Using FunctionsDummyClient. Function creation ignored.")
        return None

    def update_function(
            self,
            request=None,
            *,
            function=None,
            update_mask=None,
            retry=None,
            timeout=None,
            metadata=(),
    ) -> None:
        logger.warning(f"Using FunctionsDummyClient. Function update ignored.")
        return None

    def delete_function(
            self,
            request=None,
            *,
            name=None,
            retry=None,
            timeout=None,
            metadata= (),
    ) -> None:
        logger.warning(f"Using FunctionsDummyClient. Function deletion ignored.")
        return None


class CloudRunDummyClient:

    def create_service(
            self,
            request=None,
            *,
            parent=None,
            service=None,
            service_id=None,
            retry=None,
            timeout=None,
            metadata=None,
    ) -> None:
        logger.warning(f"Using CloudRunDummyClient. Service creation ignored.")
        return None

    def get_service(
            self,
            request=None,
            *,
            name=None,
            retry=None,
            timeout=None,
            metadata=None,
    ) -> None:
        logger.warning(f"Using CloudRunDummyClient. Service get ignored.")
        return None

    def update_service(
        self,
        request=None,
        *,
        service=None,
        retry=None,
        timeout=None,
        metadata=None,
    ) -> None:
        logger.warning(f"Using CloudRunDummyClient. Service update ignored.")
        return None


class EventarcDummyClient:

    def create_trigger(
            self,
            request=None,
            *,
            parent=None,
            trigger=None,
            trigger_id=None,
            retry=None,
            timeout=None,
            metadata=(),
    ) -> None:
        logger.warning(f"Using EventarcDummyClient. Trigger creation ignored.")
        return None


class SubscriberDummyClient:

    def create_subscription(
            self,
            request=None,
            *,
            name=None,
            subscription=None,
            retry=None,
            timeout=None,
            metadata=(),
    ) -> None:
        logger.warning(f"Using SubscriberDummyClient. Subscription creation ignored.")
        return None

    def delete_subscription(
            self,
            request=None,
            *,
            subscription=None,
            retry=None,
            timeout=None,
            metadata=(),
    ) -> None:
        logger.warning(f"Using SubscriberDummyClient. Subscription deletion ignored.")
        return None


def get_dispatcher_defaults_from_gcp_secrets(secret_id=settings.DISPATCHER_DEFAULTS_SECRET):
    if not settings.GCP_ENVIRONMENT_ENABLED:
        return {}
    # Load default settings for serverless dispatchers from GCP secrets
    client = secretmanager.SecretManagerServiceClient()
    project_id = settings.GCP_PROJECT_ID
    secret_version_id = 'latest'
    name = f"projects/{project_id}/secrets/{secret_id}/versions/{secret_version_id}"
    response = client.access_secret_version(request={"name": name})
    return json.loads(response.payload.data.decode('UTF-8'))


def _leading_subdomain(host, max_len=None):
    """Return a GCP-valid leading segment for a dispatcher / topic name.

    GCP Cloud Run service IDs and Pub/Sub topic IDs must start with a
    lowercase ASCII letter (``[a-z]``) and use only ``[a-z0-9-]``. This
    helper enforces both invariants for the leading segment:

    - Splits ``host`` on ``.`` and takes the first segment.
    - Strips any character outside ``[a-z0-9-]``. This drops ``@``, ``/``,
      non-ASCII letters (e.g. Cyrillic) and other characters that can leak
      in via the ``parsed.path`` fallback used when ``base_url`` has no
      URL scheme.
    - Falls back to ``int`` for empty input (including segments that were
      wholly non-ASCII).
    - Prepends ``i`` when the first surviving character is not in
      ``[a-z]`` (e.g. numeric-leading hostnames like
      ``8fa1d0b7.fake-traptagger.org``).
    """
    seg = host.split(".")[0] if host else ""
    seg = "".join(
        c for c in seg if "a" <= c <= "z" or "0" <= c <= "9" or c == "-"
    )
    if max_len is not None:
        seg = seg[:max_len]
    if not seg:
        return "int"
    if not ("a" <= seg[0] <= "z"):
        seg = "i" + seg
        if max_len is not None:
            seg = seg[:max_len]
    return seg


def get_default_dispatcher_name(integration, gundi_version="v2"):
    integration_url = integration.base_url if gundi_version == "v2" else integration.endpoint
    parsed = urlparse(str(integration_url).lower())
    # urlparse only populates netloc when the URL has a scheme; fall back to
    # path so bare hostnames (e.g. "foo.example.org") still yield a subdomain.
    host = parsed.netloc or parsed.path
    subdomain = _leading_subdomain(host, max_len=8)
    integration_type_id = integration.type.value if gundi_version == "v2" else integration.type.slug
    integration_type = integration_type_id.replace("_", "").lower().strip()[:5]
    integration_id = str(integration.id)
    return "-".join([subdomain, integration_type, "dis", integration_id])[:49]


def get_default_topic_name(integration, gundi_version="v2"):
    integration_url = integration.base_url if gundi_version == "v2" else integration.endpoint
    parsed = urlparse(str(integration_url).lower())
    host = parsed.netloc or parsed.path
    subdomain = _leading_subdomain(host)
    integration_type_id = integration.type.value if gundi_version == "v2" else integration.type.slug
    integration_type = integration_type_id.replace("_", "").lower().strip()[:8]
    unique_suffix = generate_short_id_milliseconds()
    return "-".join([subdomain, integration_type, unique_suffix, "topic"])[:255]


def _dispatcher_secret_id_for(integration):
    if integration.is_smart_site:
        return settings.DISPATCHER_DEFAULTS_SECRET_SMART
    if integration.is_wpswatch_site:
        return settings.DISPATCHER_DEFAULTS_SECRET_WPSWATCH
    if integration.is_traptagger_site:
        return settings.DISPATCHER_DEFAULTS_SECRET_TRAPTAGGER
    return settings.DISPATCHER_DEFAULTS_SECRET


def create_dispatcher_for_integration(integration):
    """Create a DispatcherDeployment for a v2 Integration.

    Saving the row fires deploy_serverless_dispatcher.delay() via the
    DispatcherDeployment._post_save hook, so no explicit task call is needed.

    Raises ``TypeError`` if ``integration`` is not a v2 ``Integration`` —
    this helper sets the v2 ``integration`` FK; v1 callers must build the
    row inline with ``legacy_integration`` and ``gundi_version='v1'``.
    """
    # Local imports to avoid a circular import
    # (models -> tasks -> utils -> models / v2 models -> utils).
    from deployments.models import DispatcherDeployment
    from integrations.models.v2.models import Integration

    if not isinstance(integration, Integration):
        raise TypeError(
            "create_dispatcher_for_integration is v2-only; "
            f"got {type(integration).__name__}"
        )

    return DispatcherDeployment.objects.create(
        name=get_default_dispatcher_name(integration=integration),
        integration=integration,
        configuration=get_dispatcher_defaults_from_gcp_secrets(
            secret_id=_dispatcher_secret_id_for(integration)
        ),
    )


_DRAIN_CHECK_LOOKBACK_SECONDS = 600  # 10 minutes


def subscription_is_drained(subscription_name, configuration):
    """Check whether a push subscription's backlog is empty.

    Portal subscriptions are push subscriptions, not pull: Pub/Sub rejects a
    ``pull`` request against a push subscription with FAILED_PRECONDITION, so
    a subscriber-side "peek" can never succeed here (an earlier version of
    this helper tried exactly that and could never return True). Instead,
    this reads the Cloud Monitoring
    ``pubsub.googleapis.com/subscription/num_undelivered_messages`` metric
    for the subscription over the last 10 minutes and looks at the most
    recent data point: the subscription is drained iff that value is 0.

    If no data points are returned in the lookback window, we can't verify
    the backlog is empty, so this conservatively returns False (don't tear
    down what we can't confirm is drained) and logs why.

    Requires the caller's credentials to have the ``monitoring.timeSeries.list``
    IAM permission on the project.
    """
    env_vars = (configuration or {}).get("env_vars", {})
    project_id = env_vars.get("GCP_PROJECT_ID")
    project_name = f"projects/{project_id}"
    metric_filter = (
        'metric.type = "pubsub.googleapis.com/subscription/num_undelivered_messages" '
        f'AND resource.labels.subscription_id = "{subscription_name}"'
    )

    now = time.time()
    interval = monitoring_v3.TimeInterval()
    interval.end_time.seconds = int(now)
    interval.end_time.nanos = int((now - interval.end_time.seconds) * 10 ** 9)
    interval.start_time.seconds = int(now - _DRAIN_CHECK_LOOKBACK_SECONDS)
    interval.start_time.nanos = interval.end_time.nanos

    latest_end_seconds = None
    latest_value = None
    with monitoring_v3.MetricServiceClient() as client:
        results = client.list_time_series(
            request={
                "name": project_name,
                "filter": metric_filter,
                "interval": interval,
                "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
            }
        )
        for series in results:
            for point in series.points:
                end_seconds = point.interval.end_time.seconds
                if latest_end_seconds is None or end_seconds > latest_end_seconds:
                    latest_end_seconds = end_seconds
                    latest_value = point.value.int64_value

    if latest_value is None:
        logger.warning(
            f"No Monitoring data points for num_undelivered_messages on subscription "
            f"{subscription_name} in the last {_DRAIN_CHECK_LOOKBACK_SECONDS}s; can't verify "
            "the backlog is drained, treating as NOT drained."
        )
        return False
    return latest_value == 0

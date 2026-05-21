import logging
import json
from urllib.parse import urlparse
from google.api_core import exceptions as gcp_exceptions
from google.cloud import secretmanager
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
    """Return the leading hostname segment with a guaranteed letter prefix.

    GCP Cloud Run service IDs and Pub/Sub topic IDs must start with a
    lowercase letter. This helper enforces only that leading-character rule:
    it falls back to ``int`` for empty input and prefixes ``i`` when the
    first character is not a letter (e.g. numeric-leading hostnames like
    ``8fa1d0b7.fake-traptagger.org``). Callers are responsible for ensuring
    the rest of the constructed name uses only ``[a-z0-9-]`` — hostnames
    already satisfy that, so no additional normalization is applied here.
    """
    seg = host.split(".")[0] if host else ""
    if max_len is not None:
        seg = seg[:max_len]
    if not seg:
        return "int"
    if not seg[0].isalpha():
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
    """
    # Local import to avoid a circular import (models -> tasks -> utils).
    from deployments.models import DispatcherDeployment

    return DispatcherDeployment.objects.create(
        name=get_default_dispatcher_name(integration=integration),
        integration=integration,
        configuration=get_dispatcher_defaults_from_gcp_secrets(
            secret_id=_dispatcher_secret_id_for(integration)
        ),
    )

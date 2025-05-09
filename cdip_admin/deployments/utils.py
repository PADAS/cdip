import logging
import json
from urllib.parse import urlparse
from google.cloud import secretmanager
from django.conf import settings
from core.utils import generate_short_id_milliseconds


logger = logging.getLogger(__name__)


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


def get_default_dispatcher_name(integration, gundi_version="v2"):
    integration_url = integration.base_url if gundi_version == "v2" else integration.endpoint
    base_url = urlparse(str(integration_url).lower())
    subdomain = base_url.netloc.split(".")[0][:8]
    integration_type_id = integration.type.value if gundi_version == "v2" else integration.type.slug
    integration_type = integration_type_id.replace("_", "").lower().strip()[:5]
    integration_id = str(integration.id)
    return "-".join([subdomain, integration_type, "dis", integration_id])[:49]


def get_default_topic_name(integration, gundi_version="v2"):
    integration_url = integration.base_url if gundi_version == "v2" else integration.endpoint
    base_url = urlparse(str(integration_url).lower())
    subdomain = base_url.netloc.split(".")[0]
    integration_type_id = integration.type.value if gundi_version == "v2" else integration.type.slug
    integration_type = integration_type_id.replace("_", "").lower().strip()[:8]
    unique_suffix = generate_short_id_milliseconds()
    return "-".join([subdomain, integration_type, unique_suffix, "topic"])[:255]

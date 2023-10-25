import logging
import json
from urllib.parse import urlparse
from google.cloud import secretmanager
from django.conf import settings
from core.utils import generate_short_id_milliseconds


logger = logging.getLogger(__name__)


class PubSubDummyClient():

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


class FunctionsDummyClient():

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


def get_dispatcher_defaults_from_gcp_secrets():
    # Load default settings for serverless dispatchers from GCP secrets
    client = secretmanager.SecretManagerServiceClient()
    project_id = settings.GCP_PROJECT_ID
    secret_id = settings.DISPATCHER_DEFAULTS_SECRET
    secret_version_id = 'latest'
    name = f"projects/{project_id}/secrets/{secret_id}/versions/{secret_version_id}"
    response = client.access_secret_version(request={"name": name})
    return json.loads(response.payload.data.decode('UTF-8'))


def get_default_dispatcher_name(integration, gundi_version="v2"):
    integration_url = integration.base_url if gundi_version == "v2" else integration.endpoint
    base_url = urlparse(str(integration_url).lower())
    subdomain = base_url.netloc.split(".")[0]
    integration_id = str(integration.id)
    return f"{subdomain}-dispatcher-{integration_id}"


def get_default_topic_name(integration, gundi_version="v2"):
    integration_url = integration.base_url if gundi_version == "v2" else integration.endpoint
    base_url = urlparse(str(integration_url).lower())
    subdomain = base_url.netloc.split(".")[0]
    unique_suffix = generate_short_id_milliseconds()
    return f"{subdomain}-dispatcher-{unique_suffix}-topic"
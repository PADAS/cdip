import base64
import logging
import requests as requests
from django.conf import settings
from google.cloud import pubsub_v1
from rest_framework.utils import json
from gundi_core.schemas.v1 import DestinationTypes
from gundi_core.schemas.v2 import MovebankActions
from deployments.utils import get_default_topic_name


KONG_PROXY_URL = settings.KONG_PROXY_URL
CONSUMERS_PATH = "/consumers"
KEYS_PATH = "/key-auth"
INTEGRATION_TYPES_PATH = "/integration-types/"

logger = logging.getLogger(__name__)


class ConsumerCreationError(Exception):
    """Raised when consumer fails to create"""

    def __init__(self, message="Failed to Create API Consumer"):
        self.message = message
        super().__init__(self.message)

    def __str__(self):
        return f"{self.message}"


def create_api_consumer(integration):
    integration_type_obj = integration.type
    json_blob = {
        "integration_ids": [str(integration.id)],
        "integration_type": getattr(integration_type_obj, "value", getattr(integration_type_obj, "slug", "unknown")),
    }
    json_blob = json.dumps(json_blob)
    json_blob = json_blob.encode("utf-8")
    custom_id = base64.b64encode(json_blob)

    post_data = {"username": f"integration:{integration.id}", "custom_id": custom_id}

    post_url = f"{KONG_PROXY_URL}{CONSUMERS_PATH}"

    response = requests.post(post_url, data=post_data)

    if not response.ok and response.status_code != 409:
        logger.error("Failed to create API consumer. %s", response.text)
        raise ConsumerCreationError

    return True


def get_api_consumer_info(integration):
    response = requests.get(
        f"{KONG_PROXY_URL}{CONSUMERS_PATH}/integration:{str(integration.id)}"
    )
    response.raise_for_status()
    return response.json()


def patch_api_consumer_info(integration, data):
    patch_url = f"{KONG_PROXY_URL}{CONSUMERS_PATH}/integration:{str(integration.id)}"
    response = requests.patch(patch_url, data=data)
    response.raise_for_status()
    return response


def create_api_key(integration):
    api_key_url = (
        f"{KONG_PROXY_URL}{CONSUMERS_PATH}/integration:{str(integration.id)}{KEYS_PATH}"
    )

    response = requests.post(api_key_url)

    if not response.ok:
        raise ConsumerCreationError
        # TODO: delete consumer if api key creation fails?

    key = json.loads(response.content)["key"]

    return key


def get_api_key(integration):
    create_api_consumer(integration)

    # obtain key if permission checks pass
    response = requests.get(
        f"{KONG_PROXY_URL}{CONSUMERS_PATH}/integration:{str(integration.id)}{KEYS_PATH}"
    )

    if response.ok:
        try:
            data = response.json()["data"]
            api_key = data[0]["key"] if len(data) > 0 else None
            if api_key:
                return api_key
        except:
            logger.exception("failed getting API key for consumer %s", integration)

    return create_api_key(integration)


def does_movebank_permissions_config_changed(integration_config, gundi_version):
    if gundi_version == "v2":
        # is Movebank?
        if integration_config.integration.type.value != DestinationTypes.Movebank.value:
            return False
        # is PERMISSIONS action?
        if integration_config.action.value != MovebankActions.PERMISSIONS.value:
            return False
        # JSON config changed?
        if not integration_config.tracker.has_changed("data"):
            return False
        return True
    else:
        # is Movebank?
        if integration_config.type.slug != DestinationTypes.Movebank.value:
            return False
        # JSON config changed?
        if not integration_config.tracker.has_changed("additional") \
                or "permissions" not in integration_config.additional.keys():
            return False
        return True


def send_message_to_gcp_pubsub(message, topic):
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(settings.GCP_PROJECT_ID, topic)
    logger.info(
        f"Publish message to topic: {topic_path}, message: {message}",
        extra={
            "topic_path": topic_path,
            "message_body": message
        }
    )
    future = publisher.publish(topic_path, message.encode('utf-8'))
    logger.info(f"Published message ID: {future.result()}")


def get_dispatcher_topic_default_name(integration, gundi_version="v2"):

    if integration.is_er_site or integration.is_smart_site or integration.is_wpswatch_site or integration.is_traptagger_site:
        return get_default_topic_name(integration, gundi_version=gundi_version)
    if integration.is_mb_site:
        return settings.MOVEBANK_DISPATCHER_DEFAULT_TOPIC
    # Newer Connectors v2 with push data capabilities follow a naming convention
    if gundi_version == "v2":
        integration_type_prefix = integration.type.lower().strip().replace("_", "")
        return f"{integration_type_prefix}-push-data-topic"
    # Fallback to legacy kafka dispatchers topic
    return f"sintegrate.observations.transformed"


def build_mb_tag_id(device, gundi_version):
    if gundi_version == "v1":
        tag_id = (f"{device.inbound_configuration.type.slug}."
                  f"{device.external_id}."
                  f"{str(device.inbound_configuration.id)}")
    else:
        tag_id = (f"{device.integration.type.value}."
                  f"{device.external_id}."
                  f"{str(device.integration_id)}")

    return tag_id


def register_integration_type_in_kong(integration_type):
    kong_admin_url = f"{KONG_PROXY_URL}{INTEGRATION_TYPES_PATH}"
    response = requests.post(
        kong_admin_url,
        data={
            "integration_type": integration_type.value,
            "url": integration_type.service_url,
        }
    )
    response.raise_for_status()
    return response

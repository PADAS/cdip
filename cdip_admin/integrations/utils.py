import base64
import logging
import requests as requests
from django.conf import settings
from rest_framework.utils import json
from gundi_core.schemas.v1 import DestinationTypes
from gundi_core.schemas.v2 import MovebankActions


KONG_PROXY_URL = settings.KONG_PROXY_URL
CONSUMERS_PATH = "/consumers"
KEYS_PATH = "/key-auth"

logger = logging.getLogger(__name__)


class ConsumerCreationError(Exception):
    """Raised when consumer fails to create"""

    def __init__(self, message="Failed to Create API Consumer"):
        self.message = message
        super().__init__(self.message)

    def __str__(self):
        return f"{self.message}"


def create_api_consumer(integration):
    json_blob = {"integration_ids": [str(integration.id)]}
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



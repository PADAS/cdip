import logging
from enum import Enum

import requests
import time
import rest_framework.request
from cdip_admin import settings

logger = logging.getLogger(__name__)

oauth_token_url = f"{settings.KEYCLOAK_SERVER}/auth/realms/{settings.KEYCLOAK_REALM}/protocol/openid-connect/token"


def get_admin_access_token():
    logger.debug("Getting Keycloak Admin Access Token")
    payload = {
        "grant_type": "client_credentials",
        "client_id": settings.KEYCLOAK_ADMIN_CLIENT_ID,
        "client_secret": settings.KEYCLOAK_ADMIN_CLIENT_SECRET,
    }
    response = requests.post(oauth_token_url, data=payload)

    if response.status_code != 200:
        logger.warning(f"[{response.status_code}], {response.text}")
        return

    return response.json()



def add_base_url(request, url):
    if url and not url.startswith("http"):
        if not url.startswith("/"):
            url = "/" + url

        if isinstance(request, rest_framework.request.Request):
            request = request._request

        url = request.build_absolute_uri(url)
    return url


def generate_short_id_milliseconds():
    """
    Returns a short id as an alphanumeric string.
    The typical length will be 7-8 characters
    The id will be unique if the function is called in different milliseconds.
    """
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    # Epoch since year 2000 in milliseconds
    current_time_ms = int((time.time_ns() - time.mktime((2000, 1, 1, 0, 0, 0, 0, 0, 0)) * 1e9) // 1_000_000)
    # Convert to base to get a short id
    base = len(alphabet)
    short_id = ""
    while current_time_ms:
        current_time_ms, index = divmod(current_time_ms, base)
        short_id += alphabet[index]
    return short_id


class AutoNameEnum(Enum):
    def _generate_next_value_(name, start, count, last_values):
        return name


import logging
import requests

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

    if response.status_code == 200:
        return response.json()

    else:
        logger.warning(f"[{response.status_code}], {response.text}")


def add_base_url(request, url):
    if url and not url.startswith("http"):
        if not url.startswith("/"):
            url = "/" + url

        if isinstance(request, rest_framework.request.Request):
            request = request._request

        url = request.build_absolute_uri(url)
    return url

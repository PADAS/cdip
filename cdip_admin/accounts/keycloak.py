import logging

import requests

from cdip_admin import settings
from core.utils import get_admin_access_token


KEYCLOAK_SERVER = settings.KEYCLOAK_SERVER
KEYCLOAK_REALM = settings.KEYCLOAK_REALM
KEYCLOAK_CLIENT = settings.KEYCLOAK_CLIENT_ID

KEYCLOAK_ADMIN_API = f"{KEYCLOAK_SERVER}/auth/admin/realms/{KEYCLOAK_REALM}/"

# (connect_timeout, read_timeout) for outbound Keycloak admin calls.
# Bounds the time a portal request can spend blocked on Keycloak.
KEYCLOAK_HTTP_TIMEOUT = (5, 10)

logger = logging.getLogger(__name__)


def add_account(user):
    """Create a user in Keycloak.

    `user` is a dict with keys: ``email``, ``first_name``, ``last_name``.

    Returns ``True`` if the user exists in Keycloak after the call
    (newly created, already-present, or any 2xx). Returns ``False`` if
    the call could not be made (no admin token) or Keycloak returned an
    unexpected error.
    """
    token = get_admin_access_token()
    if not token:
        logger.warning("Cannot get a valid Keycloak admin access_token.")
        return False

    url = KEYCLOAK_ADMIN_API + "users"
    headers = {
        "authorization": f"{token['token_type']} {token['access_token']}",
        "Content-type": "application/json",
    }
    user_data = {
        "email": user["email"],
        "firstName": user["first_name"],
        "lastName": user["last_name"],
        "enabled": True,
    }

    try:
        response = requests.post(
            url=url, headers=headers, json=user_data, timeout=KEYCLOAK_HTTP_TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.error(f"Keycloak add_account network error: {exc}")
        return False

    if response.ok:
        logger.info("User created successfully")
        return True
    if response.status_code == 409:
        logger.info(f'Keycloak user {user["email"]} already exists.')
        return True

    logger.error(f"Error adding account: {response.status_code}, {response.text}")
    return False


def get_password_reset_link():
    return f"{KEYCLOAK_SERVER}/auth/realms/{KEYCLOAK_REALM}/login-actions/reset-credentials?client_id={KEYCLOAK_CLIENT}"

import logging

import requests
from django.http import JsonResponse

from cdip_admin import settings
from core.utils import get_admin_access_token


KEYCLOAK_SERVER = settings.KEYCLOAK_SERVER
KEYCLOAK_REALM = settings.KEYCLOAK_REALM
KEYCLOAK_CLIENT = settings.KEYCLOAK_CLIENT_ID

KEYCLOAK_ADMIN_API = f"{KEYCLOAK_SERVER}/auth/admin/realms/{KEYCLOAK_REALM}/"

logger = logging.getLogger(__name__)


def add_account(user):

    url = KEYCLOAK_ADMIN_API + "users"

    token = get_admin_access_token()

    if not token:
        logger.warning("Cannot get a valid access_token.")
        response = JsonResponse({"message": "You don't have access to this resource"})
        response.status_code = 403
        return response

    headers = {
        "authorization": f"{token['token_type']} {token['access_token']}",
        "Content-type": "application/json",
    }
    # Prepare the payload in the format expected by keycloak
    user_data = {
        "email": user["email"],
        "firstName": user["first_name"],
        "lastName": user["last_name"],
        "enabled": True  # Enable user in keycloak
    }
    response = requests.post(url=url, headers=headers, json=user_data)

    if response.ok:
        logger.info(f"User created successfully")
    elif response.status_code == 409:
        logger.info(f'Keycloak user {user["email"]} already exists.')
    else:
        logger.error(f"Error adding account: {response.status_code}], {response.text}")
        return False

    return True


def get_password_reset_link(user):
    return f"{KEYCLOAK_SERVER}/auth/realms/{KEYCLOAK_REALM}/login-actions/reset-credentials?client_id={KEYCLOAK_CLIENT}"

import requests
from django.http import JsonResponse
import logging

from cdip_admin import settings
from core.utils import get_admin_access_token

KEYCLOAK_SERVER = settings.KEYCLOAK_SERVER
KEYCLOAK_REALM = settings.KEYCLOAK_REALM
KEYCLOAK_CLIENT = settings.KEYCLOAK_CLIENT_ID

KEYCLOAK_ADMIN_API = f'{KEYCLOAK_SERVER}/auth/admin/realms/{KEYCLOAK_REALM}/'

logger = logging.getLogger(__name__)


def add_account(user):

    # remove properties keycloak does not expect and enable user
    user.pop('role')
    user.pop('organization')
    user["enabled"] = True

    url = KEYCLOAK_ADMIN_API + 'users'

    token = get_admin_access_token()

    if not token:
        logger.warning('Cannot get a valid access_token.')
        response = JsonResponse({'message': 'You don\'t have access to this resource'})
        response.status_code = 403
        return response

    headers = {
        "authorization": f"{token['token_type']} {token['access_token']}", 'Content-type': 'application/json'
    }

    response = requests.post(url=url, headers=headers, json=user)

    if response.ok:
        logger.info(f'User created successfully')
    elif response.status_code == 409:
        logger.info(f'Keycloak user {user["email"]} already exists.')
    else:
        logger.error(f'Error adding account: {response.status_code}], {response.text}')
        return False

    return True








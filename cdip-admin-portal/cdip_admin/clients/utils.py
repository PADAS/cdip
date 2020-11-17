import requests
from django.http import JsonResponse
import logging

from cdip_admin import settings
from core.utils import get_admin_access_token

KEYCLOAK_SERVER = settings.KEYCLOAK_SERVER
KEYCLOAK_REALM = settings.KEYCLOAK_REALM
KEYCLOAK_CLIENT = settings.KEYCLOAK_CLIENT_ID
KEYCLOAK_CLIENT_UUID = settings.KEYCLOAK_CLIENT_UUID
KEYCLOAK_ADMIN_API = f'{KEYCLOAK_SERVER}/auth/admin/realms/{KEYCLOAK_REALM}/'

logger = logging.getLogger(__name__)


def get_clients():
    url = KEYCLOAK_ADMIN_API + 'clients'

    token = get_admin_access_token()

    if not token:
        logger.warning('Cannot get a valid access_token.')
        response = JsonResponse({'message': 'You don\'t have access to this resource'})
        response.status_code = 403
        return response

    headers = {
        "authorization": f"{token['token_type']} {token['access_token']}"
    }

    response = requests.get(url=url, headers=headers)

    if response.status_code == 200:
        return response.json()

    else:
        logger.warning(f'[{response.status_code}], {response.text}')


def get_client(client_id):
    url = KEYCLOAK_ADMIN_API + 'clients/' + client_id

    token = get_admin_access_token()

    if not token:
        logger.warning('Cannot get a valid access_token.')
        response = JsonResponse({'message': 'You don\'t have access to this resource'})
        response.status_code = 403
        return response

    headers = {
        "authorization": f"{token['token_type']} {token['access_token']}"
    }

    response = requests.get(url=url, headers=headers)

    if response.status_code == 200:
        return response.json()

    else:
        logger.warning(f'[{response.status_code}], {response.text}')


def add_client(client_info):
    url = KEYCLOAK_ADMIN_API + 'clients'

    token = get_admin_access_token()

    if not token:
        logger.warning('Cannot get a valid access_token.')
        response = JsonResponse({'message': 'You don\'t have access to this resource'})
        response.status_code = 403
        return response

    headers = {
        "authorization": f"{token['token_type']} {token['access_token']}", 'Content-type': 'application/json'
    }

    response = requests.post(url=url, headers=headers, json=client_info)

    if response.status_code == 201:
        logger.info(f'Client created successfully')
        return True
    else:
        logger.error(f'Error adding client: {response.status_code}], {response.text}')
        return False


def update_client(client_info, client_id):
    url = KEYCLOAK_ADMIN_API + 'clients/' + client_id

    token = get_admin_access_token()

    if not token:
        logger.warning('Cannot get a valid access_token.')
        response = JsonResponse({'message': 'You don\'t have access to this resource'})
        response.status_code = 403
        return response

    headers = {
        "authorization": f"{token['token_type']} {token['access_token']}", 'Content-type': 'application/json'
    }

    response = requests.put(url=url, headers=headers, json=client_info)

    if response.status_code == 204:
        logger.info(f'Client updated successfully')
        return True
    else:
        logger.error(f'Error updating client: {response.status_code}], {response.text}')
        return False

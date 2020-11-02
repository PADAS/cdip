import requests
from django.http import JsonResponse
import logging

from cdip_admin import settings
from core.utils import get_admin_access_token

KEYCLOAK_SERVER = settings.KEYCLOAK_SERVER
KEYCLOAK_REALM = settings.KEYCLOAK_REALM
KEYCLOAK_ADMIN_API = f'{KEYCLOAK_SERVER}/auth/admin/realms/{KEYCLOAK_REALM}/'

logger = logging.getLogger(__name__)


def get_accounts():
    """
        List of all accounts
    """

    url = KEYCLOAK_ADMIN_API + 'users'

    token = get_admin_access_token()

    if not token:
        logger.warning('Cannot get a valid access_token.')
        response = JsonResponse({'message': 'You don\'t have access to this resource'})
        response.status_code = 403
        return response

    headers = {
        "authorization": f"{token['token_type']} {token['access_token']}"
    }

    try:
        response = requests.get(url=url, headers=headers)
    except Exception as e:
        logger.exception(e)
        response = JsonResponse({'message': 'An unexpected error occurred please retry the request. If the problem '
                                            'continues please contact a system administrator.'})
        response.status_code = 500
        return response

    if response.status_code == 200:
        return response.json()

    else:
        logger.warning(f'[{response.status_code}], {response.text}')
        return response


def get_account(user_id):
    url = KEYCLOAK_ADMIN_API + 'users/' + user_id

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


def add_account(account_info):
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

    response = requests.post(url=url, headers=headers, json=account_info)

    if response.status_code == 201:
        return response.json()
    else:
        logger.warning(f'[{response.status_code}], {response.text}')


def update_account(account_info, user_id):
    url = KEYCLOAK_ADMIN_API + 'users/' + user_id

    token = get_admin_access_token()

    if not token:
        logger.warning('Cannot get a valid access_token.')
        response = JsonResponse({'message': 'You don\'t have access to this resource'})
        response.status_code = 403
        return response

    headers = {
        "authorization": f"{token['token_type']} {token['access_token']}", 'Content-type': 'application/json'
    }

    response = requests.patch(url=url, headers=headers, json=account_info)

    if response.status_code == 200:
        return response.json()

    else:
        logger.warning(f'[{response.status_code}], {response.text}')











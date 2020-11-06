import requests
from django.http import JsonResponse
import logging

from core.utils import get_admin_access_token

AUTH0_DOMAIN = 'what'
auth0_url = f"https://{AUTH0_DOMAIN}/api/v2/"

logger = logging.getLogger(__name__)


def get_clients():
    url = auth0_url + 'clients'

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
    url = auth0_url + 'clients/' + client_id

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
    url = auth0_url + 'clients'

    client_info['grant_types'] = [
        'authorization_code',
        'implicit',
        'refresh_token',
        'client_credentials'
    ]

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
        return response.json()

    else:
        logger.warning(f'[{response.status_code}], {response.text}')


def update_client(client_info, client_id):
    url = auth0_url + 'clients/' + client_id

    token = get_admin_access_token()

    if not token:
        logger.warning('Cannot get a valid access_token.')
        response = JsonResponse({'message': 'You don\'t have access to this resource'})
        response.status_code = 403
        return response

    headers = {
        "authorization": f"{token['token_type']} {token['access_token']}", 'Content-type': 'application/json'
    }

    response = requests.patch(url=url, headers=headers, json=client_info)

    if response.status_code == 200:
        return response.json()

    else:
        logger.warning(f'[{response.status_code}], {response.text}')

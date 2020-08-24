import requests
from django.http import JsonResponse
import logging
from environ import Env

from core.utils import get_access_token

env = Env()
env.read_env()

AUTH0_DOMAIN = env.str('SOCIAL_AUTH_AUTH0_DOMAIN')
auth0_url = f"https://{AUTH0_DOMAIN}/api/v2/"

logger = logging.getLogger(__name__)


def get_accounts():
    """
        List of all accounts
    """

    url = auth0_url + 'users'

    token = get_access_token()

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
    url = auth0_url + 'users/' + user_id

    token = get_access_token()

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
    url = auth0_url + 'users'

    token = get_access_token()

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
    url = auth0_url + 'users/' + user_id

    token = get_access_token()

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











import http.client
import json
import logging
import requests
from django.http import JsonResponse
from environ import Env

env = Env()
env.read_env()

AUTH0_API_AUDIENCE = env.str('JWT_AUDIENCE')
AUTH0_DOMAIN = env.str('SOCIAL_AUTH_AUTH0_DOMAIN')
AUTH0_CLIENT_ID = env.str('AUTH0_CLIENT_ID')
AUTH0_CLIENT_SECRET = env.str('SOCIAL_AUTH_AUTH0_SECRET')

oauth_token_url = f"https://{AUTH0_DOMAIN}/oauth/token"
auth0_url = f"https://{AUTH0_DOMAIN}/api/v2/"

logger = logging.getLogger(__name__)


def get_access_token():
    logger.debug('Getting Auth0 Access Token')
    response = requests.post(oauth_token_url,
                             json={
                                 "client_id": 'dm9ayezQyQe5Xc4kBLKAnqy0Vut4wBpN',
                                 'client_secret': '2EAPIHslJJ9mAq9sl8rJQ9S6uX2vFZrPV4m5R4vADU3x0CYp1Ql3El2TLBd1xl0U',
                                 'audience': 'https://dev-fop-06qh.us.auth0.com/api/v2/',
                                 'grant_type': 'client_credentials'
                             })

    if response.status_code == 200:
        return response.json()

    else:
        logger.warning(f'[{response.status_code}], {response.text}')


def get_accounts():

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

    response = requests.get(url=url, headers=headers)

    if response.status_code == 200:
        return response.json()

    else:
        logger.warning(f'[{response.status_code}], {response.text}')


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


def get_user_permissions(user_id):
    url = auth0_url + 'users/' + user_id + '/permissions'

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








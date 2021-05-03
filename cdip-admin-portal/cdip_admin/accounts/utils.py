import requests
from django.http import JsonResponse
import logging

from accounts.models import AccountProfile
from cdip_admin import settings
from core.utils import get_admin_access_token

KEYCLOAK_SERVER = settings.KEYCLOAK_SERVER
KEYCLOAK_REALM = settings.KEYCLOAK_REALM
KEYCLOAK_CLIENT = settings.KEYCLOAK_CLIENT_ID
KEYCLOAK_CLIENT_UUID = settings.KEYCLOAK_CLIENT_UUID
KEYCLOAK_ADMIN_API = f'{KEYCLOAK_SERVER}/auth/admin/realms/{KEYCLOAK_REALM}/'

logger = logging.getLogger(__name__)


# def get_accounts():
#     """
#         List of all accounts
#     """
#
#     url = KEYCLOAK_ADMIN_API + 'users'
#
#     token = get_admin_access_token()
#
#     if not token:
#         logger.warning('Cannot get a valid access_token.')
#         response = JsonResponse({'message': 'You don\'t have access to this resource'})
#         response.status_code = 403
#         return response
#
#     headers = {
#         "authorization": f"{token['token_type']} {token['access_token']}"
#     }
#
#     try:
#         response = requests.get(url=url, headers=headers)
#     except Exception as e:
#         logger.exception(e)
#         response = JsonResponse({'message': 'An unexpected error occurred please retry the request. If the problem '
#                                             'continues please contact a system administrator.'})
#         response.status_code = 500
#         return response
#
#     if response.status_code == 200:
#         return response.json()
#
#     else:
#         logger.warning(f'[{response.status_code}], {response.text}')
#         return response
#
#
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
#
#
# def get_client_roles():
#     url = KEYCLOAK_ADMIN_API + 'clients/' + KEYCLOAK_CLIENT_UUID + '/roles'
#
#     token = get_admin_access_token()
#
#     if not token:
#         logger.warning('Cannot get a valid access_token.')
#         response = JsonResponse({'message': 'You don\'t have access to this resource'})
#         response.status_code = 403
#         return response
#
#     headers = {
#         "authorization": f"{token['token_type']} {token['access_token']}"
#     }
#
#     response = requests.get(url=url, headers=headers)
#
#     if response.status_code == 200:
#         return response.json()
#
#     else:
#         logger.warning(f'[{response.status_code}], {response.text}')
#
#
# def get_account_roles(user_id):
#     url = KEYCLOAK_ADMIN_API + 'users/' + user_id + '/role-mappings/clients/' + KEYCLOAK_CLIENT_UUID
#
#     token = get_admin_access_token()
#
#     if not token:
#         logger.warning('Cannot get a valid access_token.')
#         response = JsonResponse({'message': 'You don\'t have access to this resource'})
#         response.status_code = 403
#         return response
#
#     headers = {
#         "authorization": f"{token['token_type']} {token['access_token']}"
#     }
#
#     response = requests.get(url=url, headers=headers)
#
#     if response.status_code == 200:
#         return response.json()
#
#     else:
#         logger.warning(f'[{response.status_code}], {response.text}')


def add_account(user):
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

    if response.status_code == 201:
        logger.info(f'User created successfully')
        return True
    else:
        logger.error(f'Error adding account: {response.status_code}], {response.text}')
        return False


# def add_account_roles(roles, user_id):
#     url = KEYCLOAK_ADMIN_API + 'users/' + user_id + '/role-mappings/clients/' + KEYCLOAK_CLIENT_UUID
#
#     token = get_admin_access_token()
#
#     if not token:
#         logger.warning('Cannot get a valid access_token.')
#         response = JsonResponse({'message': 'You don\'t have access to this resource'})
#         response.status_code = 403
#         return response
#
#     headers = {
#         "authorization": f"{token['token_type']} {token['access_token']}", 'Content-type': 'application/json'
#     }
#
#     response = requests.delete(url=url, headers=headers)
#
#     if response.status_code == 204:
#         logger.info("Successfully deleted user roles. Now adding new.")
#         response = requests.post(url=url, headers=headers, json=roles)
#
#         if response.status_code == 204:
#             logger.info("User roles successfully updated.")
#             return True
#         else:
#             logger.error(f'Error managing account roles: {response.status_code}], {response.text}')
#             return False
#     else:
#         logger.error(f'Error deleting account roles: {response.status_code}], {response.text}')
#         return False
#
#
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

    response = requests.put(url=url, headers=headers, json=account_info)

    if response.status_code == 204:
        logger.info(f'User updated successfully')
        return True
    else:
        logger.error(f'Error updating account: {response.status_code}], {response.text}')
        return False

def get_user_profile(user_id):

    try:
        profile = AccountProfile.objects.get(user_id=user_id)
    except AccountProfile.DoesNotExist:
        profile = None

    return profile










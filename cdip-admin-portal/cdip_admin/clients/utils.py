import requests
from django.http import JsonResponse
import logging

from cdip_admin import settings
from clients.models import InboundClientResource
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


def get_client_by_client_id(client_id):
    url = KEYCLOAK_ADMIN_API + 'clients/'
    params = {'clientId': client_id}

    token = get_admin_access_token()

    if not token:
        logger.warning('Cannot get a valid access_token.')
        response = JsonResponse({'message': 'You don\'t have access to this resource'})
        response.status_code = 403
        return response

    headers = {
        "authorization": f"{token['token_type']} {token['access_token']}"
    }

    response = requests.get(url=url, headers=headers, params=params, timeout=(2, 10))

    if response.status_code == 200:
        return response.json()

    else:
        logger.warning(f'[{response.status_code}], {response.text}')


def add_client(client_info, type_id):
    url = KEYCLOAK_ADMIN_API + 'clients'
    
    client_info = get_default_client_settings(client_info)

    authorizationSettings = build_authorization_settings(type_id)

    client_info['authorizationSettings'] = authorizationSettings
    
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
        location = response.headers['Location']
        client_id = location.split('/')[-1]
        logger.info(f'Client created successfully')
        return client_id
    else:
        logger.error(f'Error adding client: {response.status_code}], {response.text}')
        return None


def update_client(client_info, client_id):
    url = KEYCLOAK_ADMIN_API + 'clients/' + client_id

    client_info = get_default_client_settings(client_info)

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


def build_authorization_settings(type_id):
    authorizationSettings = {}
    resources_config = InboundClientResource.objects.filter(type__id=type_id)
    scopes = []
    resources = []
    for resource_config in resources_config:
        resource = {}
        resource['name'] = resource_config.resource
        resource['displayName'] = resource_config.resource
        resource_scope = []
        for config in resource_config.scopes.all():
            scope = {'name': config.scope, 'displayName': config.scope}
            if scope not in scopes:
                scopes.append(scope)
            resource_scope.append(scope)
        resource['scopes'] = resource_scope
        resource['type'] = 'urn:***REMOVED***:resources:default'
        resources.append(resource)

    authorizationSettings['resources'] = resources
    authorizationSettings['scopes'] = scopes
    return authorizationSettings


def get_default_client_settings(client_info):

    client_info['clientAuthenticatorType'] = 'client-secret'
    client_info['serviceAccountsEnabled'] = 'true'
    client_info['authorizationServicesEnabled'] = 'true'
    client_info["bearerOnly"] = 'false'
    client_info["enabled"] = 'true'
    client_info["publicClient"] = 'false'

    return client_info

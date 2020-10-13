import http.client
import json
import logging
import requests
from django.http import JsonResponse
from environ import Env

from profiles.models import AccountProfile

env = Env()
env.read_env()

AUTH0_API_AUDIENCE = env.str('JWT_AUDIENCE')
AUTH0_DOMAIN = env.str('SOCIAL_AUTH_AUTH0_DOMAIN')
AUTH0_CLIENT_ID = env.str('AUTH0_CLIENT_ID')
AUTH0_CLIENT_SECRET = env.str('SOCIAL_AUTH_AUTH0_SECRET')
AUTH0_MANAGEMENT_AUDIENCE = env.str('AUTH0_MANAGEMENT_AUDIENCE')
AUTH0_MANAGEMENT_CLIENT_ID = env.str('AUTH0_MANAGEMENT_CLIENT_ID')

oauth_token_url = f"https://{AUTH0_DOMAIN}/oauth/token"
auth0_url = f"https://{AUTH0_DOMAIN}/api/v2/"

logger = logging.getLogger(__name__)


def get_access_token():
    logger.debug('Getting Auth0 Access Token')
    response = requests.post(oauth_token_url,
                             json={
                                 "client_id": AUTH0_MANAGEMENT_CLIENT_ID,
                                 'client_secret': AUTH0_CLIENT_SECRET,
                                 'audience': AUTH0_MANAGEMENT_AUDIENCE,
                                 'grant_type': 'client_credentials'
                             })

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


# def get_user_perms(args):
#     for arg in args:
#         if hasattr(arg, 'user'):
#             auth0user = arg.user.social_auth.get(provider='auth0')
#             permissions = get_user_permissions(auth0user.uid)
#             return permissions
#
#
# def requires_permission(required_permission: object) -> object:
#     """Determines if the required permission is assigned to a User
#     Args:
#         required_permission (str): The permission required to access the resource
#     """
#     def require_permission(f):
#         @wraps(f)
#         def decorated(*args, **kwargs):
#             permissions = get_user_perms(args)
#             for permission in permissions:
#                 permission_name = permission['permission_name']
#                 if permission_name == required_permission:
#                     return f(*args, **kwargs)
#             response = JsonResponse({'message': 'You don\'t have access to this resource'})
#             response.status_code = 403
#             return response
#         return decorated

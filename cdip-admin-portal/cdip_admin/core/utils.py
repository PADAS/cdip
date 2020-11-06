import logging
import requests

from cdip_admin import settings

logger = logging.getLogger(__name__)

KEYCLOAK_SERVER = settings.KEYCLOAK_SERVER
KEYCLOAK_ADMIN_REALM = settings.KEYCLOAK_ADMIN_REALM
KEYCLOAK_ADMIN_CLIENT_ID = settings.KEYCLOAK_ADMIN_CLIENT_ID
KEYCLOAK_ADMIN_CLIENT_SECRET = settings.KEYCLOAK_ADMIN_CLIENT_SECRET

oauth_token_url = f"{KEYCLOAK_SERVER}/auth/realms/{KEYCLOAK_ADMIN_REALM}/protocol/openid-connect/token"


def get_admin_access_token():
    logger.debug('Getting Keycloak Admin Access Token')
    payload = {
        'grant_type': 'client_credentials',
        'client_id': KEYCLOAK_ADMIN_CLIENT_ID,
        'client_secret': KEYCLOAK_ADMIN_CLIENT_SECRET,
    }
    response = requests.post(oauth_token_url,
                             data=payload)

    if response.status_code == 200:
        return response.json()

    else:
        logger.warning(f'[{response.status_code}], {response.text}')


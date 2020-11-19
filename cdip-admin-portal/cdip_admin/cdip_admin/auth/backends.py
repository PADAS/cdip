import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone
from jose.exceptions import (
    ExpiredSignatureError,
    JWTClaimsError,
    JWTError,
)
from keycloak.exceptions import KeycloakClientError

from cdip_admin.auth.services import oidc_profile

logger = logging.getLogger(__name__)


class KeycloakAuthorizationBase(object):

    def get_user(self, user_id):
        user_model = get_user_model()

        try:
            user = user_model.objects.select_related('oidc_profile__realm').get(
                pk=user_id)
        except user_model.DoesNotExist:
            return None

        if user.oidc_profile.refresh_expires_before and user.oidc_profile.refresh_expires_before > timezone.now():
            return user

        return None

    def get_all_permissions(self, user_obj, obj=None):
        if not user_obj.is_active or user_obj.is_anonymous or obj is not None:
            return set()
        if not hasattr(user_obj, '_keycloak_perm_cache'):
            user_obj._keycloak_perm_cache = self.get_keycloak_permissions(
                user_obj=user_obj)
        return user_obj._keycloak_perm_cache

    def get_keycloak_permissions(self, user_obj):
        if not hasattr(user_obj, 'oidc_profile'):
            return set()

        # rpt_decoded = oidc_profile.get_entitlement(oidc_profile=user_obj.oidc_profile)

        # Look up permissions (what was once called "entitlements") and use them to generate
        # permissions.
        client = user_obj.oidc_profile.realm.client
        access_token = oidc_profile.get_active_access_token(oidc_profile=user_obj.oidc_profile)

        # Not sure why but it requires adding audience argument.
        # TODO: Move this code to it's own function.
        auth_response = client.openid_api_client.uma_ticket(access_token, audience=client.client_id)
        rpt_decoded = client.openid_api_client.decode_token(
            token=auth_response['access_token'],
            key=client.realm.certs,
            algorithms=client.openid_api_client.well_known[
                'id_token_signing_alg_values_supported']
        )

        if settings.KEYCLOAK_PERMISSIONS_METHOD == 'role':
            permissions = [
                role for role in rpt_decoded['resource_access'].get(
                    user_obj.oidc_profile.realm.client.client_id,
                    {'roles': []}
                )['roles']
            ]

            return permissions

        elif settings.KEYCLOAK_PERMISSIONS_METHOD == 'resource':
            permissions = []
            for p in rpt_decoded['authorization'].get('permissions', []):
                if 'scopes' in p:
                    for scope in p['scopes']:
                        if '.' in p['rsname']:
                            app, model = p['rsname'].split('.', 1)
                            permissions.append(f'{app}.{scope}.{model}')
                        else:
                            permissions.append(f'{scope}.{p["rsname"]}')
                else:
                    permissions.append(p['rsname'])

            return permissions
        else:
            raise ImproperlyConfigured(
                'Unsupported permission method configured for '
                'Keycloak: {}'.format(settings.KEYCLOAK_PERMISSIONS_METHOD)
            )

    def has_perm(self, user_obj, perm, obj=None):

        if not user_obj.is_active:
            return False

        granted_perms = self.get_all_permissions(user_obj, obj)
        return perm in granted_perms


class KeycloakAuthorizationCodeBackend(KeycloakAuthorizationBase):

    def authenticate(self, request, code, redirect_uri):

        if not hasattr(request, 'realm'):
            raise ImproperlyConfigured(
                'Add BaseKeycloakMiddleware to middlewares')

        keycloak_openid_profile = oidc_profile.update_or_create_from_code(
                client=request.realm.client,
                code=code,
                redirect_uri=redirect_uri
            )

        return keycloak_openid_profile.user


class KeycloakPasswordCredentialsBackend(KeycloakAuthorizationBase):

    def authenticate(self, request, username, password):

        if not hasattr(request, 'realm'):
            raise ImproperlyConfigured(
                'Add BaseKeycloakMiddleware to middlewares')

        if not request.realm:
            # If request.realm does exist, but it is filled with None, we
            # can't authenticate using Keycloak
            return None

        try:
            keycloak_openid_profile = oidc_profile.update_or_create_from_password_credentials(
                    client=request.realm.client,
                    username=username,
                    password=password
                )
        except KeycloakClientError:
            logger.debug('KeycloakPasswordCredentialsBackend: failed to '
                         'authenticate.')
        else:
            return keycloak_openid_profile.user

        return None


class KeycloakIDTokenAuthorizationBackend(KeycloakAuthorizationBase):

    def authenticate(self, request, access_token):

        if not hasattr(request, 'realm'):
            raise ImproperlyConfigured(
                'Add BaseKeycloakMiddleware to middlewares')

        try:
            profile = oidc_profile.get_or_create_from_id_token(
                    client=request.realm.client,
                    id_token=access_token
                )
        except ExpiredSignatureError:
            # If the signature has expired.
            logger.debug('KeycloakBearerAuthorizationBackend: failed to '
                         'authenticate due to an expired access token.')
        except JWTClaimsError as e:
            logger.debug('KeycloakBearerAuthorizationBackend: failed to '
                         'authenticate due to failing claim checks: "%s"'
                         % str(e))
        except JWTError:
            # The signature is invalid in any way.
            logger.debug('KeycloakBearerAuthorizationBackend: failed to '
                         'authenticate due to a malformed access token.')
        else:
            return profile.user

        return None

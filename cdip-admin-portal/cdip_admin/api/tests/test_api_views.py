import uuid
from typing import NamedTuple, Any

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db
from unittest.mock import patch

from django_keycloak.models import OpenIdConnectProfile, Realm, Server


@patch('cdip_admin.utils.decode_token')
@patch('api.views.get_user_perms')
def test_get_integration_type_list(mock_get_user_perms, mock_decode_token, client, django_user_model, inbound_integration_user):

        mock_get_user_perms.return_value = inbound_integration_user.user_permissions
        mock_decode_token.return_value = inbound_integration_user.decoded_jwt

        client.force_login(inbound_integration_user.user)

        response = client.get(reverse("inboundintegrationtype_list"), HTTP_AUTHORIZATION=f'Bearer {inbound_integration_user.bearer_token}')
        print(response.json())
        print('Call count: %s' % (mock_get_user_perms.call_count,))
        assert response.status_code == 200


class IntegrationUser(NamedTuple):
    user_permissions: list = []
    decoded_jwt: dict = {}
    user: Any = None
    bearer_token: str = ''

@pytest.fixture
def inbound_integration_user(db, django_user_model):
    password = django_user_model.objects.make_random_password()
    user_const = dict(last_name='Owen', first_name='Harry')

    user_id = str(uuid.uuid4())
    user = django_user_model.objects.create_superuser(
        user_id, 'harry.owen@vulcan.com', password,
        **user_const)

    realm = Realm.objects.create(server=Server.objects.create(url='http://tempuri.org'),
                                 _certs=CERTS, _well_known_oidc=WELL_KNOWN_OIDC)
    oidc_profile = OpenIdConnectProfile.objects.create(user=user, realm=realm, sub=user.username)

    iu = IntegrationUser(user_permissions=['read:inboundintegrationtype', 'core.admin'],
                         decoded_jwt={'sub': user_id},
                         user=user,
                         bearer_token='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyLCJraWQiOiJhc2RmYXNkZiJ9.MCbn2FuYX5mpVE20t6J7JmqFCWRTIi21wM7FOjm8ZSo')

    return iu

# These are dummy values, as placeholders in mocked testing.
CERTS = "{\"keys\": [{\"kid\": \"ZKyVfAMEXNeHVOHPCC61Uz726nuAx14NYtfNPswSwJk\", \"kty\": \"RSA\", \"alg\": \"RS256\", \"use\": \"sig\", \"n\": \"gPnFfQALNHbiAHY2Pq32ka_8PYvuWFuw_qdLXJxP88lFSEaO66wc8KnXJBsn02DqsOL2qk5tzlORW8EHl_4UuGrZzVFsZCcr6FRJOCowPAU8ksjn81_BvO1kAD5NNgnBmZ5W8pso4VlVr2Mg7Fs6FXmuxhOvS3G-OpmlXFiYAkV3r2n7SseriS-VjBNBPzV-skFTZjP6qovi7BME2vW-sAKptmlqBlrHtL8c37ge3eX0n2s-XYkqm-2V94LM9n6E02LwxR4GhLs3UmXgB9h8r_3J9c0Yn4ydnvEDWJP92d7R7reWzl0TkHnUS8Vd74LET7fzPu3_24XYlEX8BO_UCw\", \"e\": \"AQAB\", \"x5c\": [\"MIICnzCCAYcCBgF1H0yVSjANBgkqhkiG9w0BAQsFADATMREwDwYDVQQDDAhjZGlwLWRldjAeFw0yMDEwMTMwMDEwMTRaFw0zMDEwMTMwMDExNTRaMBMxETAPBgNVBAMMCGNkaXAtZGV2MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAgPnFfQALNHbiAHY2Pq32ka/8PYvuWFuw/qdLXJxP88lFSEaO66wc8KnXJBsn02DqsOL2qk5tzlORW8EHl/4UuGrZzVFsZCcr6FRJOCowPAU8ksjn81/BvO1kAD5NNgnBmZ5W8pso4VlVr2Mg7Fs6FXmuxhOvS3G+OpmlXFiYAkV3r2n7SseriS+VjBNBPzV+skFTZjP6qovi7BME2vW+sAKptmlqBlrHtL8c37ge3eX0n2s+XYkqm+2V94LM9n6E02LwxR4GhLs3UmXgB9h8r/3J9c0Yn4ydnvEDWJP92d7R7reWzl0TkHnUS8Vd74LET7fzPu3/24XYlEX8BO/UCwIDAQABMA0GCSqGSIb3DQEBCwUAA4IBAQBeC81EXCdbByw6FzpvlY1SncfN89qTLVlw3g3nO2UOXg4wvT/FGYXawaljCW9NgA9FdcCJ2NDSBOpPIsJM3++rSxTIHIqcgGV9YdRPjoCe6DB/ndKSkz7U6HNE3sj3z17VZUMRr0KNE9s4t1i7Eju0q3SroAXC6XTcnvzEyqoSMSsfG40LQxPkGcpRL0GYf+8ffQrsRH/pMSqm8tN/tpiPRSQxDvIPadHg0aRhGvDgxK68oCE6Qhr7p3ZqDdRRrNojLuyquHpmS/pu+NdIVgMjGAp9bCYijN7/gC0v9AVi072E4dawug+iH2ohELKE/AehvQ7c9OdHH7PyiGQwRhWR\"], \"x5t\": \"Tn_-Q7glIr8faA-lbikBxqDdrNs\", \"x5t#S256\": \"m1dipJ7cd-QJXZlPseT0C4zT1YdwhyT4deMqDIPJGy0\"}]}",
WELL_KNOWN_OIDC = "{\"issuer\": \"https://cdip-auth.pamdas.org/auth/realms/cdip-dev\", \"authorization_endpoint\": \"https://cdip-auth.pamdas.org/auth/realms/cdip-dev/protocol/openid-connect/auth\", \"token_endpoint\": \"https://cdip-auth.pamdas.org/auth/realms/cdip-dev/protocol/openid-connect/token\", \"introspection_endpoint\": \"https://cdip-auth.pamdas.org/auth/realms/cdip-dev/protocol/openid-connect/token/introspect\", \"userinfo_endpoint\": \"https://cdip-auth.pamdas.org/auth/realms/cdip-dev/protocol/openid-connect/userinfo\", \"end_session_endpoint\": \"https://cdip-auth.pamdas.org/auth/realms/cdip-dev/protocol/openid-connect/logout\", \"jwks_uri\": \"https://cdip-auth.pamdas.org/auth/realms/cdip-dev/protocol/openid-connect/certs\", \"check_session_iframe\": \"https://cdip-auth.pamdas.org/auth/realms/cdip-dev/protocol/openid-connect/login-status-iframe.html\", \"grant_types_supported\": [\"authorization_code\", \"implicit\", \"refresh_token\", \"password\", \"client_credentials\"], \"response_types_supported\": [\"code\", \"none\", \"id_token\", \"token\", \"id_token token\", \"code id_token\", \"code token\", \"code id_token token\"], \"subject_types_supported\": [\"public\", \"pairwise\"], \"id_token_signing_alg_values_supported\": [\"PS384\", \"ES384\", \"RS384\", \"HS256\", \"HS512\", \"ES256\", \"RS256\", \"HS384\", \"ES512\", \"PS256\", \"PS512\", \"RS512\"], \"id_token_encryption_alg_values_supported\": [\"RSA-OAEP\", \"RSA1_5\"], \"id_token_encryption_enc_values_supported\": [\"A256GCM\", \"A192GCM\", \"A128GCM\", \"A128CBC-HS256\", \"A192CBC-HS384\", \"A256CBC-HS512\"], \"userinfo_signing_alg_values_supported\": [\"PS384\", \"ES384\", \"RS384\", \"HS256\", \"HS512\", \"ES256\", \"RS256\", \"HS384\", \"ES512\", \"PS256\", \"PS512\", \"RS512\", \"none\"], \"request_object_signing_alg_values_supported\": [\"PS384\", \"ES384\", \"RS384\", \"HS256\", \"HS512\", \"ES256\", \"RS256\", \"HS384\", \"ES512\", \"PS256\", \"PS512\", \"RS512\", \"none\"], \"response_modes_supported\": [\"query\", \"fragment\", \"form_post\"], \"registration_endpoint\": \"https://cdip-auth.pamdas.org/auth/realms/cdip-dev/clients-registrations/openid-connect\", \"token_endpoint_auth_methods_supported\": [\"private_key_jwt\", \"client_secret_basic\", \"client_secret_post\", \"tls_client_auth\", \"client_secret_jwt\"], \"token_endpoint_auth_signing_alg_values_supported\": [\"PS384\", \"ES384\", \"RS384\", \"HS256\", \"HS512\", \"ES256\", \"RS256\", \"HS384\", \"ES512\", \"PS256\", \"PS512\", \"RS512\"], \"claims_supported\": [\"aud\", \"sub\", \"iss\", \"auth_time\", \"name\", \"given_name\", \"family_name\", \"preferred_username\", \"email\", \"acr\"], \"claim_types_supported\": [\"normal\"], \"claims_parameter_supported\": false, \"scopes_supported\": [\"openid\", \"offline_access\", \"profile\", \"email\", \"address\", \"phone\", \"roles\", \"web-origins\", \"microprofile-jwt\", \"openid\", \"given_name\", \"family_name\", \"userinfo\", \"realm-management\", \"integrations:view\", \"integration\", \"chrisdo-local\"], \"request_parameter_supported\": true, \"request_uri_parameter_supported\": true, \"code_challenge_methods_supported\": [\"plain\", \"S256\"], \"tls_client_certificate_bound_access_tokens\": true}"

import logging

import json
import jwt
from django.contrib.auth import authenticate
from jose import JWTError
from jose import jwt
from six.moves.urllib.request import urlopen
from cdip_admin import settings

KEYCLOAK_SERVER = settings.KEYCLOAK_SERVER
KEYCLOAK_REALM = settings.KEYCLOAK_REALM
KEYCLOAK_CLIENT_ID = settings.KEYCLOAK_CLIENT_ID
KEYCLOAK_CLIENT_SECRET = settings.KEYCLOAK_CLIENT_SECRET
JWKS_LOCATION = (
    f"{KEYCLOAK_SERVER}/auth/realms/{KEYCLOAK_REALM}/protocol/openid-connect/certs"
)

logger = logging.getLogger(__name__)


def jwt_decode_token(token):

    return decode_token(token)


def decode_token(token: str):
    try:
        unverified_header = jwt.get_unverified_header(token)
        jwks = get_json_web_keyset()

        token_data = parse_jwt_token(jwks, unverified_header, token)

        # For our purposes, we only want the subject.
        subject: str = token_data.get("sub")
        if subject is None:
            raise
    except JWTError:
        raise

    return token_data


def get_json_web_keyset():

    jsonurl = urlopen(JWKS_LOCATION)
    jwks = json.loads(jsonurl.read())

    _json_web_keyset = jwks

    return _json_web_keyset

    _json_web_keyset = None


def parse_jwt_token(jwks, unverified_header, token):

    rsa_key = {}
    payload = None
    for key in jwks["keys"]:
        if key["kid"] == unverified_header["kid"]:
            rsa_key = {
                "kty": key["kty"],
                "kid": key["kid"],
                "use": key["use"],
                "n": key["n"],
                "e": key["e"],
            }
        if rsa_key:
            try:
                payload = jwt.decode(
                    token,
                    rsa_key,
                    algorithms=[
                        "RS256",
                    ],
                    audience=KEYCLOAK_CLIENT_ID,
                    issuer=f"{KEYCLOAK_SERVER}/auth/realms/{KEYCLOAK_REALM}",
                    options={"verify_at_hash": False},
                )

            except jwt.ExpiredSignatureError:
                raise
            except jwt.JWTClaimsError:
                raise
            except Exception as e:
                logger.exception("Unexpected error when decoding a JWT")
                raise

            return payload


def parse_bool(text):
    """Return a boolean from the passed in text"""
    TRUE_VALUES = ["true", "1", "yes", "ok", "okay"]
    if isinstance(text, bool):
        return text
    if isinstance(text, str) and text.lower() in TRUE_VALUES:
        return True
    return False

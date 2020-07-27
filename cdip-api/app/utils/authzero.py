import json
import logging

from fastapi import HTTPException
from jose import jwt
from six.moves.urllib.request import urlopen

import app.settings

logger = logging.getLogger(__name__)


def get_json_web_keyset():
    '''
    Get the key once and cache it.
    :return: public key

    See https://auth0.com/docs/tokens/concepts/jwks for detailed information about
    JSON Web Key Sets.

    TODO: Verify that this keyset is truly additive (so we don't have to worry about expiration).
    '''

    global _json_web_keyset
    if not _json_web_keyset:
        jsonurl = urlopen(f"https://{app.settings.AUTH0_DOMAIN}/.well-known/jwks.json")
        jwks = json.loads(jsonurl.read())
        logger.debug('Fetched Json Web Key Set: %s', jwks)
        _json_web_keyset = jwks

    return _json_web_keyset


_json_web_keyset = None


def parse_authzero_token(jwks, unverified_header, token):
    '''
    Parse an Auth0 Token.

    This function is adapted from some sample code Auth0 provides in manuals.

    :param jwks: public key from our Auth0 tenant.
    :param unverified_header: raw token from header.
    :param token:
    :return: dict - JSON Web Token
    '''
    rsa_key = {}
    payload = None
    for key in jwks["keys"]:
        if key["kid"] == unverified_header["kid"]:
            rsa_key = {
                "kty": key["kty"],
                "kid": key["kid"],
                "use": key["use"],
                "n": key["n"],
                "e": key["e"]
            }
        if rsa_key:
            try:
                payload = jwt.decode(
                    token,
                    rsa_key,
                    algorithms=app.settings.AUTH0_ALGORITHMS,
                    audience=app.settings.AUTH0_API_AUDIENCE,
                    issuer=f"https://{app.settings.AUTH0_DOMAIN}/"
                )

            except jwt.ExpiredSignatureError:
                raise HTTPException(
                    status_code=401,
                    detail='Authorization token expired')
            except jwt.JWTClaimsError:
                raise HTTPException(
                    status_code=401,
                    detail='Incorrect claims, check the audience and issuer.')
            except Exception as e:
                logging.warning(e, exc_info=True)
                raise HTTPException(
                    status_code=401,
                    detail='Unable to parse authentication token')

    return payload




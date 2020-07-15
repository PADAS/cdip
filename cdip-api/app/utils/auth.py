import json
import logging
import os
from fastapi import HTTPException, Header
from six.moves.urllib.request import urlopen
from jose import jwt, exceptions


logging.basicConfig(format='%(asctime)s %(message)s',
    datefmt='%m/%d/%Y %I:%M:%S %p',
    level=logging.os.environ.get('LOGGING_LEVEL', 'INFO'))

AUTH0_DOMAIN = os.environ.get('AUTH0_DOMAIN', '')

AUTH0_API_AUDIENCE = os.environ.get('AUTH0_API_AUDIENCE', '')

AUTH0_ALGORITHMS = os.environ.get( 'AUTH0_ALGORITHMS', 'RS256')

# hacking in my previous settings values
from app import settings
AUTH0_DOMAIN = settings.SOCIAL_AUTH_AUTH0_DOMAIN
AUTH0_API_AUDIENCE = 'https://dev-fop-06qh.us.auth0.com/api/v2/'
AUTH0_ALGORITHMS = settings.ALGORITHMS

def get_token_auth_header(authorization):
    '''
    Pull apart the authorization header.
    :param authorization:
    :return:
    '''
    parts = authorization.split()

    if parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=401, 
            detail='Authorization header must start with Bearer')
    elif len(parts) == 1:
        raise HTTPException(
            status_code=401, 
            detail='Authorization token not found')
    elif len(parts) > 2:
        raise HTTPException(
            status_code=401, 
            detail='Authorization header be Bearer token')
    
    token = parts[1]

    return token


def get_payload(jwks, unverified_header, token):
    '''
    Parse a token.
    :param jwks: public key from our Auth0 tenant.
    :param unverified_header: raw token from header.
    :param token:
    :return:
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
                    algorithms=AUTH0_ALGORITHMS,
                    audience=AUTH0_API_AUDIENCE,
                    issuer=f"https://{AUTH0_DOMAIN}/"
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


def get_jwks():
    '''
    Get the key once and cache it.
    :return: public key

    TODO: Consider how often to fetch public key. Or how to detect when it needs to be re-fetched.
    '''
    jsonurl = urlopen(f"https://{AUTH0_DOMAIN}/.well-known/jwks.json")
    jwks = json.loads(jsonurl.read())

    global get_jwks
    get_jwks = lambda: jwks
    
    return jwks


async def require_auth(authorization: str = Header(...)):

    token = get_token_auth_header(authorization)
    jwks = get_jwks()

    try:
        unverified_header = jwt.get_unverified_header(token)
    except exceptions.JWTError:
        raise HTTPException(
                    status_code=401, 
                    detail='Unable to decode authorization token headers')
    
    payload = get_payload(jwks, unverified_header, token)
    
    if not payload:
        raise HTTPException(
                    status_code=401, 
                    detail='Invalid authorization token')

    return payload
import logging

from fastapi import Depends, HTTPException, status
from fastapi.security import (
    OAuth2PasswordBearer
)
from jose import JWTError
from jose import jwt

import app.settings
from app.schemas import TokenData
from .authzero import get_json_web_keyset, parse_authzero_token

logger = logging.getLogger(__name__)


oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=app.settings.OAUTH_TOKEN_URL,
    scopes={"write:position": "Write a location for a device."},
)


async def get_current_user(token: str = Depends(oauth2_scheme)):

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"}, )

    try:
        unverified_header = jwt.get_unverified_header(token)
        jwks = get_json_web_keyset()

        token_data = parse_authzero_token(jwks, unverified_header, token)
        logger.debug('current_user token_data: %s', token_data)

        # For our purposes, we only want the subject.
        subject: str = token_data.get("sub")
        if subject is None:
            raise credentials_exception
        token_data = TokenData(subject=subject, scopes=token_data.get('scope').split())

    except JWTError:
        raise credentials_exception

    logger.debug('Token Payload: %s', token_data)
    return token_data




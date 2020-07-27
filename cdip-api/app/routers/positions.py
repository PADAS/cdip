import json
import logging
from typing import List, Optional

import walrus
from fastapi import APIRouter
from fastapi import Depends
from fastapi.security import (
    SecurityScopes
)
from pydantic import BaseModel, Field

import app.utils.auth as auth
from app.streams import get_position_stream

logger = logging.getLogger(__name__)

class Location(BaseModel):
    x: float = Field(default=0.0, ge=-180, le=180)
    y: float = Field(default=0.0, ge=-90, le=90)
    z: float = 0.0


class Position(BaseModel):
    id: Optional[int] = None
    device_id: str
    recorded_at: Optional[str] = None
    location: Location
    data: Optional[dict] = dict
    owner: str = 'na'


router = APIRouter()

@router.post("/")
def post_item(positions: List[Position],
              security_scopes: SecurityScopes,
              token: dict = Depends(auth.get_current_user),
              position_stream: walrus.containers.Stream = Depends(get_position_stream)):

    logger.debug('Security Scopes: %s', security_scopes)
    if security_scopes.scopes:
        authenticate_value = f'Bearer scope="{security_scopes.scope_str}"'
    else:
        authenticate_value = "Bearer"
    logger.debug('Authenticate value: %s', authenticate_value)

    for position in positions:

        # Downstream consumers will want to know the owner by subject.
        position.owner = token.subject

        logger.debug('Post_item. position: %s', position)

        id = position_stream.add({'data': json.dumps(position.dict(), default=str)})
        position.id = id

    return {'count': len(positions)}


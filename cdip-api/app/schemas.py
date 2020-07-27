from typing import List, Optional
from pydantic import BaseModel
from uuid import UUID
from typing import Union
from enum import Enum


class RadioStatusEnum(str, Enum):
    online = 'online'
    online_gps = 'online-gps'
    offline = 'offline'
    alarm = 'alarm'


class Location(BaseModel):
    x: float
    y: float
    z: float = 0.0


class Position(BaseModel):
    id: Optional[int] = None
    device_id: str
    recorded_at: str
    location: Location
    hdop: Optional[int] = None
    vdop: Optional[int] = None
    data: Optional[dict] = dict

    owner: str = 'na'
    integration_id: Union[int, str, UUID] = None

    voltage: Optional[float] = None
    temperature: Optional[float] = None

    radio_status: Optional[RadioStatusEnum] = None


class TokenData(BaseModel):
    subject: Optional[str] = None
    scopes: List[str] = []


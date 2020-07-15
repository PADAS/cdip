from typing import List, Optional
from pydantic import BaseModel, Field
import json
import walrus
from fastapi import APIRouter, HTTPException

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

db = walrus.Database(host='localhost', port=32769, db=0)

s1 = db.Stream('radios')

@router.post("/")
def post_item(position: Position):

    print(f'inside post_item. position: {position}')
    id = s1.add({'data': json.dumps(position.dict(), default=str)})
    position.id = id
    return position


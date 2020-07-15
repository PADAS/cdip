import os
from datetime import datetime, timedelta
import pytz

import uvicorn
from typing import List, Optional
from pydantic import BaseModel

import json

import walrus
# from app import auth
from fastapi import FastAPI, Request, Depends

from app.routers import items, positions
# from app.utils.auth import require_auth
import app.utils.auth as auth
app = FastAPI()

#db = walrus.Database(host='localhost', port=32769, db=0)

#s1 = db.Stream('radios')

root_path = os.environ.get('ROOT_PATH', '')
app = FastAPI(openapi_url=f'{root_path}/openapi.json',
title='CDIP API', description='CDIP Sensor API', version='1',)


class Location(BaseModel):
    x: float
    y: float
    z: float = 0.0
    
class Position(BaseModel):
    id: Optional[int] = None
    device_id: str
    recorded_at: Optional[str] = None
    location: Location
    data: Optional[dict] = dict
    owner: str = 'na'

@app.get("/")
def read_root(request: Request):
    return {"message": "Hello World"}

# @app.get("/items/{item_id}")
# def read_item(item_id: int, q: Optional[str] = None):
#     return {"item_id": item_id, "q": q}


#@app.post("/position")
#def post_item(position: Position):
#
#    id = s1.add({'data': json.dumps(position.dict(), default=str)})
#    position.id = id
#    return position

app.include_router(
    positions.router,
    prefix='/positions', tags=["sensors"],
    dependencies=[Depends(auth.require_auth)],
    responses={}
)

app.include_router(
    items.router,
    prefix="/items",
    tags=["items"],
    dependencies=[Depends(auth.require_auth)],
    responses={404: {"description": "Not found"}},
)

# @app.exception_handler(auth.AuthError)
# def handle_auth_error(ex):
#     response = str(ex.error)
#     response.status_code = ex.status_code
#     return response


# if __name__ == "__main__":
#     uvicorn.run("main:app", host="127.0.0.1", port=9500, log_level="info",)

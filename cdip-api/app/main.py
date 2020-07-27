import logging
import os

import uvicorn
from fastapi import FastAPI, Request

from app.routers import positions

logging.basicConfig(format='%(asctime)s %(message)s',
    datefmt='%m/%d/%Y %I:%M:%S %p',
    level=logging.os.environ.get('LOGGING_LEVEL', 'INFO'))

app = FastAPI()


# For running behind a proxy, we'll want to configure the root path for OpenAPI browser.
root_path = os.environ.get('ROOT_PATH', '')
app = FastAPI(openapi_url=f'{root_path}/openapi.json',
              title='CDIP API', description='CDIP Sensor API', version='1',)


@app.get("/")
def read_root(request: Request):
    print(f'request: {request}')
    return {"message": "CDIP Sensor API"}


app.include_router(positions.router, prefix='/positions', tags=["sensors"],
                   responses={})


if __name__ == "__main__":
    '''
    Run directly foor debugging and in an IDE.
    '''
    uvicorn.run("main:app", host="127.0.0.1", port=8000, log_level="info",)

# CDIP Sensors API

This is the beginning of a simple Sensors API for CDIP allowing clients to post "Positions".

## Developer Setup

You can run CDIP Sensors API locally, along with some test scripts to exercise it.

### Runtime Environment

Create a virtual environment.

```shell
python3.7 -m vevn venv
source venv/bin/activate
pip install -r requirements.txt
```

### App Environment

The App (as well as the test scripts) use `.env` for loading configuration information. You can find `cdip-api/.env-example` for a list of variables you'll need to provide.

This is where you configure your Auth0 tenant details. *Your Audience and Domain settings will be different.*

```shell
# Auth0 tenant settings.
AUTH0_ALGORITHMS=RS256
AUTH0_API_AUDIENCE='http://cdip-dev-chrisd.org'
AUTH0_DOMAIN='cdip-dev-chrisd.us.auth0.com'
```

Items prefixed with **REDIS_** will specify a Redis instance to push data into.
```shell
# Coordinates for a Redis Instance (where position data will be written to streams).
REDIS_HOST=localhost
REDIS_PORT=32768
REDIS_DB=0
```

Items prefixed with **PRODUCER_** are strictly for use with `cdip-api/test-utils/producer.py` which is a bare bones test script for generating data. It'll go away soon, but it's provided here as a convenience.

```shell
# These PRODUCER_ variables are only used by the producer.py test script.
PRODUCER_AUTH0_CLIENT_ID = 'put your client Id here.'
PRODUCER_AUTH0_CLIENT_SECRET = 'and put your client secret here.'
PRODUCER_CDIP_API = 'Put your CDIP API's URL here.
```

### Run the API Server

Once you've configured your environment (and started a Redis server) you can run the server directly using app.main like so:

```shell
src/cdip/cdip-api $ PYTHONPATH=. python3 app/main.py

INFO:     Started server process [82643]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

Alternatively you can run using a shell script that's provided:

```shell
src/cdip/cdip-api $ ./start_app.sh 

[2020-07-27 17:09:32 -0700] [82725] [INFO] Starting gunicorn 20.0.4
[2020-07-27 17:09:32 -0700] [82725] [INFO] Listening at: http://0.0.0.0:8000 (82725)
[2020-07-27 17:09:32 -0700] [82725] [INFO] Using worker: uvicorn.workers.UvicornWorker
[2020-07-27 17:09:32 -0700] [82730] [INFO] Booting worker with pid: 82730
[2020-07-27 17:09:32 -0700] [82731] [INFO] Booting worker with pid: 82731
[2020-07-27 17:09:32 -0700] [82732] [INFO] Booting worker with pid: 82732
[2020-07-27 17:09:32 -0700] [82733] [INFO] Booting worker with pid: 82733
[2020-07-27 17:09:33 -0700] [82730] [INFO] Started server process [82730]
[2020-07-27 17:09:33 -0700] [82732] [INFO] Started server process [82732]
[2020-07-27 17:09:33 -0700] [82731] [INFO] Started server process [82731]
[2020-07-27 17:09:33 -0700] [82730] [INFO] Waiting for application startup.
[2020-07-27 17:09:33 -0700] [82732] [INFO] Waiting for application startup.
[2020-07-27 17:09:33 -0700] [82731] [INFO] Waiting for application startup.
[2020-07-27 17:09:33 -0700] [82732] [INFO] Application startup complete.
[2020-07-27 17:09:33 -0700] [82731] [INFO] Application startup complete.
[2020-07-27 17:09:33 -0700] [82730] [INFO] Application startup complete.
[2020-07-27 17:09:33 -0700] [82733] [INFO] Started server process [82733]
[2020-07-27 17:09:33 -0700] [82733] [INFO] Waiting for application startup.
[2020-07-27 17:09:33 -0700] [82733] [INFO] Application startup complete.
```

### Test Utilities

***Produce*** some random position data and post to your CDIP Sensors API endpoint.

* The .env-example file includes variables prefixed with `PRODUCER_` and you'll want to fill them in for this test utility to work.

```shell
python3 /Users/chris/padas/cdip/cdip-api/test-utils/producer.py --device_id=my-radio-id
```

Start a ***Consumer*** that will read data from the back end stream and write to standard output. 

```shell
python3 /Users/chris/padas/cdip/cdip-api/test-utils/consumer.py
```


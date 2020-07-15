#!/bin/bash

gunicorn -w 4 -k uvicorn.workers.UvicornWorker app.main:app -b 0.0.0.0:9500

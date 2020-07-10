# Getting started with Airflow Examples

Initially this folder is organized for local development in a single node Airflow runtime.

This readme file can help get you started by identifying the right version of python and
by providing instructions for installing required packages in a virtual environment.

## Pre-requisites

* *nix environment
* Python 3.7+

## Create a Python Virtual Environment

I recommend installing a python virtual environment, likely in or near the folder where you've cloned this repository.

```python3 -m venv airflow-venv```

## Activate your virtual environment

```source airflow-venv/bin/activate```

## Install requirements

```pip installl -r dependencies/requirements.txt```

## Run Airflow Web Server

Out of the box, Airflow will create a configuration file and a database file. And by default these will be
created in `~/airflow`. This might be fine for you, but I recommend changing the location by setting 
a new value for `AIRFLOW_HOME`.

This example sets AIRFLOW_HOME to the current directory.

```export AIRFLOW_HOME=$(pwd)
airflow webserver
```

## Run Airflow Scheduler

Run an Airflow scheduler in a different termimal.

```export AIRFLOW_HOME=$(pwd)
airflow scheduler
```

## Configuration needed for running the savannah_streams DAG
The savannah_streams DAG uses Redis Streams as the datastore for observations being processed in the system, which requires Redis v5.0 or higher. Additionally, the following 3 connections need to be added to Airflow under Admin->Connections in the web UI
* Savannah tracking endpoint configuration: Add this as a connection of type HTTP. Set the Conn Id to ```savannah_api```. The Host field will likely be https://api.savannahtracking.co.ke. The Login and Password fields are also required.
* Destination endpoint configuration: This code assumes an ER instance as the destination. Add this as a connection of type HTTP. Set the Conn Id to ```cdip_destination```. The Host field will be a URL to an ER API, e.g., https://dev.pamdas.org/api/v1.0. Enter a valid ER auth token in the Password field.
* Redis configuration: Add this as a connection of type Redis. Set the Conn Id to ```redis_connection```. Enter the host name in the Host field (donot add the "redis://" or "https://" before the host name string). Enter a password if one is needed for access redis. 

The DAG uses 3 streams that get created when a task writes to them for the very first time. The stream names are currently hardcoded in the DAG.

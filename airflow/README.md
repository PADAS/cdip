# Getting started with Airflow Examples

Initially this folder is organized for local development in a single node Airflow runtime.

This readme file can help get you started by identifying the right version fo python and
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

## Run Airflow

```airflow webserver```



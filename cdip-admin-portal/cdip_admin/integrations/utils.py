import base64

import requests as requests
from django.conf import settings
from django.core.exceptions import PermissionDenied
from rest_framework.utils import json

KONG_PROXY_URL = settings.KONG_PROXY_URL
CONSUMERS_PATH = "/consumers"
KEYS_PATH = "/key-auth"


class ConsumerCreationError(Exception):
    """Raised when consumer fails to create"""
    def __init__(self, message="Failed to Create API Consumer"):
        self.message = message
        super().__init__(self.message)

    def __str__(self):
        return f'{self.message}'


def create_api_consumer(integration):
    json_blob = {"integration_ids": [str(integration.id)]}
    json_blob = json.dumps(json_blob)
    json_blob = json_blob.encode('utf-8')
    custom_id = base64.b64encode(json_blob)

    post_data = {'username': f'integration:{integration.id}',
                 'custom_id': custom_id}

    post_url = f'{KONG_PROXY_URL}{CONSUMERS_PATH}'

    response = requests.post(post_url, data=post_data)

    if not response.ok:
        raise ConsumerCreationError

    content = json.loads(response.content)
    consumer_id = content["id"]

    integration.consumer_id = consumer_id
    integration.save()

    return consumer_id


def create_api_key(consumer_id):

    api_key_url = f'{KONG_PROXY_URL}{CONSUMERS_PATH}/{consumer_id}{KEYS_PATH}'

    response = requests.post(api_key_url)

    if not response.ok:
        raise ConsumerCreationError
        # TODO: delete consumer if api key creation fails?

    key = json.loads(response.content)['key']

    return key


def get_api_key(integration):
    # permission checking
    get_url = f'{KONG_PROXY_URL}{CONSUMERS_PATH}/{integration.consumer_id}'
    response = requests.get(get_url)
    consumer = response.json()
    custom_id = consumer['custom_id']
    consumer_id = consumer['id']
    json_blob = custom_id.encode('utf-8')
    json_blob = base64.b64decode(json_blob)
    json_blob = json_blob.decode('utf-8')
    json_blob = json.loads(json_blob)
    integration_ids = json_blob['integration_ids']

    # check consumer is valid for this integration
    if str(integration.id) not in integration_ids:
        raise PermissionDenied

    # obtain key if permission checks pass
    api_key_url = f'{KONG_PROXY_URL}{CONSUMERS_PATH}/{consumer_id}{KEYS_PATH}'
    response = requests.get(api_key_url)
    api_keys = response.json()['data']

    # Use the first found key
    if api_keys:
        return api_keys[0]['key']
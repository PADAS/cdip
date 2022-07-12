import json
import logging
import os

import redis
import smartconnect
from integrations.models import OutboundIntegrationConfiguration
from smartconnect import SmartClient

logger = logging.getLogger(__name__)


# This is the cache used by Routing App
cache = redis.from_url(os.environ.get("REDIS_URL"))


def is_cached(ca_uuid):

    cache_key = f"cache:smart-ca:{ca_uuid}:datamodel"
    return cache.ttl(cache_key) > 1


def cache_dm(ca_uuid, ca_datamodel):

    cache_key = f"cache:smart-ca:{ca_uuid}:datamodel"

    cache.setex(
        name=cache_key,
        time=60 * 60 * 24 * 30,
        value=json.dumps(ca_datamodel.export_as_dict()),
    )


smartconnect.DEFAULT_TIMEOUT = (3.1, 180)


def primecache():
    oiclist = OutboundIntegrationConfiguration.objects.filter(
        type__slug="smart_connect"
    )

    for oic in oiclist:
        print(f"Processing {oic}")

        smartclient = SmartClient(
            api=oic.endpoint, username=oic.login, password=oic.password
        )

        for ca_uuid in oic.additional.get("ca_uuids", []):
            print(f"-- ca_uuid: {ca_uuid}")
            if is_cached(ca_uuid):
                continue
            try:
                ca_datamodel = smartclient.download_datamodel(ca_uuid=ca_uuid)
                cache_dm(ca_uuid, ca_datamodel)
            except Exception as e:
                print(f"Error on {oic}, {ca_uuid}, {e}")


def run(*args):
    primecache()

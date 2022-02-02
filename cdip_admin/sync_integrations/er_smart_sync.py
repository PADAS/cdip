import json
import logging
from urllib.parse import urlparse

from dasclient.dasclient import DasClient
from django.db.models import F

from integrations.models import InboundIntegrationConfiguration, OutboundIntegrationConfiguration

from smartconnect import SmartClient, utils
from smartconnect.er_sync_utils import build_earth_ranger_event_types, er_event_type_schemas_equal

logger = logging.getLogger(__name__)

CA_LABEL = 'Smart ER Integration Test CA [SMART_ER]'


def push_smart_ca_data_model_to_er_event_types():
    smart_config = OutboundIntegrationConfiguration.objects.get(type__slug='smart_connect', name__exact="SMART Connect 7.4.x")
    smart_client = SmartClient(api=smart_config.endpoint,
                               username=smart_config.login,
                               password=smart_config.password,
                               use_language_code='en')

    # TODO: Get list of all outbounds associated to inbound
    # ibc = InboundIntegrationConfiguration.objects.get(id=config.id)
    # er_destinations = OutboundIntegrationConfiguration.objects.filter(devicegroup__devices__inbound_configuration=ibc).\
    #     annotate(inbound_type_slug=F('devicegroup__devices__inbound_configuration__type__slug')).distinct()

    er_config = OutboundIntegrationConfiguration.objects.get(name__exact="ER SMART Test Site")

    provider_key = 'smart_connect'
    url_parse = urlparse(er_config.endpoint)

    das_client = DasClient(service_root=er_config.endpoint,
                     username=er_config.login,
                     password=er_config.password,
                     token=er_config.token,
                     token_url=f"{url_parse.scheme}://{url_parse.hostname}/oauth2/token",
                     client_id="das_web_client",
                     provider_key=provider_key)

    caslist = smart_client.get_conservation_areas()

    for ca in caslist:
        if ca.label == CA_LABEL:
            ca_uuid = ca.uuid
            break

    dm = smart_client.download_datamodel(ca_uuid=ca_uuid)
    dm_dict = dm.export_as_dict()

    event_types = build_earth_ranger_event_types(dm_dict)

    existing_event_categories = das_client.get_event_categories()
    event_category = next((x for x in existing_event_categories if x.get('value') == CA_LABEL), None)
    if not event_category:
        event_category = dict(value=CA_LABEL,
                              display=CA_LABEL)
        das_client.post_event_category(event_category)

    existing_event_types = das_client.get_event_types()
    try:
        for event_type in event_types:
            event_type_match = next((x for x in existing_event_types if x.get('value') == event_type.get('value')), None)
            if event_type_match:
                event_type_match_schema = das_client.get_event_schema(event_type.get('value'))
                if not er_event_type_schemas_equal(json.loads(event_type.get('schema')).get('schema'),
                                                   event_type_match_schema.get('schema')):
                    event_type['id'] = event_type_match.get('id')
                    das_client.patch_event_type(event_type)
            else:
                event_type['category'] = event_category.get('value')
                das_client.post_event_type(event_type)
    except Exception as e:
        logger.exception(f'Exception raised posting event type', extra=dict(event_type=event_type))
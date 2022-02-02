import json
from urllib.parse import urlparse

from dasclient.dasclient import DasClient
from django.db.models import F

from integrations.models import InboundIntegrationConfiguration, OutboundIntegrationConfiguration

from smartconnect import SmartClient, utils
from smartconnect.er_sync_utils import build_earth_ranger_event_types, er_event_type_schemas_equal

CA_LABEL = 'Smart ER Integration Test CA [SMART_ER]'


def push_smart_ca_data_model_to_er_event_types():
    config = InboundIntegrationConfiguration.objects.get(type__slug='smart_connect', name__exact="SMART Connect 7.4.X")
    smart_client = SmartClient(api=config.endpoint,
                               username=config.login,
                               password=config.password,
                               use_language_code='en')

    # TODO: Get list of all outbounds associated to inbound
    # ibc = InboundIntegrationConfiguration.objects.get(id=config.id)
    # er_destinations = OutboundIntegrationConfiguration.objects.filter(devicegroup__devices__inbound_configuration=ibc).\
    #     annotate(inbound_type_slug=F('devicegroup__devices__inbound_configuration__type__slug')).distinct()

    outbound_config = OutboundIntegrationConfiguration.objects.get(name__exact="ER SMART Test Site")

    provider_key = 'smart_connect'
    url_parse = urlparse(outbound_config.endpoint)

    return DasClient(service_root=outbound_config.endpoint,
                     username=outbound_config.login,
                     password=outbound_config.password,
                     token=outbound_config.token,
                     token_url=f"{url_parse.scheme}://{url_parse.hostname}/oauth2/token",
                     client_id="das_web_client",
                     provider_key=provider_key)

    caslist = smart_client.get_conservation_areas()

    for ca in caslist:
        if ca.label == CA_LABEL:
            ca_uuid = ca.uuid
            break

    # print(f'CA UUID: {ca_uuid}')
    # predicted_timezone = utils.guess_ca_timezone(ca)
    # print(f'{ca.label} -- Predicted_timezone: {predicted_timezone}')
    #
    # present = datetime.now(tz=pytz.utc)
    # print(f'Now is: {present.astimezone(predicted_timezone)} in {predicted_timezone}')

    dm = smart_client.download_datamodel(ca_uuid=ca_uuid)
    dm_dict = dm.export_as_dict()

    event_types = build_earth_ranger_event_types(dm_dict)

    existing_event_categories = das_client.get_event_categories()
    event_category = next((x for x in existing_event_categories if x.get('value') == CA_LABEL[0:40]), None)
    if not event_category:
        event_category = dict(value=CA_LABEL[0:40],
                              display=CA_LABEL[0:40])
        das_client.post_event_category(event_category)

    existing_event_types = das_client.get_event_types()
    try:
        for event_type in event_types:
            event_type_match = next((x for x in existing_event_types if x.get('value') == event_type.get('value')), None)
            if event_type_match:
                event_type_match_schema = das_client.get_event_schema(event_type.get('value'))
                if not er_event_type_schemas_equal(json.loads(event_type.get('schema')), event_type_match_schema):
                    # TODO: Update Das Client to update event type
                    pass
            else:
                event_type['category'] = event_category.get('value')
                das_client.post_event_type(event_type)
    except Exception as e:
        print(f'Exception raised posting event type {e}')
        print(dict(event_type=event_type))

    # smart_client.download_patrolmodel(ca_uuid=ca_uuid)
    # smart_client.download_missionmodel(ca_uuid=ca_uuid)
    #
    # present = datetime.now(tz=pytz.utc)
    #
    # smart_client.add_incident(ca_uuid=ca_uuid)
    # smart_client.add_patrol_trackpoint(ca_uuid=ca_uuid, device_id='dev-00009', x=-122.4526, y=48.4948, timestamp=present)
    # smart_client.add_mission(ca_uuid=ca_uuid)


if __name__ == '__main__':
    push_smart_ca_data_model_to_er_event_types()

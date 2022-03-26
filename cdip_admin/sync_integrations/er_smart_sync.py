import json
import logging
from urllib.parse import urlparse

from dasclient.dasclient import DasClient
from smartconnect import SmartClient
from smartconnect.er_sync_utils import build_earth_ranger_event_types, er_event_type_schemas_equal

from integrations.models import OutboundIntegrationConfiguration

logger = logging.getLogger(__name__)

CA_LABEL = 'Smart ER Integration Test CA [SMART_ER]'


class ERSMART_Synchronizer():
    def __init__(self, **kwargs):
        smart_integration_id = kwargs.get('smart_integration_id')
        er_integration_id= kwargs.get('er_integration_id')

        smart_config = OutboundIntegrationConfiguration.objects.get(id=smart_integration_id)
        er_config = OutboundIntegrationConfiguration.objects.get(id=er_integration_id)

        if not smart_config or not er_config:
            logger.exception(f"No configurations found for integration ids",
                             extra=dict(smart_integration_id=smart_integration_id,
                                        er_integration_id=er_integration_id))
            raise Exception("No configurations found for integration ids")

        self.smart_client = SmartClient(api=smart_config.endpoint,
                                        username=smart_config.login,
                                        password=smart_config.password,
                                        use_language_code='en')

        self.smart_ca_uuid = smart_config.additional.get('ca_uuid')

        provider_key = smart_config.type.slug
        url_parse = urlparse(er_config.endpoint)

        self.das_client = DasClient(service_root=er_config.endpoint,
                                    username=er_config.login,
                                    password=er_config.password,
                                    token=er_config.token,
                                    token_url=f"{url_parse.scheme}://{url_parse.hostname}/oauth2/token",
                                    client_id="das_web_client",
                                    provider_key=provider_key)

    def push_smart_ca_data_model_to_er_event_types(self):
        caslist = self.smart_client.get_conservation_areas()

        # TODO: Handle Group of CA's
        ca_match = False
        for ca in caslist:
            if str(ca.uuid) == self.smart_ca_uuid:
                ca_match = True
                break

        if not ca_match:
            logger.warning(f'Conservation Area not found', extra=dict(smart_ca_uuid=self.smart_ca_uuid))
            return

        dm = self.smart_client.download_datamodel(ca_uuid=self.smart_ca_uuid)
        dm_dict = dm.export_as_dict()

        event_types = build_earth_ranger_event_types(dm_dict)

        existing_event_categories = self.das_client.get_event_categories()
        event_category = next((x for x in existing_event_categories if x.get('value') == CA_LABEL), None)
        if not event_category:
            logger.info('Event Category not found in destination ER, creating now ...', extra=dict(value=CA_LABEL,
                                                                                                   display=CA_LABEL))
            event_category = dict(value=CA_LABEL,
                                  display=CA_LABEL)
            self.das_client.post_event_category(event_category)
        self.create_or_update_er_event_types(event_category, event_types)

    def create_or_update_er_event_types(self, event_category: str, event_types: dict):
        existing_event_types = self.das_client.get_event_types()
        try:
            for event_type in event_types:
                event_type_match = next((x for x in existing_event_types if x.get('value') == event_type.get('value')),
                                        None)
                if event_type_match:
                    event_type_match_schema = self.das_client.get_event_schema(event_type.get('value'))
                    if not er_event_type_schemas_equal(json.loads(event_type.get('schema')).get('schema'),
                                                       event_type_match_schema.get('schema')):
                        logger.info(f'Updating ER event type', extra=dict(value=event_type['value']))
                        event_type['id'] = event_type_match.get('id')
                        self.das_client.patch_event_type(event_type)
                else:
                    event_type['category'] = event_category.get('value')
                    logger.info(f'Creating ER event type', extra=dict(value=event_type['value'],
                                                                      category=event_type['category']))
                    self.das_client.post_event_type(event_type)
        except Exception as e:
            logger.exception(f'Exception raised posting event type', extra=dict(event_type=event_type))
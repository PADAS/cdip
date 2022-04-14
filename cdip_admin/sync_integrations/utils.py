from integrations.models import OutboundIntegrationConfiguration, InboundIntegrationConfiguration
from sync_integrations.er_smart_sync import ER_SMART_Synchronizer
import logging

logger = logging.getLogger(__name__)


def run_er_smart_sync_integrations():
    # TODO: Better way to associate in portal which integrations should be synced
    smart_integrations = OutboundIntegrationConfiguration.objects.filter(enabled=True, type__slug="smart_connect")
    for smart_integration in smart_integrations:
        smart_integration_id = str(smart_integration.id)
        er_integration_id = smart_integration.additional.get('er_integration_id') if smart_integration.additional else None
        if er_integration_id:
            # confirm er_integration exists
            try:
                er_integration = InboundIntegrationConfiguration.objects.get(id=er_integration_id)
            except InboundIntegrationConfiguration.DoesNotExist:
                logger.error(f'Earth Ranger Inbound Integration specified was not found: {er_integration_id}')
                er_integration = None
            if not er_integration:
                er_integration_id = None
        if smart_integration_id and er_integration_id:
            logger.info(f"Beginning SMART ER sync process", extra=dict(smart_integration_id=smart_integration_id,
                                                                       smart_integration_name=smart_integration.name,
                                                                       er_integration_id=er_integration_id,
                                                                       er_integration_name=er_integration.name))
            er_smart_sync = ER_SMART_Synchronizer(smart_integration_id=smart_integration_id,
                                                  er_integration_id=er_integration_id)
            caslist = er_smart_sync.smart_client.get_conservation_areas()

            # Handle Group of CA's associated to single ER site
            for smart_ca_uuid in er_smart_sync.smart_ca_uuids:
                logger.debug(f'Processing SMART CA: {smart_ca_uuid}')
                ca_match = next((ca for ca in caslist if str(ca.uuid) == smart_ca_uuid), None)
                if not ca_match:
                    logger.warning(f'Conservation Area not found', extra=dict(smart_ca_uuid=smart_ca_uuid))
                    return
                logger.debug(f'Beginning sync of event types: {smart_ca_uuid}')
                er_smart_sync.push_smart_ca_data_model_to_er_event_types(smart_ca_uuid=smart_ca_uuid, ca=ca_match)
                er_smart_sync.sync_patrol_datamodel(smart_ca_uuid=smart_ca_uuid)

            # TODO: create non-directional int so we dont have both inbound and outbound int representing same system
            if er_integration:
                logger.debug(f'Beginning pull of ER objects')
                er_smart_sync.get_er_events(config=er_integration)
                er_smart_sync.get_er_patrols(config=er_integration)

        else:
            logger.warning(f"skipping sync, er_integration_id not found for smart_integration {smart_integration.id}")
            continue


if __name__ == '__main__':
    run_er_smart_sync_integrations()

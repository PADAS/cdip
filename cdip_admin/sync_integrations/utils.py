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
                er_integration = OutboundIntegrationConfiguration.objects.get(id=er_integration_id)
            except OutboundIntegrationConfiguration.DoesNotExist:
                logger.error(f'er_integration_id specified was not found: {er_integration_id}')
                er_integration = None
            if not er_integration:
                er_integration_id = None
        if smart_integration_id and er_integration_id:
            er_smart_sync = ER_SMART_Synchronizer(smart_integration_id=smart_integration_id,
                                                  er_integration_id=er_integration_id)
            er_smart_sync.push_smart_ca_data_model_to_er_event_types()
            er_smart_sync.sync_patrol_datamodel()
            # TODO: create non-directional int so we dont have both inbound and outbound int representing same system
            er_inbound_integration = InboundIntegrationConfiguration.objects.get(endpoint=er_integration.endpoint,
                                                                                 enabled=True)
            if er_inbound_integration:
                er_smart_sync.get_er_events(config=er_inbound_integration)
                er_smart_sync.get_er_patrols(config=er_inbound_integration)

        else:
            logger.warning(f"skipping sync, er_integration_id not found for smart_integration {smart_integration.id}")
            continue


if __name__ == '__main__':
    run_er_smart_sync_integrations()

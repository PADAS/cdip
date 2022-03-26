from integrations.models import OutboundIntegrationConfiguration
from sync_integrations.er_smart_sync import ERSMART_Synchronizer
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
            er_integration = OutboundIntegrationConfiguration.objects.get(id=er_integration_id)
            if not er_integration:
                er_integration_id = None
        if smart_integration_id and er_integration_id:
            er_smart_sync = ERSMART_Synchronizer(smart_integration_id=smart_integration_id,
                                                 er_integration_id=er_integration_id)
            er_smart_sync.push_smart_ca_data_model_to_er_event_types()
        else:
            logger.warning(f"skipping sync, er_integration_id not found for smart_integration {smart_integration.id}")
            continue


if __name__ == '__main__':
    run_er_smart_sync_integrations()
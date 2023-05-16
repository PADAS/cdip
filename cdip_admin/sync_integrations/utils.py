import uuid

import smartconnect
from smartconnect import SmartClient
from smartconnect.models import (
    ConservationArea,
)
from cdip_admin import settings

from integrations.models import (
    OutboundIntegrationConfiguration,
    InboundIntegrationConfiguration,
)
from sync_integrations.er_smart_sync import ER_SMART_Synchronizer
import logging
import json

logger = logging.getLogger(__name__)


def run_er_smart_sync_integrations():
    # TODO: Better way to associate in portal which integrations should be synced
    smart_integrations = OutboundIntegrationConfiguration.objects.filter(
        enabled=True, type__slug="smart_connect"
    )
    for smart_integration in smart_integrations:
        smart_integration_id = str(smart_integration.id)
        er_integration_id = (
            smart_integration.additional.get("er_integration_id")
            if smart_integration.additional
            else None
        )
        if er_integration_id:
            # confirm er_integration exists
            try:
                er_integration = InboundIntegrationConfiguration.objects.get(
                    id=er_integration_id
                )
            except InboundIntegrationConfiguration.DoesNotExist:
                logger.error(
                    f"Earth Ranger Inbound Integration specified was not found: {er_integration_id}"
                )
                er_integration = None
            if not er_integration:
                er_integration_id = None
        if smart_integration_id and er_integration_id:
            logger.info(
                f"Beginning SMART ER sync process",
                extra=dict(
                    smart_integration_id=smart_integration_id,
                    smart_integration_name=smart_integration.name,
                    er_integration_id=er_integration_id,
                    er_integration_name=er_integration.name,
                ),
            )
            er_smart_sync = ER_SMART_Synchronizer(
                smart_integration_id=smart_integration_id,
                er_integration_id=er_integration_id,
            )

            if not er_smart_sync.smart_ca_uuids:
                logger.warning(
                    f"ca_uuids not found in integration configuration",
                    extra=dict(smart_integration_id=smart_integration_id),
                )
                continue

            # Handle Group of CA's associated to single ER site
            for smart_ca_uuid in er_smart_sync.smart_ca_uuids:
                try:
                    extra_dict = dict(
                        smart_ca_uuid=smart_ca_uuid,
                        smart_server=er_smart_sync.smart_client.api,
                        use_smart_cache=settings.USE_SMART_CACHE,
                    )
                    logger.debug(f"Processing SMART CA: {smart_ca_uuid}")
                    ca = er_smart_sync.smart_client.get_conservation_area(
                        ca_uuid=smart_ca_uuid, use_cache=settings.USE_SMART_CACHE
                    )
                    if not ca:
                        logger.warning(
                            f"Conservation Area not found",
                            extra=dict(smart_ca_uuid=smart_ca_uuid),
                        )
                        return
                    logger.debug(
                        f"Beginning sync of event types",
                        extra=dict(ca_uuid=smart_ca_uuid),
                    )
                    er_smart_sync.push_smart_ca_data_model_to_er_event_types(
                        smart_ca_uuid=smart_ca_uuid, ca=ca
                    )
                    er_smart_sync.sync_patrol_datamodel(
                        smart_ca_uuid=smart_ca_uuid, ca=ca
                    )
                except Exception as e:
                    logger.exception(
                        f"Error occurred while attempting to process SMART data",
                        extra=extra_dict,
                    )

            # TODO: create non-directional int so we dont have both inbound and outbound int representing same system
            if er_integration:
                logger.debug(f"Beginning pull of ER objects")
                er_smart_sync.get_er_events(config=er_integration)
                er_smart_sync.get_er_patrols(config=er_integration)

        else:
            logger.warning(
                f"skipping sync, er_integration_id not found for smart_integration {smart_integration.id}"
            )
            continue


def on_smart_integration_save(*, integration_id: str):
    config = OutboundIntegrationConfiguration.objects.get(id=integration_id)

    if not config.state.get('download_data_models', False):
        return

    version = config.additional.get("version", "7.0")
    use_language_code = config.additional.get("use_language_code", "en")

    smart_client = SmartClient(
        api=config.endpoint,
        username=config.login,
        password=config.password,
        use_language_code=use_language_code,
        version=version,
    )
    ca_uuids = config.additional.get("ca_uuids")
    configurable_models_lists = {}
    for ca_uuid in ca_uuids:
        try:
            smart_client.get_data_model(ca_uuid=ca_uuid)
            smart_client.get_conservation_area(ca_uuid=ca_uuid)
            cm_values = smart_client.get_configurable_datamodels(ca_uuid=ca_uuid)

            print(json.dumps(cm_values, indent=2))

            configurable_models_lists[ca_uuid] = cm_values

            for cm in cm_values:
                logger.info('Downloading configurable model %s (%s)', cm['name'], cm['uuid'])
                smart_client.get_configurable_data_model(cm_uuid=cm['uuid'])
        except Exception as e:
            logger.exception(e, extra=dict(ca_uuid=ca_uuid))

    config.additional['configurable_models_lists'] = configurable_models_lists
    config.state['download_data_models'] = False
    config.save()

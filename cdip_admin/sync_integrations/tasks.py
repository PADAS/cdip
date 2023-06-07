import logging

from celery_once import QueueOnce

from cdip_admin import celery
from integrations.models import OutboundIntegrationConfiguration, InboundIntegrationConfiguration,\
    InboundIntegrationType, OutboundIntegrationType, Device

from sync_integrations.er_smart_sync import ER_SMART_Synchronizer
from sync_integrations.utils import (
    maintain_smart_integration,
)

logger = logging.getLogger(__name__)

@celery.app.task(base=QueueOnce, once={"graceful": True})
def synchronize_smart_datamodels(integration_id:str):

    smart_config = OutboundIntegrationConfiguration.objects.get(id=integration_id)
    logger.info('Synchronizing SMART datamodels for %s (%s)', smart_config.name, smart_config.id)

    datamodel_synchronizer = ER_SMART_Synchronizer(smart_config=smart_config)
    datamodel_synchronizer.synchronize_datamodel()
    logger.info('Finished synchronizing SMART datamodels for %s (%s)', smart_config.name, smart_config.id)


@celery.app.task(base=QueueOnce, once={"graceful": True})
def synchronize_smart_datamodels_all():

    for oic in OutboundIntegrationConfiguration.objects.filter(type__slug='smart_connect', enabled=True):
        synchronize_smart_datamodels.delay(str(oic.id))


@celery.app.task(base=QueueOnce, once={"graceful": True})
def run_sync_integrations():
    run_er_smart_sync_integrations()


@celery.app.task(base=QueueOnce, once={"graceful": True})
def handle_outboundintegration_save(integration_id):

    try:
        oic = OutboundIntegrationConfiguration.objects.get(id=integration_id)
    except OutboundIntegrationConfiguration.DoesNotExist:
        logger.error(f'OutboundIntegrationConfiguration(%s) does not exist.', integration_id)
    else:

        if oic.type.slug == 'smart_connect':
            maintain_smart_integration(integration_id=integration_id)




@celery.app.task(base=QueueOnce, once={"graceful": True})
def run_er_smart_sync_integrations():
    # TODO: Better way to associate in portal which integrations should be synced
    smart_integrations = OutboundIntegrationConfiguration.objects.filter(
        enabled=True, type__slug="smart_connect"
    )
    for i in smart_integrations:
        run_er_smart_sync_integration(smart_integration_id=str(i.id))

@celery.app.task
def maintain_smart_integrations():
    smart_integrations = OutboundIntegrationConfiguration.objects.filter(
        enabled=True, type__slug="smart_connect"
    )
    for i in smart_integrations:
        _maintain_smart_integration.delay(integration_id=str(i.id))


@celery.app.task(base=QueueOnce, once={"graceful": True})
def _maintain_smart_integration(integration_id:str):
    maintain_smart_integration(integration_id=integration_id, force=True)


@celery.app.task(base=QueueOnce, once={"graceful": True})
def run_er_smart_sync_integration(*args, smart_integration_id=None):

    assert not args, "Only keyword arguments are allowed"

    try:
        smart_integration = OutboundIntegrationConfiguration.objects.get(
            id=smart_integration_id,
            enabled=True,
            type__slug=OutboundIntegrationType.SMARTCONNECT)
    except OutboundIntegrationConfiguration.DoesNotExist:
        logger.error(f"SMART integration configuration does not exist for id: {smart_integration_id}")
        return

    device_groups = smart_integration.devicegroups.all()
    devices = Device.objects.filter(devicegroup__in=device_groups,
                                    inbound_configuration__type__slug=InboundIntegrationType.EARTHRANGER
                                    ).order_by('inbound_configuration_id').distinct('inbound_configuration_id')

    for device in devices:

        er_configuration = device.inbound_configuration

        try:
            er_smart_sync = ER_SMART_Synchronizer(smart_config=smart_integration, er_config=er_configuration)

            logger.info("Synchronizing Data Models for %s (%s) to %s (%s)",
                         smart_integration.name, smart_integration.id,
                         er_configuration.name, er_configuration.id)

            er_smart_sync.synchronize_datamodel()
            er_smart_sync.sync_patrol_datamodel()

            logger.info("Synchronizing EarthRanger events and patrols for %s (%s) to %s (%s)",
                         smart_integration.name, smart_integration.id,
                         er_configuration.name, er_configuration.id)

            er_smart_sync.get_er_events(config=er_configuration)
            er_smart_sync.get_er_patrols(config=er_configuration)

        except Exception as e:
            logger.exception('Failed synchronizing data models for %s (%s) to %s (%s)',
                             smart_integration.name, smart_integration.id,
                             er_configuration.name, er_configuration.id)


import logging
import time
from functools import wraps

from django.db.models import Q
from celery_once import QueueOnce
from celery import shared_task, chain, group
from celery.exceptions import SoftTimeLimitExceeded

from integrations.models import OutboundIntegrationConfiguration, InboundIntegrationConfiguration,\
    InboundIntegrationType, OutboundIntegrationType, Device

from sync_integrations.er_smart_sync import ER_SMART_Synchronizer
from sync_integrations.utils import (
    maintain_smart_integration,
)

logger = logging.getLogger(__name__)


def handle_timeout_exceptions(func):
    """Decorator to catch and log SoftTimeLimitExceeded exceptions with task duration."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            return func(*args, **kwargs)
        except SoftTimeLimitExceeded as e:
            duration = time.time() - start_time
            logger.error(
                f"Task {func.__name__} timed out after {duration:.2f} seconds",
                extra={
                    'task_name': func.__name__,
                    'duration_seconds': duration,
                    'args': args,
                    'kwargs': kwargs,
                    'exception_type': 'SoftTimeLimitExceeded',
                    'exception_message': str(e)
                }
            )
            raise  # Re-raise the exception so Celery can handle it properly
        except Exception as e:
            duration = time.time() - start_time
            logger.exception(
                f"Task {func.__name__} failed after {duration:.2f} seconds",
                extra={
                    'task_name': func.__name__,
                    'duration_seconds': duration,
                    'args': args,
                    'kwargs': kwargs,
                    'exception_type': type(e).__name__,
                    'exception_message': str(e)
                }
            )
            raise
    return wrapper

@shared_task(base=QueueOnce, once={"graceful": True})
@handle_timeout_exceptions
def synchronize_smart_datamodels(integration_id:str):

    smart_config = OutboundIntegrationConfiguration.objects.get(id=integration_id)
    logger.info('Synchronizing SMART datamodels for %s (%s)', smart_config.name, smart_config.id)

    datamodel_synchronizer = ER_SMART_Synchronizer(smart_config=smart_config)
    datamodel_synchronizer.synchronize_datamodel()
    logger.info('Finished synchronizing SMART datamodels for %s (%s)', smart_config.name, smart_config.id)


@shared_task(base=QueueOnce, once={"graceful": True})
@handle_timeout_exceptions
def synchronize_smart_datamodels_all():

    for oic in OutboundIntegrationConfiguration.objects.filter(type__slug='smart_connect', enabled=True):
        synchronize_smart_datamodels.delay(str(oic.id))


@shared_task(base=QueueOnce, once={"graceful": True})
@handle_timeout_exceptions
def run_sync_integrations():
    run_er_smart_sync_integrations()


@shared_task(base=QueueOnce, once={"graceful": True})
@handle_timeout_exceptions
def handle_outboundintegration_save(integration_id):

    try:
        oic = OutboundIntegrationConfiguration.objects.get(id=integration_id)
    except OutboundIntegrationConfiguration.DoesNotExist:
        logger.error(f'OutboundIntegrationConfiguration(%s) does not exist.', integration_id)
    else:

        if oic.type.slug == 'smart_connect':
            maintain_smart_integration(integration_id=integration_id)




@shared_task(base=QueueOnce, once={"graceful": True})
@handle_timeout_exceptions
def run_er_smart_sync_integrations():
    # TODO: Better way to associate in portal which integrations should be synced
    smart_integrations = OutboundIntegrationConfiguration.objects.filter(
        enabled=True, type__slug="smart_connect"
    )
    for i in smart_integrations:
        run_er_smart_sync_integration.delay(smart_integration_id=str(i.id))

@shared_task
@handle_timeout_exceptions
def maintain_smart_integrations():
    smart_integrations = OutboundIntegrationConfiguration.objects.filter(
        enabled=True, type__slug="smart_connect"
    )
    for i in smart_integrations:
        _maintain_smart_integration.delay(integration_id=str(i.id))


@shared_task(base=QueueOnce, once={"graceful": True})
@handle_timeout_exceptions
def _maintain_smart_integration(integration_id:str):
    maintain_smart_integration(integration_id=integration_id, force=True)


@shared_task(base=QueueOnce, once={"graceful": True}, soft_time_limit=1800)
@handle_timeout_exceptions
def sync_er_smart_datamodels(*, smart_integration_id=None, er_integration_id=None):
    """Synchronize SMART data models and patrol data models to EarthRanger."""
    try:
        smart_integration = OutboundIntegrationConfiguration.objects.get(
            id=smart_integration_id,
            enabled=True,
            type__slug=OutboundIntegrationType.SMARTCONNECT)
        er_configuration = InboundIntegrationConfiguration.objects.get(
            id=er_integration_id,
            enabled=True,
            type__slug=InboundIntegrationType.EARTHRANGER)
    except (OutboundIntegrationConfiguration.DoesNotExist, InboundIntegrationConfiguration.DoesNotExist) as e:
        logger.error(f"Integration configuration does not exist: {e}")
        return

    try:
        er_smart_sync = ER_SMART_Synchronizer(smart_config=smart_integration, er_config=er_configuration)

        logger.info("Synchronizing Data Models for %s (%s) to %s (%s)",
                     smart_integration.name, smart_integration.id,
                     er_configuration.name, er_configuration.id)

        er_smart_sync.synchronize_datamodel()
        er_smart_sync.sync_patrol_datamodel()

        logger.info("Finished synchronizing Data Models for %s (%s) to %s (%s)",
                     smart_integration.name, smart_integration.id,
                     er_configuration.name, er_configuration.id)

    except Exception as e:
        logger.exception('Failed synchronizing data models for %s (%s) to %s (%s)',
                         smart_integration.name, smart_integration.id,
                         er_configuration.name, er_configuration.id)


@shared_task(base=QueueOnce, once={"graceful": True}, soft_time_limit=1800)
@handle_timeout_exceptions
def sync_er_events(*, smart_integration_id=None, er_integration_id=None):
    """Synchronize EarthRanger events to SMART."""
    try:
        smart_integration = OutboundIntegrationConfiguration.objects.get(
            id=smart_integration_id,
            enabled=True,
            type__slug=OutboundIntegrationType.SMARTCONNECT)
        er_configuration = InboundIntegrationConfiguration.objects.get(
            id=er_integration_id,
            enabled=True,
            type__slug=InboundIntegrationType.EARTHRANGER)
    except (OutboundIntegrationConfiguration.DoesNotExist, InboundIntegrationConfiguration.DoesNotExist) as e:
        logger.error(f"Integration configuration does not exist: {e}")
        return

    try:
        er_smart_sync = ER_SMART_Synchronizer(smart_config=smart_integration, er_config=er_configuration)

        logger.info("Synchronizing EarthRanger events for %s (%s) to %s (%s)",
                     smart_integration.name, smart_integration.id,
                     er_configuration.name, er_configuration.id)

        er_smart_sync.sychronize_er_events_to_smartconnect(config=er_configuration)

        logger.info("Finished synchronizing EarthRanger events for %s (%s) to %s (%s)",
                     smart_integration.name, smart_integration.id,
                     er_configuration.name, er_configuration.id)

    except Exception as e:
        logger.exception('Failed synchronizing events for %s (%s) to %s (%s)',
                         smart_integration.name, smart_integration.id,
                         er_configuration.name, er_configuration.id)


@shared_task(base=QueueOnce, once={"graceful": True}, soft_time_limit=1800)
@handle_timeout_exceptions
def sync_er_patrols(*, smart_integration_id=None, er_integration_id=None):
    """Synchronize EarthRanger patrols to SMART."""
    try:
        smart_integration = OutboundIntegrationConfiguration.objects.get(
            id=smart_integration_id,
            enabled=True,
            type__slug=OutboundIntegrationType.SMARTCONNECT)
        er_configuration = InboundIntegrationConfiguration.objects.get(
            id=er_integration_id,
            enabled=True,
            type__slug=InboundIntegrationType.EARTHRANGER)
    except (OutboundIntegrationConfiguration.DoesNotExist, InboundIntegrationConfiguration.DoesNotExist) as e:
        logger.error(f"Integration configuration does not exist: {e}")
        return

    try:
        er_smart_sync = ER_SMART_Synchronizer(smart_config=smart_integration, er_config=er_configuration)

        logger.info("Synchronizing EarthRanger patrols for %s (%s) to %s (%s)",
                     smart_integration.name, smart_integration.id,
                     er_configuration.name, er_configuration.id)

        er_smart_sync.synchronize_er_patrols_to_smart_connect(config=er_configuration)

        logger.info("Finished synchronizing EarthRanger patrols for %s (%s) to %s (%s)",
                     smart_integration.name, smart_integration.id,
                     er_configuration.name, er_configuration.id)

    except Exception as e:
        logger.exception('Failed synchronizing patrols for %s (%s) to %s (%s)',
                         smart_integration.name, smart_integration.id,
                         er_configuration.name, er_configuration.id)


@shared_task(base=QueueOnce, once={"graceful": True})
@handle_timeout_exceptions
def run_er_smart_sync_integration(*, smart_integration_id=None):
    """Orchestrate the full ER-SMART synchronization process using task chains."""
    try:
        smart_integration = OutboundIntegrationConfiguration.objects.get(
            id=smart_integration_id,
            enabled=True,
            type__slug=OutboundIntegrationType.SMARTCONNECT)
    except OutboundIntegrationConfiguration.DoesNotExist:
        logger.error(f"SMART integration configuration does not exist for id: {smart_integration_id}")
        return

    logger.info(f"Starting ER smart sync integration for {smart_integration.name} ({smart_integration.id}) with endpoint {smart_integration.endpoint}")

    device_groups = smart_integration.devicegroups.all()

    # Get all devices that are in the device groups and have an EarthRanger inbound integration
    devices = Device.objects.filter(devicegroup__in=device_groups,
                                    inbound_configuration__type__slug=InboundIntegrationType.EARTHRANGER).order_by(
        'inbound_configuration_id').distinct('inbound_configuration_id').values('inbound_configuration_id')

    idlist = [dev.get('inbound_configuration_id') for dev in devices]

    # Also include any Inbound Configuration that is associated by its default device group.
    er_integrations = InboundIntegrationConfiguration.objects.filter(
        enabled=True,
        type__slug=InboundIntegrationType.EARTHRANGER).filter(
        Q(default_devicegroup__in=device_groups) | Q(id__in=idlist)
    )

    # Create task chains for each ER integration
    for er_configuration in er_integrations:
        logger.info("Creating sync chain for %s (%s) to %s (%s)",
                     smart_integration.name, smart_integration.id,
                     er_configuration.name, er_configuration.id)

        # Chain the tasks: datamodels -> events -> patrols in the background
        task_chain = chain(
            sync_er_smart_datamodels.si(
                smart_integration_id=str(smart_integration.id),
                er_integration_id=str(er_configuration.id)
            ),
            sync_er_events.si(
                smart_integration_id=str(smart_integration.id),
                er_integration_id=str(er_configuration.id)
            ),
            sync_er_patrols.si(
                smart_integration_id=str(smart_integration.id),
                er_integration_id=str(er_configuration.id)
            )
        )
        
        # Execute the chain in the background
        task_chain.apply_async()

    logger.info(f"Finished creating sync chains for {smart_integration.name} ({smart_integration.id})")


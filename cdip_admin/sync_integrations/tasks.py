import logging
import time
from functools import wraps

from django.core.exceptions import ValidationError
from django.db.models import Q
from celery_once import QueueOnce
from celery import shared_task, chain, group
from celery.exceptions import SoftTimeLimitExceeded

from integrations.models import OutboundIntegrationConfiguration, InboundIntegrationConfiguration,\
    InboundIntegrationType, OutboundIntegrationType, Device

from sync_integrations.er_smart_sync import build_synchronizer
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
def synchronize_smart_datamodels(integration_id: str):
    smart_config = OutboundIntegrationConfiguration.objects.get(id=integration_id)
    logger.info('Synchronizing SMART datamodels for %s (%s)', smart_config.name, smart_config.id)

    er_integration_id = (smart_config.additional or {}).get("er_integration_id")
    try:
        er_config = InboundIntegrationConfiguration.objects.get(id=er_integration_id)
    except (InboundIntegrationConfiguration.DoesNotExist, ValidationError, ValueError):
        logger.error(
            "SMART integration %s (%s) has no valid additional.er_integration_id (%r); skipping",
            smart_config.name, smart_config.id, er_integration_id,
        )
        return

    build_synchronizer(smart_config=smart_config, er_config=er_config).synchronize_datamodel()
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


# Hard limit on the three sync tasks: the library's retries swallow
# SoftTimeLimitExceeded; it checkpoints per event and the datamodel push is
# idempotent, so a hard kill is safe.
@shared_task(
    base=QueueOnce, once={"graceful": True}, soft_time_limit=1800, time_limit=2100
)
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
        er_smart_sync = build_synchronizer(smart_config=smart_integration, er_config=er_configuration)

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


@shared_task(
    base=QueueOnce, once={"graceful": True}, soft_time_limit=1800, time_limit=2100
)
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
        er_smart_sync = build_synchronizer(smart_config=smart_integration, er_config=er_configuration)

        logger.info("Synchronizing EarthRanger events for %s (%s) to %s (%s)",
                     smart_integration.name, smart_integration.id,
                     er_configuration.name, er_configuration.id)

        er_smart_sync.synchronize_er_events()

        logger.info("Finished synchronizing EarthRanger events for %s (%s) to %s (%s)",
                     smart_integration.name, smart_integration.id,
                     er_configuration.name, er_configuration.id)

    except Exception as e:
        logger.exception('Failed synchronizing events for %s (%s) to %s (%s)',
                         smart_integration.name, smart_integration.id,
                         er_configuration.name, er_configuration.id)


@shared_task(
    base=QueueOnce, once={"graceful": True}, soft_time_limit=1800, time_limit=2100
)
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
        er_smart_sync = build_synchronizer(smart_config=smart_integration, er_config=er_configuration)

        logger.info("Synchronizing EarthRanger patrols for %s (%s) to %s (%s)",
                     smart_integration.name, smart_integration.id,
                     er_configuration.name, er_configuration.id)

        er_smart_sync.synchronize_er_patrols()

        logger.info("Finished synchronizing EarthRanger patrols for %s (%s) to %s (%s)",
                     smart_integration.name, smart_integration.id,
                     er_configuration.name, er_configuration.id)

    except Exception as e:
        logger.exception('Failed synchronizing patrols for %s (%s) to %s (%s)',
                         smart_integration.name, smart_integration.id,
                         er_configuration.name, er_configuration.id)


# Set `"er_smart_sync_paused": true` in a SMART integration's `additional` to
# keep it out of the ER <-> SMART sync without disabling the integration
# itself (which would also stop routing). Used to hold back a site whose v1
# event types ER cannot migrate yet.
ER_SMART_SYNC_PAUSED = "er_smart_sync_paused"


def er_smart_sync_paused(smart_integration) -> bool:
    return bool((smart_integration.additional or {}).get(ER_SMART_SYNC_PAUSED))


def er_integrations_for(smart_integration):
    """The enabled ER integrations a SMART integration syncs with.

    An ER integration qualifies when one of the SMART integration's device
    groups is its default device group, or holds one of its devices. The
    sync task and the preflight command share this so they cannot drift.
    """
    device_groups = smart_integration.devicegroups.all()
    devices = Device.objects.filter(
        devicegroup__in=device_groups,
        inbound_configuration__type__slug=InboundIntegrationType.EARTHRANGER,
    ).order_by('inbound_configuration_id').distinct('inbound_configuration_id').values('inbound_configuration_id')
    idlist = [dev.get('inbound_configuration_id') for dev in devices]
    return InboundIntegrationConfiguration.objects.filter(
        enabled=True,
        type__slug=InboundIntegrationType.EARTHRANGER,
    ).filter(Q(default_devicegroup__in=device_groups) | Q(id__in=idlist))

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

    if er_smart_sync_paused(smart_integration):
        logger.warning(
            "ER smart sync is paused for %s (%s): additional.%s is set; skipping",
            smart_integration.name, smart_integration.id, ER_SMART_SYNC_PAUSED,
        )
        return

    logger.info(f"Starting ER smart sync integration for {smart_integration.name} ({smart_integration.id}) with endpoint {smart_integration.endpoint}")

    # Create task chains for each ER integration
    for er_configuration in er_integrations_for(smart_integration):
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


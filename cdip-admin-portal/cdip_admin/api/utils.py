import logging
from django.core.exceptions import ObjectDoesNotExist

from integrations.models import Device, DeviceState

logger = logging.getLogger(__name__)


def update_device_information(config):
    logger.info('Update Device Information')
    for key in config.state:
        try:
            device = Device.objects.get(name=key, type_id=config.type__id)
        except ObjectDoesNotExist:
            logger.info('Device not found. Create a new one.')
            device = Device.objects.create(type_id=config.id, name=key, owner_id=config.owner__id,
                                           outbound_configuration=config.defaultConfiguration)

        logger.info('Update the state of the device stream.')
        DeviceState.objects.create(device_id=device.name, end_state=config.state[key])

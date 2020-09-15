import logging
from django.core.exceptions import ObjectDoesNotExist

from integrations.models import Device, DeviceState

logger = logging.getLogger(__name__)


def update_device_information(config):
    logger.info('Update Device Information')
    for key in config.state:
        device, created = Device.objects.get_or_create(external_id=key, inbound_configuration=config)

        # TODO: add outbound configurations to the device in some way
        for item in config.defaultConfiguration.all():
            device.outbound_configuration.add(item)

        logger.info('Update the state of the device stream.')
        DeviceState.objects.create(device_id=device.id, end_state=config.state[key])

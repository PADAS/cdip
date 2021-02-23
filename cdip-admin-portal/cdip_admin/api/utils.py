import logging

from integrations.models import Device, DeviceState, InboundIntegrationConfiguration, DeviceGroup

logger = logging.getLogger(__name__)


def update_device_information(state, config):
    logger.info('Update Device Information')
    for key in state:
        device, created = Device.objects.get_or_create(external_id=key, inbound_configuration=config)

        # # TODO: add outbound configurations to the device in some way
        # for item in config.defaultConfiguration.all():
        #     device.outbound_configuration.add(item)

        logger.info('Update the state of the device stream if it has changed.')
        DeviceState.objects.get_or_create(device_id=device.id, end_state=state[key])


def post_device_information(state, config):
    logger.info('Post Device Information')

    name = config.type.name + " - Default"
    device_group, created = DeviceGroup.objects.get_or_create(inbound_configuration=config,
                                                              defaults=dict(owner_id=config.owner.id, name=name))

    for key in state:
        device, created = Device.objects.get_or_create(external_id=key, inbound_configuration_id=config.id)

        for item in config.defaultConfiguration.all():
            device.outbound_configuration.add(item)

        if device not in device_group.devices.all():
            device_group.devices.add(device)
            device_group.save()

        logger.info('Update the state of the device stream if it has changed.')
        DeviceState.objects.get_or_create(device_id=device.id, state=state[key])

    return device_group.devices.values('id', 'external_id', 'inbound_configuration_id')

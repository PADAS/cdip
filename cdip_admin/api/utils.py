import logging

from integrations.models import (
    Device,
    DeviceState,
    InboundIntegrationConfiguration,
    DeviceGroup,
)

logger = logging.getLogger(__name__)


def post_device_information(state: dict, config: InboundIntegrationConfiguration):
    logger.info("Post Device Information", extra={"integration_id": config.id})

    if config.default_devicegroup:
        device_group = config.default_devicegroup
    else:

        name = f"{config.name} - Default Group"
        device_group = DeviceGroup.objects.create(owner_id=config.owner.id, name=name)
        config.default_devicegroup = device_group
        config.save()

    for key in state:
        device, created = Device.objects.get_or_create(
            external_id=key, inbound_configuration_id=config.id
        )

        if device not in device_group.devices.all():
            device_group.devices.add(device)
            device_group.save()

        logger.debug("Update the state of the device stream if it has changed.")
        DeviceState.objects.get_or_create(device_id=device.id, state=state[key])

    return device_group.devices.values("id", "external_id", "inbound_configuration_id")

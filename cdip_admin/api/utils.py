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

    for key, val in state.items():
        device, created = Device.objects.get_or_create(
            external_id=key, inbound_configuration_id=config.id
        )

        if device not in device_group.devices.all():
            device_group.devices.add(device)
            device_group.save()

        # This construct is here while we don't have unique index on {device_id}.
        for _ in range(2):
            try:
                ds, created = DeviceState.objects.update_or_create(device_id=device.id, defaults=dict(state=val))
                break
            except DeviceState.MultipleObjectsReturned:
                DeviceState.objects.filter(device_id= device.id).delete()


    return device_group.devices.values("id", "external_id", "inbound_configuration_id")

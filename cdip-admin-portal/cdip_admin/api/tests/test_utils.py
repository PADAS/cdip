import pytest

from api.utils import post_device_information
from integrations.models import Device, DeviceState, InboundIntegrationConfiguration, InboundIntegrationType, \
    OutboundIntegrationConfiguration, OutboundIntegrationType, DeviceGroup

from organizations.models import Organization


def test_post_device_information(device_group):
    # Update a Bunch of devices
    inbound_config = InboundIntegrationConfiguration.objects.first()
    assert inbound_config is not None
    post_device_information(inbound_config.state, inbound_config)
    count = Device.objects.count()

    # Assert the count is correct
    assert count == 10

    # Assert some of the cursor values in the DeviceState Table
    device_1 = Device.objects.get(external_id='ST2010-2758')
    device_state_1 = DeviceState.objects.get(device__id=device_1.id)
    assert device_state_1.state == 14469583

    device_2 = Device.objects.get(external_id='ST2010-2762')
    device_state_2 = DeviceState.objects.get(device__id=device_2.id)
    assert device_state_2.state == 14488454

    # Update the cursor info to add a few more devices and update a couple of the cursors
    state = dict({
        "ST2010-2758": 14469900,
        "ST2010-2759": 14430249,
        "ST2010-2760": 14650428,
        "ST2010-2761": 14722788,
        "ST2010-2762": 14488750,
        "ST2010-2763": 14454926,
        "ST2010-2764": 14699313,
        "ST2010-2765": 14428313,
        "ST2010-2766": 14383613,
        "ST2010-2767": 14174427,
        "ST2010-2768": 14031055,
        "ST2010-2769": 14210284,
        "ST2010-2770": 17351262,
        "ST2010-2771": 17560037,
        "ST2010-2772": 17638614
    })

    inbound_config.state = state

    post_device_information(state, inbound_config)
    count = Device.objects.count()
    # Assert the count is correct
    assert count == 15

    # Assert that work check the count and values of a couple devices
    device_1 = Device.objects.get(external_id='ST2010-2758')
    device_state_1 = DeviceState.objects.filter(device__id=device_1.id).order_by('-created_at').first()
    assert device_state_1.state == 14469900

    device_2 = Device.objects.get(external_id='ST2010-2762')
    device_state_2 = DeviceState.objects.filter(device__id=device_2.id).order_by('-created_at').first()
    assert device_state_2.state == 14488750

    device_3 = Device.objects.get(external_id='ST2010-2760')
    device_state_3 = DeviceState.objects.filter(device__id=device_3.id).order_by('-created_at').first()
    assert device_state_3.state == 14650428

    device_4 = Device.objects.get(external_id='ST2010-2772')
    device_state_4 = DeviceState.objects.filter(device__id=device_4.id).order_by('-created_at').first()
    assert device_state_4.state == 17638614

    outbound_config = DeviceGroup.objects.get(devices=device_4).destinations.first()
    assert outbound_config is not None
    outbound_type = outbound_config.type
    assert outbound_type is not None
    assert outbound_type.name == "EarthRanger"


@pytest.fixture
def device_group(db, django_user_model):
    # This where to setup the initial data
    organization = Organization.objects.create(name="WPS", description="An Organization for testing.")

    outbound_type = OutboundIntegrationType.objects.create(name="EarthRanger", description="ER")

    outbound_config = OutboundIntegrationConfiguration.objects.create(type_id=outbound_type.id, owner_id=organization.id)

    inbound_type = InboundIntegrationType.objects.create(name="Savannah Tracker")

    name = inbound_type.name + " - Default Group"

    device_group = DeviceGroup.objects.create(owner_id=outbound_config.owner.id, name=name)
    device_group.destinations.add(outbound_config)


    state = dict({
        "ST2010-2758": 14469583,
        "ST2010-2759": 14430249,
        "ST2010-2760": 14650428,
        "ST2010-2761": 14722788,
        "ST2010-2762": 14488454,
        "ST2010-2763": 14454926,
        "ST2010-2764": 14699313,
        "ST2010-2765": 14428313,
        "ST2010-2766": 14383613,
        "ST2010-2767": 14174427
    })

    inbound_config = InboundIntegrationConfiguration.objects.create(type_id=inbound_type.id, owner_id=organization.id,
                                                                    state=state, default_devicegroup=device_group)

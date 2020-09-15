from django.test import TestCase

from api.utils import update_device_information
from integrations.models import Device, DeviceState, InboundIntegrationConfiguration, InboundIntegrationType, \
    OutboundIntegrationConfiguration, OutboundIntegrationType

from organizations.models import Organization


class TestUpdateDeviceInformation(TestCase):
    @classmethod
    def setUpTestData(cls):
        # This where to setup the initial data
        organization = Organization.objects.create(name="WPS", description="An Organization for testing.")

        outbound_type = OutboundIntegrationType.objects.create(name="Earthranger", description="ER")

        outbound_config = OutboundIntegrationConfiguration.objects.create(type_id=outbound_type.id, owner_id=organization.id)

        default_config = [outbound_config]

        inbound_type = InboundIntegrationType.objects.create(name="Savannah Tracker")

        state = dict(cursors={
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
                                                                        defaultConfiguration=default_config, state=state)

    def test_update_device_information(self):
        # Update a Bunch of devices
        inbound_config = InboundIntegrationConfiguration.objects.get(id=1)
        update_device_information(inbound_config)
        count = Device.objects.count()
        # Assert the count is correct
        self.assertEquals(count, 10)

        # Assert some of the cursor values in the DeviceState Table
        device_1 = Device.objects.get(name='ST2010-2758')
        device_state_1 = DeviceState.objects.get(device__id=device_1.id)
        self.assertEquals(device_state_1.end_state, "14469583")

        # Update the cursor info to add a few more devices and update a couple of the cursors
        state = dict(cursors={
            "ST2010-2758": 14469583,
            "ST2010-2759": 14430249,
            "ST2010-2760": 14650428,
            "ST2010-2761": 14722788,
            "ST2010-2762": 14488454,
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

        update_device_information(inbound_config)
        count = Device.objects.count()
        # Assert the count is correct
        self.assertEquals(count, 15)

        # Assert that work check the count and values of a couple devices

        # state = dict(cursors={
        #     "ST2010-2758": 14469583,
        #     "ST2010-2759": 14430249,
        #     "ST2010-2760": 14650428,
        #     "ST2010-2761": 14722788,
        #     "ST2010-2762": 14488454,
        #     "ST2010-2763": 14454926,
        #     "ST2010-2764": 14699313,
        #     "ST2010-2765": 14428313,
        #     "ST2010-2766": 14383613,
        #     "ST2010-2767": 14174427,
        #     "ST2010-2768": 14031055,
        #     "ST2010-2769": 14210284,
        #     "ST2010-2770": 17351262,
        #     "ST2010-2771": 17560037,
        #     "ST2010-2772": 17638614,
        #     "ST2010-3042": 17744801,
        #     "ST2010-3043": 20746124,
        #     "ST2010-3044": 20864549,
        #     "ST2010-3045": 17826618,
        #     "ST2010-3046": 17726857,
        #     "ST2010-3047": 17748119,
        #     "ST2010-3048": 17763270,
        #     "ST2010-3049": 17755930,
        #     "ST2010-3050": 17767553,
        #     "ST2010-3051": 17752117,
        #     "ST2010-3052": 17767767,
        #     "ST2010-3053": 17762774,
        #     "ST2010-3054": 17744395,
        #     "ST2010-3055": 17793712,
        #     "ST2010-3056": 17750800,
        #     "ST2010-3057": 17738471,
        #     "IRI2016-3285": 31416290,
        #     "IRI2016-3313": 31446299,
        #     "IRI2016-3314": 31446394,
        #     "IRI2016-3315": "20075981",
        #     "IRI2016-3384": 31440883,
        #     "IRI2016-3385": "19399113",
        #     "IRI2016-3386": "19399111",
        #     "IRI2016-3387": "20041332"
        # })

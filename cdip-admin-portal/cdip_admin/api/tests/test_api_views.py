import uuid
from typing import NamedTuple, Any

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse

from core.enums import DjangoGroups

pytestmark = pytest.mark.django_db
from unittest.mock import patch

from integrations.models import InboundIntegrationType, DeviceGroup, \
    OutboundIntegrationConfiguration, OutboundIntegrationType, InboundIntegrationConfiguration, \
    Organization, Device


def test_get_integration_type_list(client, inbound_integration_user):

        iit = InboundIntegrationType.objects.create(
            name='Some integration type',
            slug='some-integration-type',
            description='Some integration type.'

        )

        client.force_login(inbound_integration_user.user)

        response = client.get(reverse("inboundintegrationtype_list"))

        assert response.status_code == 200

        response = response.json()

        assert str(iit.id) in [x['id'] for x in response]


def test_get_outbound_by_ibc(client, inbound_integration_user):

        org = Organization.objects.create(
            name = 'Some org.'
        )

        iit = InboundIntegrationType.objects.create(
            name='Some integration type',
            slug='some-integration-type',
            description='Some integration type.'

        )
        oit = OutboundIntegrationType.objects.create(
            name='Some destination type',
            slug='my-dest-slug',
            description='Some integration type.'

        )

        ii = InboundIntegrationConfiguration.objects.create(
            type = iit,
            name = 'some ii',
            owner = org
        )
        oi = OutboundIntegrationConfiguration.objects.create(
            type = oit,
            name = 'some oi',
            owner = org
        )

        other_oi = OutboundIntegrationConfiguration.objects.create(
            type = oit,
            name = 'some other oi',
            owner = org
        )

        devicegroup = DeviceGroup.objects.create(
            name='some device group',
            owner=org,
        )

        devicegroup.destinations.add(oi)

        device = Device.objects.create(
            external_id = 'some-ext-id',
            inbound_configuration = ii
        )

        devicegroup.devices.add(device)


        # Sanity check on the test data relationships.
        assert Device.objects.filter(inbound_configuration=ii).exists()
        assert DeviceGroup.objects.filter(devices__inbound_configuration=ii).exists()
        assert OutboundIntegrationConfiguration.objects.filter(devicegroup__devices__inbound_configuration=ii).exists()

        client.force_login(inbound_integration_user.user)

        # Get destinations by inbound-id.
        response = client.get(reverse("outboundintegrationconfiguration_list"),
                              data={'inbound_id': str(ii.id)})

        assert response.status_code == 200
        response = response.json()

        assert len(response) == 1
        assert str(oi.id) in [item['id'] for item in response]
        assert not str(other_oi.id) in [item['id'] for item in response]


class IntegrationUser(NamedTuple):
    user: Any = None
    user_info: str = ''


@pytest.fixture
def inbound_integration_user(db, django_user_model):
    password = django_user_model.objects.make_random_password()
    user_const = dict(last_name='Owen', first_name='Harry')

    user_id = str(uuid.uuid4())
    user = django_user_model.objects.create_superuser(
        user_id, 'harry.owen@vulcan.com', password,
        **user_const)
    group_name = DjangoGroups.GLOBAL_ADMIN.value
    group = Group(name=group_name)
    group.save()
    user.groups.add(group)

    iu = IntegrationUser(user_info={'sub': user_id},
                         user=user)

    return iu
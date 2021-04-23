import base64
import uuid
from typing import NamedTuple, Any

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse
from rest_framework.utils import json

from accounts.models import AccountProfileOrganization, AccountProfile
from clients.models import ClientProfile
from core.enums import DjangoGroups, RoleChoices

pytestmark = pytest.mark.django_db
from unittest.mock import patch

from integrations.models import InboundIntegrationType, DeviceGroup, \
    OutboundIntegrationConfiguration, OutboundIntegrationType, InboundIntegrationConfiguration, \
    Organization, Device


def test_get_integration_type_list(client, global_admin_user):

        iit = InboundIntegrationType.objects.create(
            name='Some integration type',
            slug='some-integration-type',
            description='Some integration type.'

        )

        client.force_login(global_admin_user.user)

        response = client.get(reverse("inboundintegrationtype_list"))

        assert response.status_code == 200

        response = response.json()

        assert str(iit.id) in [x['id'] for x in response]


def test_get_outbound_by_ibc(client, global_admin_user):

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

        client.force_login(global_admin_user.user)

        # Get destinations by inbound-id.
        response = client.get(reverse("outboundintegrationconfiguration_list"),
                              data={'inbound_id': str(ii.id)})

        assert response.status_code == 200
        response = response.json()

        assert len(response) == 1
        assert str(oi.id) in [item['id'] for item in response]
        assert not str(other_oi.id) in [item['id'] for item in response]


def test_get_organizations_list_organization_member_viewer(client, organization_member_user):
    org1 = Organization.objects.create(
        name='Some org1'
    )

    org2 = Organization.objects.create(
        name='Some org2'
    )

    ap = AccountProfile.objects.create(
        user_id=organization_member_user.user.username
    )

    apo = AccountProfileOrganization.objects.create(
        accountprofile=ap,
        organization=org1,
        role=RoleChoices.VIEWER
    )

    # Sanity check on the test data relationships.
    assert Organization.objects.filter(id=org1.id).exists()
    assert AccountProfile.objects.filter(user_id=organization_member_user.user.username).exists()
    assert AccountProfileOrganization.objects.filter(accountprofile=ap).exists()

    client.force_login(organization_member_user.user)

    # Get organizations list
    response = client.get(reverse("organization_list"))

    assert response.status_code == 200
    response = response.json()

    # should receive the organization user is viewer of
    assert len(response) == 1


def test_get_organizations_list_organization_member_admin(client, organization_member_user):
    org1 = Organization.objects.create(
        name='Some org1'
    )

    org2 = Organization.objects.create(
        name='Some org2'
    )

    ap = AccountProfile.objects.create(
        user_id=organization_member_user.user.username
    )

    apo = AccountProfileOrganization.objects.create(
        accountprofile=ap,
        organization=org1,
        role=RoleChoices.ADMIN
    )

    # Sanity check on the test data relationships.
    assert Organization.objects.filter(id=org1.id).exists()
    assert AccountProfile.objects.filter(user_id=organization_member_user.user.username).exists()
    assert AccountProfileOrganization.objects.filter(accountprofile=ap).exists()

    client.force_login(organization_member_user.user)

    # Get organizations list
    response = client.get(reverse("organization_list"))

    assert response.status_code == 200
    response = response.json()

    # should receive the organization user is admin of
    assert len(response) == 1


def test_get_organizations_list_global_admin(client, global_admin_user):
    org1 = Organization.objects.create(
        name='Some org1'
    )

    org2 = Organization.objects.create(
        name='Some org2'
    )

    # Sanity check on the test data relationships.
    assert Organization.objects.filter(id=org1.id).exists()

    client.force_login(global_admin_user.user)

    # Get organizations list
    response = client.get(reverse("organization_list"))

    assert response.status_code == 200
    response = response.json()

    # global admins should receive all organizations even without a profile
    assert len(response) == 2


def test_get_inbound_integration_configuration_list_client_user(client, client_user):

    client.force_login(client_user.user)

    # Get inbound integration configuration list
    response = client.get(reverse("inboundintegrationconfiguration_list"), HTTP_X_USERINFO=client_user.user_info)

    assert response.status_code == 200
    response = response.json()

    assert len(response) == 1


class User(NamedTuple):
    user: Any = None
    user_info: bytes = None


@pytest.fixture
def global_admin_user(db, django_user_model):
    password = django_user_model.objects.make_random_password()
    user_const = dict(last_name='Owen', first_name='Harry')
    user_id = str(uuid.uuid4())
    username = 'harry.owen@vulcan.com'
    user = django_user_model.objects.create_superuser(
        user_id, username, password,
        **user_const)
    user_info = {'sub': user_id,
                 'username': username}

    x_user_info = base64.b64encode(json.dumps(user_info).encode("utf-8"))

    group_name = DjangoGroups.GLOBAL_ADMIN.value
    group = Group.objects.create(name=group_name)
    user.groups.add(group)
    user.save()

    u = User(user_info=x_user_info,
             user=user)

    return u


@pytest.fixture
def organization_member_user(db, django_user_model):
    password = django_user_model.objects.make_random_password()
    user_const = dict(last_name='Owen', first_name='Harry')
    user_id = str(uuid.uuid4())
    username = 'harry.owen@vulcan.com'
    user = django_user_model.objects.create_superuser(
        user_id, username, password,
        **user_const)
    user_info = {'sub': user_id,
                 'username': username}

    x_user_info = base64.b64encode(json.dumps(user_info).encode("utf-8"))

    group_name = DjangoGroups.ORGANIZATION_MEMBER.value
    group = Group.objects.create(name=group_name)
    user.groups.add(group)
    user.save()

    u = User(user_info=x_user_info,
             user=user)

    return u


@pytest.fixture
def client_user(db, django_user_model):
    password = django_user_model.objects.make_random_password()
    user_const = dict(last_name='Owen', first_name='Harry')
    username = 'service-account-test-function'
    user_id = str(uuid.uuid4())
    client_id = 'test-function'

    user_info = {'sub': user_id,
                 'client_id': client_id,
                 'username': username}

    x_user_info = base64.b64encode(json.dumps(user_info).encode("utf-8"))

    user = django_user_model.objects.create_superuser(
        user_id, username, password,
        **user_const)

    # arrange client profile that will map to this client
    iit = InboundIntegrationType.objects.create(
        name='Some integration type',
        slug='some-integration-type',
        description='Some integration type.'
    )

    org = Organization.objects.create(
        name='Some org.'
    )

    ii = InboundIntegrationConfiguration.objects.create(
        type=iit,
        name='some ii',
        owner=org,
        enabled=True
    )

    client_profile = ClientProfile.objects.create(client_id=client_id,
                                                  type=iit)

    u = User(user_info=x_user_info,
              user=user)

    return u

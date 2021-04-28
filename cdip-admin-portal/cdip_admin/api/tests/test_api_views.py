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
    Organization, Device, DeviceState


def test_get_integration_type_list(client, global_admin_user):

        iit = InboundIntegrationType.objects.create(
            name='Some integration type',
            slug='some-integration-type',
            description='Some integration type.'

        )

        client.force_login(global_admin_user.user)

        response = client.get(reverse("inboundintegrationtype_list"), HTTP_X_USERINFO=global_admin_user.user_info)

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
                              data={'inbound_id': str(ii.id)},
                              HTTP_X_USERINFO=global_admin_user.user_info)

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
    response = client.get(reverse("organization_list"), HTTP_X_USERINFO=organization_member_user.user_info)

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
    response = client.get(reverse("organization_list"), HTTP_X_USERINFO=organization_member_user.user_info)

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
    response = client.get(reverse("organization_list"), HTTP_X_USERINFO=global_admin_user.user_info)

    assert response.status_code == 200
    response = response.json()

    # global admins should receive all organizations even without a profile
    assert len(response) == 2


def test_get_inbound_integration_configuration_list_client_user(client, client_user):

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
    )

    # arrange data we want to check is not in the response
    o_iit = InboundIntegrationType.objects.create(
        name='Some other integration type',
        slug='some-other-integration-type',
        description='Some other integration type.'
    )


    o_ii = InboundIntegrationConfiguration.objects.create(
        type=o_iit,
        name='some other ii',
        owner=org,
    )

    client_profile = ClientProfile.objects.create(client_id='test-function',
                                                  type=iit)

    client.force_login(client_user.user)

    # Get inbound integration configuration list
    response = client.get(reverse("inboundintegrationconfiguration_list"), HTTP_X_USERINFO=client_user.user_info)

    assert response.status_code == 200
    response = response.json()

    assert len(response) == 1

    assert str(ii.id) in [item['id'] for item in response]
    assert str(o_iit.id) not in [item['id'] for item in response]


def test_get_inbound_integration_configurations_detail_client_user(client, client_user):

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
    )

    # arrange data we want to check is not in the response
    o_iit = InboundIntegrationType.objects.create(
        name='Some other integration type',
        slug='some-other-integration-type',
        description='Some other integration type.'
    )


    o_ii = InboundIntegrationConfiguration.objects.create(
        type=o_iit,
        name='some other ii',
        owner=org,
    )

    client_profile = ClientProfile.objects.create(client_id='test-function',
                                                  type=iit)

    client.force_login(client_user.user)

    # Get inbound integration configuration detail
    response = client.get(reverse("inboundintegrationconfigurations_detail", kwargs={'pk': ii.id}),
                          HTTP_X_USERINFO=client_user.user_info)

    assert response.status_code == 200
    response = response.json()

    assert response['id'] == str(ii.id)

    # Get inbound integration configuration detail for other type
    response = client.get(reverse("inboundintegrationconfigurations_detail", kwargs={'pk': o_ii.id}),
                          HTTP_X_USERINFO=client_user.user_info)

    # expect permission denied since this client is not configured for that type
    assert response.status_code == 403


def test_get_inbound_integration_configurations_detail_organization_member_hybrid(client, organization_member_user):

    iit = InboundIntegrationType.objects.create(
        name='Some integration type',
        slug='some-integration-type',
        description='Some integration type.'
    )

    org1 = Organization.objects.create(
        name='Some org.'
    )

    org2 = Organization.objects.create(
        name='Some org2'
    )

    ii = InboundIntegrationConfiguration.objects.create(
        type=iit,
        name='some ii',
        owner=org1,
    )

    o_iit = InboundIntegrationType.objects.create(
        name='Some other integration type',
        slug='some-other-integration-type',
        description='Some other integration type.'
    )


    o_ii = InboundIntegrationConfiguration.objects.create(
        type=o_iit,
        name='some other ii',
        owner=org2,
    )

    ap = AccountProfile.objects.create(
        user_id=organization_member_user.user.username
    )

    apo = AccountProfileOrganization.objects.create(
        accountprofile=ap,
        organization=org1,
        role=RoleChoices.VIEWER
    )

    apo2 = AccountProfileOrganization.objects.create(
        accountprofile=ap,
        organization=org2,
        role=RoleChoices.ADMIN
    )

    # Sanity check on the test data relationships.
    assert Organization.objects.filter(id=org1.id).exists()
    assert Organization.objects.filter(id=org2.id).exists()
    assert AccountProfile.objects.filter(user_id=organization_member_user.user.username).exists()
    assert AccountProfileOrganization.objects.filter(accountprofile=ap).exists()

    client.force_login(organization_member_user.user)

    # Get inbound integration configuration detail
    response = client.get(reverse("inboundintegrationconfigurations_detail", kwargs={'pk': ii.id}),
                          HTTP_X_USERINFO=organization_member_user.user_info)

    # confirm viewer role passes object permission check
    assert response.status_code == 200
    response = response.json()

    assert response['id'] == str(ii.id)

    # Get inbound integration configuration detail for other type
    response = client.get(reverse("inboundintegrationconfigurations_detail", kwargs={'pk': o_ii.id}),
                          HTTP_X_USERINFO=organization_member_user.user_info)

    # confirm admin role passes object permission check
    assert response.status_code == 200

    response = response.json()
    assert response['id'] == str(o_ii.id)


def test_put_inbound_integration_configurations_detail_client_user(client, client_user):

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
    )

    # arrange data we want to check is not in the response
    o_iit = InboundIntegrationType.objects.create(
        name='Some other integration type',
        slug='some-other-integration-type',
        description='Some other integration type.'
    )


    o_ii = InboundIntegrationConfiguration.objects.create(
        type=o_iit,
        name='some other ii',
        owner=org,
    )

    client_profile = ClientProfile.objects.create(client_id='test-function',
                                                  type=iit)

    client.force_login(client_user.user)

    state = "{'ST2010-2758': 14469584, 'ST2010-2759': 14430249, 'ST2010-2760': 14650428}"
    ii_update = {'state': state}

    # Test update of inbound integration configuration detail state
    response = client.put(reverse("inboundintegrationconfigurations_detail", kwargs={'pk': ii.id}),
                          data=json.dumps(ii_update),
                          content_type='application/json',
                          HTTP_X_USERINFO=client_user.user_info)

    assert response.status_code == 200
    response = response.json()

    assert response['state'] == state

    # Test update of inbound integration configuration detail state on different type
    response = client.put(reverse("inboundintegrationconfigurations_detail", kwargs={'pk': o_ii.id}),
                          data=json.dumps(ii_update),
                          content_type='application/json',
                          HTTP_X_USERINFO=client_user.user_info)

    # expect permission denied since this client is not configured for that type
    assert response.status_code == 403


def test_put_inbound_integration_configurations_detail_organization_member_hybrid(client, organization_member_user):

    iit = InboundIntegrationType.objects.create(
        name='Some integration type',
        slug='some-integration-type',
        description='Some integration type.'
    )

    org1 = Organization.objects.create(
        name='Some org.'
    )

    org2 = Organization.objects.create(
        name='Some org2'
    )

    ii = InboundIntegrationConfiguration.objects.create(
        type=iit,
        name='some ii',
        owner=org1,
    )

    o_iit = InboundIntegrationType.objects.create(
        name='Some other integration type',
        slug='some-other-integration-type',
        description='Some other integration type.'
    )


    o_ii = InboundIntegrationConfiguration.objects.create(
        type=o_iit,
        name='some other ii',
        owner=org2,
    )

    ap = AccountProfile.objects.create(
        user_id=organization_member_user.user.username
    )

    apo = AccountProfileOrganization.objects.create(
        accountprofile=ap,
        organization=org1,
        role=RoleChoices.VIEWER
    )

    apo2 = AccountProfileOrganization.objects.create(
        accountprofile=ap,
        organization=org2,
        role=RoleChoices.ADMIN
    )

    # Sanity check on the test data relationships.
    assert Organization.objects.filter(id=org1.id).exists()
    assert Organization.objects.filter(id=org2.id).exists()
    assert AccountProfile.objects.filter(user_id=organization_member_user.user.username).exists()
    assert AccountProfileOrganization.objects.filter(accountprofile=ap).exists()

    client.force_login(organization_member_user.user)

    # Get inbound integration configuration detail
    state = "{'ST2010-2758': 14469584, 'ST2010-2759': 14430249, 'ST2010-2760': 14650428}"
    ii_update = {'state': state}

    # Test update of inbound integration configuration detail state
    response = client.put(reverse("inboundintegrationconfigurations_detail", kwargs={'pk': ii.id}),
                          data=json.dumps(ii_update),
                          content_type='application/json',
                          HTTP_X_USERINFO=organization_member_user.user_info)

    # confirm viewer role does not pass object permission check
    assert response.status_code == 403


    # confirm admin role passes object permission check
    response = client.put(reverse("inboundintegrationconfigurations_detail", kwargs={'pk': o_ii.id}),
                          data=json.dumps(ii_update),
                          content_type='application/json',
                          HTTP_X_USERINFO=organization_member_user.user_info)

    # confirm admin role passes object permission check
    assert response.status_code == 200

    response = response.json()
    assert response['state'] == state


def test_get_device_state_list_client_user(client, client_user):

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
    )

    client_profile = ClientProfile.objects.create(client_id='test-function',
                                                  type=iit)

    device = Device.objects.create(
        external_id='some-ext-id',
        inbound_configuration=ii
    )

    device_state = DeviceState.objects.create(
        device = device,
    )

    # arrange data we want to check is not in the response
    o_iit = InboundIntegrationType.objects.create(
        name='Some other integration type',
        slug='some-other-integration-type',
        description='Some other integration type.'
    )


    o_ii = InboundIntegrationConfiguration.objects.create(
        type=o_iit,
        name='some other ii',
        owner=org,
    )

    o_device = Device.objects.create(
        external_id='some-o-ext-id',
        inbound_configuration=o_ii
    )

    o_device_state = DeviceState.objects.create(
        device=o_device,
    )

    client.force_login(client_user.user)

    # Test update of inbound integration configuration detail state
    url = "%s?inbound_config_id=%s" % (reverse("device_state_list_api"), str(ii.id))
    response = client.get(url, HTTP_X_USERINFO=client_user.user_info)

    assert response.status_code == 200
    response = response.json()

    assert len(response) == 1

    assert str(device.external_id) in [item['device_external_id'] for item in response]
    assert str(o_device.external_id) not in [item['device_external_id'] for item in response]


class User(NamedTuple):
    user: Any = None
    user_info: bytes = None


'''
Provisions a django user that is enrolled in the django group "Global Admin"
'''
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


'''
Provisions a django user that is enrolled in the django group "Organization Member"
'''
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


'''
Provisions a django user that simulates a service account or "client". Proper user info is added so that requests can be
made with header "HTTP_X_USERINFO" so that our middleware and backend appropriately add the client_id to the requests 
session, allowing the permissions checks to pass for IsServiceAccount. The associated client profile and 
dependent objects related to that client are also created here. 
'''
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

    u = User(user_info=x_user_info,
              user=user)

    return u

import pytest
from django.urls import reverse
from rest_framework.utils import json

from clients.models import ClientProfile
from conftest import setup_account_profile_mapping
from core.enums import RoleChoices

import random


pytestmark = pytest.mark.django_db

from integrations.models import (
    DeviceGroup,
    OutboundIntegrationConfiguration,
    InboundIntegrationConfiguration,
    Organization,
    Device,
)


def test_get_integration_type_list(client, global_admin_user, setup_data):
    iit = setup_data["iit1"]

    client.force_login(global_admin_user.user)

    response = client.get(
        reverse("inboundintegrationtype_list"),
        HTTP_X_USERINFO=global_admin_user.user_info,
    )

    assert response.status_code == 200

    response = response.json()

    assert str(iit.id) in [x["id"] for x in response]


def test_get_outbound_by_ibc(client, global_admin_user, setup_data):
    ii = setup_data["ii1"]
    oi = setup_data["oi1"]
    other_oi = setup_data["oi2"]
    d1 = setup_data["d1"]

    # Sanity check on the test data relationships.
    assert Device.objects.filter(inbound_configuration=ii).exists()
    assert DeviceGroup.objects.filter(devices__inbound_configuration=ii).exists()
    assert OutboundIntegrationConfiguration.objects.filter(
        devicegroup__devices__inbound_configuration=ii
    ).exists()

    client.force_login(global_admin_user.user)

    view = reverse("outboundintegrationconfiguration_list")
    # Get destinations by inbound-id.
    response = client.get(
        view,
        data={"inbound_id": str(ii.id), "device_id": d1.external_id},
        HTTP_X_USERINFO=global_admin_user.user_info,
    )

    assert response.status_code == 200
    response = response.json()

    assert len(response) == 1
    assert str(oi.id) in [item["id"] for item in response]
    assert not str(other_oi.id) in [item["id"] for item in response]


def test_getting_outbound_for_absent_device(client, global_admin_user, setup_data):
    '''
    Test for case described at https://allenai.atlassian.net/browse/SIK-1262
    It is the case where a client queries for OutboundIntegration data by
    Inbound ID and Device.external_id. The Inbound ID is valid, but the Device.external_id
    is not present in the database.
    The desired result is that the Device is added to the Integration and that the
    associated Outbound Integration is returned.
    '''
    ii = setup_data["ii1"]
    oi = setup_data["oi1"]
    other_oi = setup_data["oi2"]

    client.force_login(global_admin_user.user)

    an_external_id = "".join(random.sample([chr(x) for x in range(97, 97 + 26)], 12))
    view = reverse("outboundintegrationconfiguration_list")

    # Get destinations by inbound-id.
    response = client.get(
        view,
        data={"inbound_id": str(ii.id), "device_id": an_external_id},
        HTTP_X_USERINFO=global_admin_user.user_info,
    )

    assert response.status_code == 200
    response = response.json()

    assert len(response) == 1
    assert str(oi.id) in [item["id"] for item in response]
    assert not str(other_oi.id) in [item["id"] for item in response]

    # Assert that the previously unknown device has been created.
    assert Device.objects.filter(external_id=an_external_id, inbound_configuration=ii).exists()


def test_get_organizations_list_organization_member_viewer(
    client, organization_member_user, setup_data
):
    org1 = setup_data["org1"]

    account_profile_mapping = {
        (organization_member_user.user, org1, RoleChoices.VIEWER)
    }
    setup_account_profile_mapping(account_profile_mapping)

    client.force_login(organization_member_user.user)

    # Get organizations list
    response = client.get(
        reverse("organization_list"), HTTP_X_USERINFO=organization_member_user.user_info
    )

    assert response.status_code == 200
    response = response.json()

    # should receive the organization user is viewer of
    assert len(response) == Organization.objects.filter(id=org1.id).count()


def test_get_organizations_list_organization_member_admin(
    client, organization_member_user, setup_data
):
    org1 = setup_data["org1"]

    account_profile_mapping = {(organization_member_user.user, org1, RoleChoices.ADMIN)}
    setup_account_profile_mapping(account_profile_mapping)

    client.force_login(organization_member_user.user)

    # Get organizations list
    response = client.get(
        reverse("organization_list"), HTTP_X_USERINFO=organization_member_user.user_info
    )

    assert response.status_code == 200
    response = response.json()

    # should receive the organization user is admin of
    assert len(response) == Organization.objects.filter(id=org1.id).count()


def test_get_organizations_list_global_admin(client, global_admin_user, setup_data):
    client.force_login(global_admin_user.user)

    # Get organizations list
    response = client.get(
        reverse("organization_list"), HTTP_X_USERINFO=global_admin_user.user_info
    )

    assert response.status_code == 200
    response = response.json()

    # global admins should receive all organizations even without a profile
    assert len(response) == Organization.objects.count()


def test_get_inbound_integration_configuration_list_client_user(
    client, client_user, setup_data
):

    iit1 = setup_data["iit1"]
    ii = setup_data["ii1"]
    o_ii = setup_data["ii2"]

    client_profile = ClientProfile.objects.create(client_id="test-function", type=iit1)

    client.force_login(client_user.user)

    # Get inbound integration configuration list
    response = client.get(
        reverse("inboundintegrationconfiguration_list"),
        HTTP_X_USERINFO=client_user.user_info,
    )

    assert response.status_code == 200
    response = response.json()

    assert (
        len(response)
        == InboundIntegrationConfiguration.objects.filter(type=iit1).count()
    )

    assert str(ii.id) in [item["id"] for item in response]

    # confirm integration of different type not present in results
    assert str(o_ii.id) not in [item["id"] for item in response]


def test_get_inbound_integration_configurations_detail_client_user(
    client, client_user, setup_data
):

    iit = setup_data["iit1"]
    ii = setup_data["ii1"]
    o_ii = setup_data["ii2"]

    client_profile = ClientProfile.objects.create(client_id="test-function", type=iit)

    client.force_login(client_user.user)

    # Get inbound integration configuration detail
    response = client.get(
        reverse("inboundintegrationconfigurations_detail", kwargs={"pk": ii.id}),
        HTTP_X_USERINFO=client_user.user_info,
    )

    assert response.status_code == 200
    response = response.json()

    assert response["id"] == str(ii.id)

    # Get inbound integration configuration detail for other type
    response = client.get(
        reverse("inboundintegrationconfigurations_detail", kwargs={"pk": o_ii.id}),
        HTTP_X_USERINFO=client_user.user_info,
    )

    # expect permission denied since this client is not configured for that type
    assert response.status_code == 403


def test_get_inbound_integration_configurations_detail_organization_member_hybrid(
    client, organization_member_user, setup_data
):

    org1 = setup_data["org1"]
    org2 = setup_data["org2"]
    ii = setup_data["ii1"]
    o_ii = setup_data["ii2"]

    account_profile_mapping = {
        (organization_member_user.user, org1, RoleChoices.VIEWER),
        (organization_member_user.user, org2, RoleChoices.ADMIN),
    }
    setup_account_profile_mapping(account_profile_mapping)

    client.force_login(organization_member_user.user)

    # Get inbound integration configuration detail
    response = client.get(
        reverse("inboundintegrationconfigurations_detail", kwargs={"pk": ii.id}),
        HTTP_X_USERINFO=organization_member_user.user_info,
    )

    # confirm viewer role passes object permission check
    assert response.status_code == 200
    response = response.json()

    assert response["id"] == str(ii.id)

    # Get inbound integration configuration detail for other type
    response = client.get(
        reverse("inboundintegrationconfigurations_detail", kwargs={"pk": o_ii.id}),
        HTTP_X_USERINFO=organization_member_user.user_info,
    )

    # confirm admin role passes object permission check
    assert response.status_code == 200

    response = response.json()
    assert response["id"] == str(o_ii.id)


def test_put_inbound_integration_configurations_detail_client_user(
    client, client_user, setup_data
):

    # arrange client profile that will map to this client
    iit = setup_data["iit1"]
    ii = setup_data["ii1"]
    o_ii = setup_data["ii2"]

    client_profile = ClientProfile.objects.create(client_id="test-function", type=iit)

    client.force_login(client_user.user)

    state = (
        "{'ST2010-2758': 14469584, 'ST2010-2759': 14430249, 'ST2010-2760': 14650428}"
    )
    ii_update = {"state": state}

    # Test update of inbound integration configuration detail state
    response = client.put(
        reverse("inboundintegrationconfigurations_detail", kwargs={"pk": ii.id}),
        data=json.dumps(ii_update),
        content_type="application/json",
        HTTP_X_USERINFO=client_user.user_info,
    )

    assert response.status_code == 200
    response = response.json()

    assert response["state"] == state

    # Test update of inbound integration configuration detail state on different type
    response = client.put(
        reverse("inboundintegrationconfigurations_detail", kwargs={"pk": o_ii.id}),
        data=json.dumps(ii_update),
        content_type="application/json",
        HTTP_X_USERINFO=client_user.user_info,
    )

    # expect permission denied since this client is not configured for that type
    assert response.status_code == 403


def test_put_inbound_integration_configurations_detail_organization_member_hybrid(
    client, organization_member_user, setup_data
):
    org1 = setup_data["org1"]
    org2 = setup_data["org2"]
    ii = setup_data["ii1"]
    o_ii = setup_data["ii2"]

    account_profile_mapping = {
        (organization_member_user.user, org1, RoleChoices.VIEWER),
        (organization_member_user.user, org2, RoleChoices.ADMIN),
    }
    setup_account_profile_mapping(account_profile_mapping)

    client.force_login(organization_member_user.user)

    # Get inbound integration configuration detail
    state = (
        "{'ST2010-2758': 14469584, 'ST2010-2759': 14430249, 'ST2010-2760': 14650428}"
    )
    ii_update = {"state": state}

    # Test update of inbound integration configuration detail state
    response = client.put(
        reverse("inboundintegrationconfigurations_detail", kwargs={"pk": ii.id}),
        data=json.dumps(ii_update),
        content_type="application/json",
        HTTP_X_USERINFO=organization_member_user.user_info,
    )

    # confirm viewer role does not pass object permission check
    assert response.status_code == 403

    # confirm admin role passes object permission check
    response = client.put(
        reverse("inboundintegrationconfigurations_detail", kwargs={"pk": o_ii.id}),
        data=json.dumps(ii_update),
        content_type="application/json",
        HTTP_X_USERINFO=organization_member_user.user_info,
    )

    # confirm admin role passes object permission check
    assert response.status_code == 200

    response = response.json()
    assert response["state"] == state


def test_get_device_state_list_client_user(client, client_user, setup_data):

    # arrange client profile that will map to this client
    iit = setup_data["iit1"]
    ii = setup_data["ii1"]
    device = setup_data["d1"]
    o_device = setup_data["d2"]

    client_profile = ClientProfile.objects.create(client_id="test-function", type=iit)

    client.force_login(client_user.user)

    # Test update of inbound integration configuration detail state
    url = "%s?inbound_config_id=%s" % (reverse("device_state_list_api"), str(ii.id))
    response = client.get(url, HTTP_X_USERINFO=client_user.user_info)

    assert response.status_code == 200
    response = response.json()

    assert len(response) == 1

    assert str(device.external_id) in [item["device_external_id"] for item in response]
    assert str(o_device.external_id) not in [
        item["device_external_id"] for item in response
    ]


def test_new_device_from_location_is_added_to_default_group_as_global_admin(client, global_admin_user, setup_data):
    device = setup_data["d1"]
    request_data = {
        "inbound_configuration": str(device.inbound_configuration.id),
        "external_id": device.external_id,
    }

    client.force_login(global_admin_user.user)
    response = client.post(
        reverse("device_list_api"),
        data=json.dumps(request_data),
        content_type="application/json",
        HTTP_X_USERINFO=global_admin_user.user_info,
    )
    # Check the request response
    assert response.status_code == 200
    response_data = response.json()
    assert "id" in response_data
    # Check that the device is added to the default device group
    device.refresh_from_db()
    assert device.default_group is not None
    assert device in device.default_group.devices.all()



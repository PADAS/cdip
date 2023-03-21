import pytest
from django.urls import reverse


pytestmark = pytest.mark.django_db

from integrations.models import (
    Organization,
)

"""
    ToDo: Create tests for:
    Create Org
    Delete Org
    View list of the Orgs I belong to
    View Org Details
    Edit Org
    Invite User
    View Memebers List
    View Member Details
    Edit Member
    Remove Member
"""


def test_create_organization_as_superuser(api_client, superuser, setup_data):
    # ToDo: Implement
    pass


def test_delete_organization_as_superuser(api_client, superuser, setup_data):
    # ToDo: Implement
    pass


def test_list_organizations_as_superuser(api_client, superuser, setup_data):
    # ToDo: Implement
    pass


def test_list_organizations_as_org_admin(api_client, org_admin_user, setup_data):
    # ToDo: Implement
    pass


def test_list_organizations_as_org_viewer(api_client, org_viewer_user, setup_data):
    # ToDo: Implement
    pass


def test_retrieve_organization_details_as_superuser(api_client, superuser, setup_data):
    # ToDo: Implement
    pass


def test_retrieve_organization_details_as_org_admin(api_client, org_admin_user, setup_data):
    # ToDo: Implement
    pass


def test_retrieve_organization_details_as_org_viewer(api_client, org_viewer_user, setup_data):
    # ToDo: Implement
    pass


def test_update_organization_details_as_superuser(api_client, superuser, setup_data):
    # ToDo: Implement
    pass


def test_update_organization_details_as_org_admin(api_client, org_admin_user, setup_data):
    # ToDo: Implement
    pass


def test_invite_org_admin_as_superuser(api_client, superuser, setup_data):
    # ToDo: Implement
    pass


def test_invite_org_admin_as_org_admin(api_client, org_admin, setup_data):
    # ToDo: Implement
    pass


def test_invite_org_viewer_as_superuser(api_client, superuser, setup_data):
    # ToDo: Implement
    pass


def test_invite_org_viewer_as_org_admin(api_client, org_admin, setup_data):
    # ToDo: Implement
    pass


def test_cannot_invite_users_as_org_viewer(api_client, org_viewer, setup_data):
    # ToDo: Implement
    pass


def test_new_device_from_location_is_added_to_default_group_as_global_admin(api_client, global_admin_user, get_device_id, setup_data):
    """
    Test for case described at https://allenai.atlassian.net/browse/SIK-1267
    Given an observation from an unknown device
    When the routing service calls the Device creation endpoint of the Portal's API
    Then a new Device is created in the Portal
    And the Device is added to the default DeviceGroup of the related InboundIntegrationConfiguration
    """
    inbound_configuration = setup_data["ii1"]
    device_external_id = get_device_id()
    request_data = {
        "inbound_configuration": str(inbound_configuration.id),
        "external_id": device_external_id,
    }

    api_client.force_authenticate(global_admin_user.user)
    response = api_client.post(
        reverse("device_list_api"),
        data=request_data,
        HTTP_X_USERINFO=global_admin_user.user_info,
    )

    # Check the request response
    assert response.status_code == 200
    response_data = response.json()
    assert "id" in response_data
    # Check that the device is created and added to the default device group
    assert Device.objects.filter(external_id=device_external_id).exists()
    device = Device.objects.get(external_id=device_external_id)
    assert device.default_group is not None
    assert device.default_group == inbound_configuration.default_devicegroup
    assert device in device.default_group.devices.all()



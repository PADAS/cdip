import pytest
from django.urls import reverse
from rest_framework import status

pytestmark = pytest.mark.django_db

from integrations.models import (
    Organization,
)


def test_create_organization_as_superuser(api_client, organization, superuser):
    request_data = {
      "name": "Grumeti",
      "description": "A reserve in Tanzania"
    }

    api_client.force_authenticate(superuser)
    response = api_client.post(
        reverse("organizations-list"),
        data=request_data
    )

    # Check the request response
    assert response.status_code == status.HTTP_201_CREATED
    response_data = response.json()
    assert "id" in response_data
    # Check that the organization was created in the database
    assert Organization.objects.filter(name=request_data["name"]).exists()


def test_cannot_create_organization_as_org_admin(api_client, org_admin_user, setup_data):
    request_data = {
      "name": "New Organization",
    }

    api_client.force_authenticate(org_admin_user)
    response = api_client.post(
        reverse("organizations-list"),
        data=request_data
    )

    # Check the request response
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_cannot_create_organization_as_org_viewer(api_client, org_viewer_user, setup_data):
    request_data = {
      "name": "New Organization",
    }

    api_client.force_authenticate(org_viewer_user)
    response = api_client.post(
        reverse("organizations-list"),
        data=request_data
    )

    # Check the request response
    assert response.status_code == status.HTTP_403_FORBIDDEN

# ToDo: Pending tests
# def test_delete_organization_as_superuser(api_client, superuser, setup_data):
#     # ToDo: Implement
#     pass
#
#
# def test_list_organizations_as_superuser(api_client, superuser, setup_data):
#     # ToDo: Implement
#     pass
#
#
# def test_list_organizations_as_org_admin(api_client, org_admin_user, setup_data):
#     # ToDo: Implement
#     pass
#
#
# def test_list_organizations_as_org_viewer(api_client, org_viewer_user, setup_data):
#     # ToDo: Implement
#     pass
#
#
# def test_retrieve_organization_details_as_superuser(api_client, superuser, setup_data):
#     # ToDo: Implement
#     pass
#
#
# def test_retrieve_organization_details_as_org_admin(api_client, org_admin_user, setup_data):
#     # ToDo: Implement
#     pass
#
#
# def test_retrieve_organization_details_as_org_viewer(api_client, org_viewer_user, setup_data):
#     # ToDo: Implement
#     pass
#
#
# def test_update_organization_details_as_superuser(api_client, superuser, setup_data):
#     # ToDo: Implement
#     pass
#
#
# def test_update_organization_details_as_org_admin(api_client, org_admin_user, setup_data):
#     # ToDo: Implement
#     pass
#
#
# def test_invite_org_admin_as_superuser(api_client, superuser, setup_data):
#     # ToDo: Implement
#     pass
#
#
# def test_invite_org_admin_as_org_admin(api_client, org_admin, setup_data):
#     # ToDo: Implement
#     pass
#
#
# def test_invite_org_viewer_as_superuser(api_client, superuser, setup_data):
#     # ToDo: Implement
#     pass
#
#
# def test_invite_org_viewer_as_org_admin(api_client, org_admin, setup_data):
#     # ToDo: Implement
#     pass
#
#
# def test_cannot_invite_users_as_org_viewer(api_client, org_viewer, setup_data):
#     # ToDo: Implement
#     pass
#
#
# def test_list_organization_members_as_superuser(api_client, superuser, setup_data):
#     # ToDo: Implement
#     pass
#
#
# def test_list_organization_members_as_org_admin(api_client, org_admin_user, setup_data):
#     # ToDo: Implement
#     pass
#
#
# def test_list_organization_members_as_org_viewer(api_client, org_viewer_user, setup_data):
#     # ToDo: Implement
#     pass
#
#
# def test_retrieve_member_details_as_superuser(api_client, superuser, setup_data):
#     # ToDo: Implement
#     pass
#
#
# def test_retrieve_member_details_as_org_admin(api_client, org_admin_user, setup_data):
#     # ToDo: Implement
#     pass
#
#
# def test_cannot_retrieve_other_member_details_as_org_viewer(api_client, org_viewer_user, setup_data):
#     # ToDo: Implement
#     pass
#
#
# def test_update_member_details_as_superuser(api_client, superuser, setup_data):
#     # ToDo: Implement
#     pass
#
#
# def test_update_member_details_as_org_admin(api_client, org_admin_user, setup_data):
#     # ToDo: Implement
#     pass
#
#
# def test_cannot_update_member_details_as_org_viewer(api_client, org_viewer_user, setup_data):
#     # ToDo: Implement
#     pass
#
#
# def test_remove_member_as_superuser(api_client, superuser, setup_data):
#     # ToDo: Implement
#     pass
#
#
# def test_remove_member_as_org_admin(api_client, org_admin_user, setup_data):
#     # ToDo: Implement
#     pass
#
#
# def test_cannot_remove_member_as_org_viewer(api_client, org_viewer_user, setup_data):
#     # ToDo: Implement
#     pass


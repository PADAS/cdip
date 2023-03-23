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


def test_cannot_create_organization_as_org_admin(api_client, org_admin_user):
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


def test_cannot_create_organization_as_org_viewer(api_client, org_viewer_user):
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


def test_delete_organization_as_superuser(api_client, superuser, organization):
    api_client.force_authenticate(superuser)
    response = api_client.delete(
        reverse("organizations-detail", kwargs={"pk": organization.id})
    )

    # Check the request response
    assert response.status_code == status.HTTP_204_NO_CONTENT
    # Check that the organization was deleted in the database
    with pytest.raises(Organization.DoesNotExist):
        Organization.objects.get(id=organization.id)


def test_cannot_delete_organization_as_org_admin(api_client, org_admin_user, organization):
    api_client.force_authenticate(org_admin_user)
    response = api_client.delete(
        reverse("organizations-detail", kwargs={"pk": organization.id})
    )

    # Check the request response
    assert response.status_code == status.HTTP_403_FORBIDDEN
    # Check that the organization was NOT deleted in the database
    assert Organization.objects.filter(id=organization.id).exists()


def test_cannot_delete_organization_as_org_viewer(api_client, org_viewer_user, organization):
    api_client.force_authenticate(org_viewer_user)
    response = api_client.delete(
        reverse("organizations-detail", kwargs={"pk": organization.id})
    )

    # Check the request response
    assert response.status_code == status.HTTP_403_FORBIDDEN
    # Check that the organization was NOT deleted in the database
    assert Organization.objects.filter(id=organization.id).exists()


def test_list_organizations_as_superuser(api_client, superuser, organizations_list):
    api_client.force_authenticate(superuser)
    response = api_client.get(
        reverse("organizations-list"),
    )
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    # Check that the superuser can see all the organizations
    expected_organizations_ids = [str(o.id) for o in organizations_list]
    for org in response_data["results"]:
        assert org["id"] in expected_organizations_ids



# ToDo: Pending tests
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


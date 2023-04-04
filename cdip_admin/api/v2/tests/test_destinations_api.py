import pytest
from django.urls import reverse
from rest_framework import status
from integrations.models import (
    OutboundIntegrationConfiguration
)


pytestmark = pytest.mark.django_db


def _test_list_destinations(api_client, user, organization):
    api_client.force_authenticate(user)
    response = api_client.get(
        reverse("destinations-list"),
    )
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    destinations = response_data["results"]
    if user.is_superuser:
        # The superuser can see all the destinations
        destinations_qs = OutboundIntegrationConfiguration.objects.all()
    else: # Only see destinations owned by the organization(s) where the user is a member
        destinations_qs = OutboundIntegrationConfiguration.objects.filter(owner=organization)
    expected_destinations_ids = [str(uid) for uid in destinations_qs.values_list("id", flat=True)]
    assert len(destinations) == len(expected_destinations_ids)
    for dest in destinations:
        assert dest.get("id") in expected_destinations_ids
        assert "name" in dest
        assert "url" in dest
        assert "enabled" in dest
        assert "type" in dest
        owner = dest.get("owner")
        assert owner
        assert "id" in owner
        assert "name" in owner
        assert "description" in owner
        configuration = dest.get("configuration")
        assert configuration
        assert "site_name" in configuration
        assert "username" in configuration
        assert "password" in configuration
        assert "status" in dest
        # ToDo test status further once defined/implemented.


def test_list_destinations_as_superuser(api_client, superuser, organization, destinations_list):
    _test_list_destinations(
        api_client=api_client,
        user=superuser,
        organization=organization
    )


def test_list_destinations_as_org_admin(api_client, org_admin_user, organization, destinations_list):
    _test_list_destinations(
        api_client=api_client,
        user=org_admin_user,
        organization=organization
    )


def test_list_destinations_as_org_viewer(api_client, org_viewer_user, organization, destinations_list):
    _test_list_destinations(
        api_client=api_client,
        user=org_viewer_user,
        organization=organization
    )


def _test_create_destination(api_client, user, owner, destination_type, destination_name, configuration):
    request_data = {
      "name": destination_name,
      "type": str(destination_type.id),
      "owner": str(owner.id),
      "url": "https://reservex.pamdas.org",
      "configuration": configuration
    }
    api_client.force_authenticate(user)
    response = api_client.post(
        reverse("destinations-list"),
        data=request_data,
        format='json'
    )
    assert response.status_code == status.HTTP_201_CREATED
    response_data = response.json()
    assert "id" in response_data
    # Check that the destination was created in the database
    assert OutboundIntegrationConfiguration.objects.filter(name=request_data["name"]).exists()


def test_create_destination_as_superuser(api_client, superuser, organization, destination_type_er, get_random_id):
    _test_create_destination(
        api_client=api_client,
        user=superuser,
        owner=organization,
        destination_type=destination_type_er,
        destination_name=f"Reserve X {get_random_id()}",
        configuration={
            "site": "https://reservex.pamdas.org",
            "username": "reservex@pamdas.org",
            "password": "P4sSW0rD"
        }
    )


def test_create_destination_as_org_admin(api_client, org_admin_user, organization, destination_type_er, get_random_id):
    _test_create_destination(
        api_client=api_client,
        user=org_admin_user,
        owner=organization,
        destination_type=destination_type_er,
        destination_name=f"Reserve Y {get_random_id()}",
        configuration={
            "site": "https://reservey.pamdas.org",
            "username": "reservey@pamdas.org",
            "password": "P4sSW0rD"
        }
    )


def _test_cannot_create_destination(api_client, user, owner, destination_type, destination_name, configuration):
    request_data = {
      "name": destination_name,
      "type": str(destination_type.id),
      "owner": str(owner.id),
      "url": "https://reservex.pamdas.org",
      "configuration": configuration
    }
    api_client.force_authenticate(user)
    response = api_client.post(
        reverse("destinations-list"),
        data=request_data,
        format='json'
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_cannot_create_destination_as_org_viewer(api_client, org_viewer_user, organization, destination_type_er, get_random_id):
    _test_cannot_create_destination(
        api_client=api_client,
        user=org_viewer_user,
        owner=organization,
        destination_type=destination_type_er,
        destination_name=f"Reserve Z {get_random_id()}",
        configuration={
            "site": "https://reservez.pamdas.org",
            "username": "reservez@pamdas.org",
            "password": "P4sSW0rD"
        }
    )

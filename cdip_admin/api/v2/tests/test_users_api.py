import pytest
from django.urls import reverse
from rest_framework import status


pytestmark = pytest.mark.django_db


def test_retrieve_user_details_as_superuser(api_client, superuser, eula_v1):
    api_client.force_authenticate(superuser)
    response = api_client.get(
        reverse("user-details")
    )
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    assert response_data.get("is_superuser")
    assert response_data.get("id") == superuser.id
    assert response_data.get("username") == superuser.username
    assert response_data.get("email") == superuser.email
    assert "full_name" in response_data
    assert response_data.get("accepted_eula") == False


def test_retrieve_user_details_as_org_admin(api_client, org_admin_user, eula_v1):
    api_client.force_authenticate(org_admin_user)
    response = api_client.get(
        reverse("user-details")
    )
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    assert "is_superuser" in response_data
    assert not response_data["is_superuser"]
    assert response_data.get("id") == org_admin_user.id
    assert response_data.get("username") == org_admin_user.username
    assert response_data.get("email") == org_admin_user.email
    assert response_data.get("accepted_eula") == False


def test_retrieve_user_details_as_org_viewer(api_client, org_viewer_user, eula_v1):
    api_client.force_authenticate(org_viewer_user)
    response = api_client.get(
        reverse("user-details")
    )
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    assert "is_superuser" in response_data
    assert not response_data["is_superuser"]
    assert response_data.get("id") == org_viewer_user.id
    assert response_data.get("username") == org_viewer_user.username
    assert response_data.get("email") == org_viewer_user.email
    assert response_data.get("accepted_eula") == False

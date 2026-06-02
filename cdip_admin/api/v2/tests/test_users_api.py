import pytest
from django.urls import reverse
from rest_framework import status

from accounts.models import AccountProfile, AccountProfileOrganization


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
    # Superuser doesn't have an AccountProfile by default
    assert response_data.get("contact_email") is None
    assert response_data.get("workspaces") == []


def test_retrieve_user_details_as_org_admin(api_client, org_admin_user, organization, eula_v1):
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
    assert response_data.get("first_name") == org_admin_user.first_name
    assert response_data.get("last_name") == org_admin_user.last_name
    assert response_data.get("accepted_eula") == False
    assert response_data.get("contact_email") is None
    workspaces = response_data.get("workspaces")
    assert isinstance(workspaces, list)
    assert len(workspaces) == 1
    ws = workspaces[0]
    assert ws["workspace_id"] == str(organization.id)
    assert ws["name"] == organization.name
    assert ws["role"] == "admin"
    assert "id" in ws


def test_retrieve_user_details_as_org_viewer(api_client, org_viewer_user, organization, eula_v1):
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
    workspaces = response_data.get("workspaces")
    assert len(workspaces) == 1
    assert workspaces[0]["role"] == "viewer"
    assert workspaces[0]["workspace_id"] == str(organization.id)


def test_retrieve_user_details_returns_contact_email_when_set(api_client, org_admin_user, eula_v1):
    profile = org_admin_user.accountprofile
    profile.contact_email = "caroline.contact@example.org"
    profile.save(update_fields=["contact_email"])

    api_client.force_authenticate(org_admin_user)
    response = api_client.get(reverse("user-details"))

    assert response.status_code == status.HTTP_200_OK
    assert response.json().get("contact_email") == "caroline.contact@example.org"


def test_patch_user_details_updates_user_and_profile_fields(api_client, org_admin_user, eula_v1):
    api_client.force_authenticate(org_admin_user)
    payload = {
        "first_name": "Caro",
        "last_name": "Westside",
        "contact_email": "caro.westside@example.org",
    }
    response = api_client.patch(reverse("user-details"), data=payload, format="json")

    assert response.status_code == status.HTTP_200_OK
    org_admin_user.refresh_from_db()
    assert org_admin_user.first_name == "Caro"
    assert org_admin_user.last_name == "Westside"
    assert org_admin_user.accountprofile.contact_email == "caro.westside@example.org"
    # Response uses the retrieve serializer shape
    body = response.json()
    assert body["first_name"] == "Caro"
    assert body["last_name"] == "Westside"
    assert body["contact_email"] == "caro.westside@example.org"


def test_patch_user_details_rejects_invalid_email(api_client, org_admin_user, eula_v1):
    api_client.force_authenticate(org_admin_user)
    response = api_client.patch(
        reverse("user-details"),
        data={"contact_email": "not-an-email"},
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "contact_email" in response.json()


def test_patch_user_details_accepts_null_contact_email(api_client, org_admin_user, eula_v1):
    profile = org_admin_user.accountprofile
    profile.contact_email = "old@example.org"
    profile.save(update_fields=["contact_email"])

    api_client.force_authenticate(org_admin_user)
    response = api_client.patch(
        reverse("user-details"),
        data={"contact_email": None},
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK
    profile.refresh_from_db()
    assert profile.contact_email is None


def test_patch_user_details_creates_profile_for_superuser(api_client, superuser, eula_v1):
    assert not AccountProfile.objects.filter(user=superuser).exists()

    api_client.force_authenticate(superuser)
    response = api_client.patch(
        reverse("user-details"),
        data={"contact_email": "super@example.org"},
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK
    profile = AccountProfile.objects.get(user=superuser)
    assert profile.contact_email == "super@example.org"


def test_patch_user_details_with_partial_payload(api_client, org_admin_user, eula_v1):
    original_email = org_admin_user.accountprofile.contact_email
    api_client.force_authenticate(org_admin_user)
    response = api_client.patch(
        reverse("user-details"),
        data={"first_name": "OnlyFirst"},
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK
    org_admin_user.refresh_from_db()
    assert org_admin_user.first_name == "OnlyFirst"
    # contact_email untouched
    assert org_admin_user.accountprofile.contact_email == original_email


def test_user_details_requires_authentication(api_client):
    response = api_client.get(reverse("user-details"))
    assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

    response = api_client.patch(reverse("user-details"), data={"first_name": "X"}, format="json")
    assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)


def test_retrieve_user_details_does_not_n_plus_1_on_workspaces(
    api_client, org_admin_user, other_organization, eula_v1, django_assert_max_num_queries,
):
    # Add a second membership; query count must not scale with workspaces count.
    AccountProfileOrganization.objects.create(
        accountprofile=org_admin_user.accountprofile,
        organization=other_organization,
        role="admin",
    )
    api_client.force_authenticate(org_admin_user)

    with django_assert_max_num_queries(10):
        response = api_client.get(reverse("user-details"))

    assert response.status_code == status.HTTP_200_OK
    assert len(response.json()["workspaces"]) == 2

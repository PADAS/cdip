import pytest
from django.urls import reverse
from rest_framework import status

from accounts.models import UserAgreement, EULA

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("user", [
    ("superuser"),
    ("org_admin_user"),
    ("org_viewer_user"),
])
def test_retrieve_active_eula(request, api_client, user, eula_v1, eula_v2):
    user = request.getfixturevalue(user)
    api_client.force_authenticate(user)

    response = api_client.get(
        reverse("eula-list")
    )

    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    assert response_data.get("version") == eula_v2.version
    assert response_data.get("eula_url") == eula_v2.eula_url
    assert response_data.get("accepted") == False


@pytest.mark.parametrize("user", [
    ("superuser"),
    ("org_admin_user"),
    ("org_viewer_user"),
])
def test_accept_active_eula(request, api_client, user, eula_v1, eula_v2):
    user = request.getfixturevalue(user)
    api_client.force_authenticate(user)

    response = api_client.post(
        reverse("eula-accept")
    )

    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    assert response_data.get("accept")
    assert "date_accepted" in response_data
    agreement_in_db = UserAgreement.objects.get(user=user, eula=eula_v2)
    assert agreement_in_db.accept


@pytest.mark.parametrize("user", [
    ("superuser"),
    ("org_admin_user"),
    ("org_viewer_user"),
])
def test_new_eula_requires_new_acceptance(request, api_client, user, eula_v1):
    user = request.getfixturevalue(user)
    # Accept the active eula (v1)
    UserAgreement.objects.create(
        user=user,
        eula=eula_v1,
    )

    # A new EULA mus invalidate the previous acceptance
    eula_new_version = EULA.objects.create(
        version="Gundi_EULA_2024-05-06",
        eula_url="https://projectgundi.org/Legal-Pages/User-Agreement"
    )
    assert eula_new_version.active


    api_client.force_authenticate(user)
    response = api_client.get(
        reverse("eula-list")
    )

    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    assert response_data.get("version") == eula_new_version.version
    assert response_data.get("eula_url") == eula_new_version.eula_url
    assert response_data.get("accepted") == False

import pytest
from django.urls import reverse
from rest_framework import status
from integrations.models import (
    Route, get_user_routes_qs
)


pytestmark = pytest.mark.django_db


def _test_list_routes(api_client, user):
    api_client.force_authenticate(user)
    response = api_client.get(
        reverse("routes-list"),
    )
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    routes = response_data["results"]
    routes_qs = get_user_routes_qs(user=user)
    expected_routes_ids = [str(uid) for uid in routes_qs.values_list("id", flat=True)]
    assert len(routes) == len(expected_routes_ids)
    for route in routes:
        assert route.get("id") in expected_routes_ids
        assert "name" in route
        assert "owner" in route
        assert "data_providers" in route
        assert "destinations" in route
        assert "configuration" in route
        assert "additional" in route


def test_list_routes_as_superuser(api_client, superuser, organization, integrations_list):
    _test_list_routes(
        api_client=api_client,
        user=superuser,
    )


def test_list_routes_as_org_admin(api_client, org_admin_user, organization, integrations_list):
    _test_list_routes(
        api_client=api_client,
        user=org_admin_user,
    )


def test_list_routes_as_org_viewer(api_client, org_viewer_user, organization, integrations_list):
    _test_list_routes(
        api_client=api_client,
        user=org_viewer_user,
    )

# ToDo: Add tests for: retrieve details, create, update and delete

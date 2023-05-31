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


def _test_create_route(api_client, user, data):
    api_client.force_authenticate(user)
    response = api_client.post(
        reverse("routes-list"),
        data=data,
        format='json'
    )
    # Check the request response
    assert response.status_code == status.HTTP_201_CREATED
    response_data = response.json()
    assert "id" in response_data
    # Check that the route was created and the connection was made
    route = Route.objects.get(id=response_data["id"])
    expected_providers_ids = data.get("data_providers", [])
    providers_ids = [str(p.id) for p in route.data_providers.all()]
    assert len(providers_ids) == len(expected_providers_ids)
    assert providers_ids == expected_providers_ids
    expected_destinations_ids = sorted(data.get("destinations", []))
    destinations_ids = sorted([str(d.id) for d in route.destinations.all()])
    assert len(destinations_ids) == len(expected_destinations_ids)
    assert destinations_ids == expected_destinations_ids
    assert "configuration" in response_data
    if "configuration" in data or "configuration_id" in data:
        assert response_data["configuration"] is not None


def test_create_route_as_superuser(api_client, superuser, organization, integrations_list, provider_lotek_panthera):
    _test_create_route(
        api_client=api_client,
        user=superuser,
        data={
            "name": "Custom Route - Lotek to ER",
            "owner": str(organization.id),
            "data_providers": [
                str(provider_lotek_panthera.id)
            ],
            "destinations": [
                str(i.id) for i in integrations_list[2:4]
            ],
            # "configuration": {},  # This should be optional
            "additional": {}
        }
    )


def test_create_route_as_org_admin(
        api_client, org_admin_user_2, organization, other_organization, integrations_list, provider_movebank_ewt
):
    _test_create_route(
        api_client=api_client,
        user=org_admin_user_2,
        data={
            "name": "Custom Route - Move Bank to ER",
            "owner": str(other_organization.id),
            "data_providers": [
                str(provider_movebank_ewt.id)
            ],
            "destinations": [
                str(integrations_list[5].id)
            ],
            "additional": {}
        }
    )


def test_create_route_with_configuration_as_org_admin(
        api_client, org_admin_user_2, organization, other_organization, integrations_list, provider_movebank_ewt
):
    _test_create_route(
        api_client=api_client,
        user=org_admin_user_2,
        data={
            "name": "Custom Route - Move Bank to ER",
            "owner": str(other_organization.id),
            "data_providers": [
                str(provider_movebank_ewt.id)
            ],
            "destinations": [
                str(integrations_list[5].id)
            ],
            "configuration": {
                "name": "Route settings for EWT",
                "data": {
                    "some_setting": "ABC1234",
                }
            },
            "additional": {}
        }
    )


def test_create_route_with_configuration_id_as_org_admin(
        api_client, org_admin_user_2, organization, other_organization, integrations_list, provider_movebank_ewt, route_2
):
    _test_create_route(
        api_client=api_client,
        user=org_admin_user_2,
        data={
            "name": "Custom Route - Move Bank to ER",
            "owner": str(other_organization.id),
            "data_providers": [
                str(provider_movebank_ewt.id)
            ],
            "destinations": [
                str(integrations_list[5].id)
            ],
            "configuration_id": str(route_2.configuration.id),  # Reuse config from other route
            "additional": {}
        }
    )


def _test_cannot_create_route(api_client, user, data):
    api_client.force_authenticate(user)
    response = api_client.post(
        reverse("routes-list"),
        data=data,
        format='json'
    )
    # Check the request response
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_cannot_create_route_as_org_viewer(
        api_client, org_viewer_user, organization, other_organization, integrations_list, provider_movebank_ewt, route_2
):
    _test_cannot_create_route(
        api_client=api_client,
        user=org_viewer_user,
        data={
            "name": "Custom Route - Move Bank to ER",
            "owner": str(other_organization.id),
            "data_providers": [
                str(provider_movebank_ewt.id)
            ],
            "destinations": [
                str(integrations_list[5].id)
            ],
            "configuration_id": str(route_2.configuration.id),  # Reuse config from other route
            "additional": {}
        }
    )


def test_cannot_create_route_for_other_organization_as_org_admin(
        api_client, org_admin_user, organization, other_organization, integrations_list, provider_movebank_ewt, route_2
):
    _test_cannot_create_route(
        api_client=api_client,
        user=org_admin_user,
        data={
            "name": "Custom Route - Move Bank to ER",
            "owner": str(other_organization.id),  # The user doesn't belong to this organization
            "data_providers": [
                str(provider_movebank_ewt.id)
            ],
            "destinations": [
                str(integrations_list[5].id)
            ],
            "configuration_id": str(route_2.configuration.id),  # Reuse config from other route
            "additional": {}
        }
    )


def _test_retrieve_route_details(api_client, user, route):
    api_client.force_authenticate(user)
    response = api_client.get(
        reverse("routes-detail",  kwargs={"pk": route.id}),
    )
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    assert response_data.get("id") == str(route.id)
    assert response_data.get("name") == route.name
    assert response_data.get("owner") == str(route.owner.id)


def test_retrieve_route_details_as_superuser(
        api_client, superuser, organization, other_organization, integrations_list, route_1, route_2
):
    _test_retrieve_route_details(
        api_client=api_client,
        user=superuser,
        route=integrations_list[0].default_route
    )


def test_retrieve_route_details_as_org_admin(
        api_client, org_admin_user, organization, other_organization, integrations_list, route_1, route_2
):
    _test_retrieve_route_details(
        api_client=api_client,
        user=org_admin_user,
        route=route_1
    )


def test_retrieve_route_details_as_org_viewer(
        api_client, org_viewer_user_2, organization, other_organization, integrations_list, route_1, route_2
):
    _test_retrieve_route_details(
        api_client=api_client,
        user=org_viewer_user_2,
        route=route_2
    )


def _test_cannot_retrieve_unrelated_route_details(api_client, user, route):
    api_client.force_authenticate(user)
    response = api_client.get(
        reverse("routes-detail",  kwargs={"pk": route.id}),
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_cannot_retrieve_unrelated_route_details_as_org_viewer(
        api_client, org_viewer_user_2, organization, other_organization, integrations_list, route_1, route_2
):
    _test_cannot_retrieve_unrelated_route_details(
        api_client=api_client,
        user=org_viewer_user_2,
        route=route_1  # This route belongs to an integration owned by other organization
    )


def test_cannot_retrieve_unrelated_route_details_as_org_admin(
        api_client, org_admin_user, organization, other_organization, integrations_list, route_1, route_2
):
    _test_cannot_retrieve_unrelated_route_details(
        api_client=api_client,
        user=org_admin_user,
        route=route_2  # This route belongs to an integration owned by other organization
    )

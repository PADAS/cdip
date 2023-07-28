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
    if "configuration" in data:
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
            "configuration": str(route_2.configuration.id),  # Reuse config from other route
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
            "configuration": str(route_2.configuration.id),  # Reuse config from other route
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
            "configuration": str(route_2.configuration.id),  # Reuse config from other route
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
    providers_ids = sorted([p["id"] for p in response_data.get("data_providers", [])])
    expected_providers_ids = sorted([str(p.id) for p in route.data_providers.all()])
    assert providers_ids == expected_providers_ids
    destinations_ids = sorted([p["id"] for p in response_data.get("destinations", [])])
    expected_destinations_ids = sorted([str(d.id) for d in route.destinations.all()])
    assert destinations_ids == expected_destinations_ids
    assert "configuration" in response_data
    if route.configuration:
        response_config = response_data.get("configuration")
        assert response_config is not None
        assert response_config.get("id") == str(route.configuration.id)
        assert response_config.get("name") == route.configuration.name
        assert response_config.get("data") == route.configuration.data
    else:
        assert not response_data.get("configuration")
    assert response_data.get("additional") == route.additional


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


def _test_partial_update_route(api_client, user, route, new_data):
    api_client.force_authenticate(user)
    response = api_client.patch(
        reverse("routes-detail",  kwargs={"pk": route.id}),
        data=new_data,
        format="json"
    )
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    # Check that the data was updated in teh database
    route.refresh_from_db()
    assert response_data.get("id") == str(route.id)
    if "name" in new_data:
        assert new_data.get("name") == route.name
    if "owner" in new_data:
        assert new_data.get("owner") == str(route.owner.id)
    if "data_providers" in new_data:
        expected_providers_ids = sorted(new_data.get("data_providers", []))
        providers_ids = sorted([str(p.id) for p in route.data_providers.all()])
        assert providers_ids == expected_providers_ids
    if "destinations" in new_data:
        destinations_ids = sorted(new_data.get("destinations", []))
        expected_destinations_ids = sorted([str(d.id) for d in route.destinations.all()])
        assert destinations_ids == expected_destinations_ids
    if "configuration" in new_data:
        new_config = new_data.get("configuration")
        assert new_config == str(route.configuration.id)
    if "additional" in new_data:
        assert new_data.get("additional") == route.additional


def _test_full_update_route(api_client, user, route, new_data):
    api_client.force_authenticate(user)
    response = api_client.put(
        reverse("routes-detail",  kwargs={"pk": route.id}),
        data=new_data,
        format="json"
    )
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    # Check that the data was updated in teh database
    route.refresh_from_db()
    assert response_data.get("id") == str(route.id)
    assert new_data.get("name") == route.name
    assert new_data.get("owner") == str(route.owner.id)
    expected_providers_ids = sorted(new_data.get("data_providers", []))
    providers_ids = sorted([str(p.id) for p in route.data_providers.all()])
    assert providers_ids == expected_providers_ids
    destinations_ids = sorted(new_data.get("destinations", []))
    expected_destinations_ids = sorted([str(d.id) for d in route.destinations.all()])
    assert destinations_ids == expected_destinations_ids
    new_config = new_data.get("configuration")
    assert new_config == str(route.configuration.id)
    assert new_data.get("additional") == route.additional


def test_full_update_route_as_superuser(
        api_client, superuser, organization, other_organization, integrations_list,
        provider_lotek_panthera, provider_movebank_ewt, route_1, route_2, smart_integration, smart_route_configuration
):
    _test_full_update_route(
        api_client=api_client,
        user=superuser,
        route=route_1,
        new_data={
            "name": "Move Bank to SMART",
            "owner": str(other_organization.id),
            "data_providers": [
                str(provider_movebank_ewt.id)
            ],
            "destinations": [
                str(smart_integration.id)
            ],
            "configuration": str(smart_route_configuration.id),
            "additional": {
                "extra": "ABC1234"
            }
        }
    )


def test_partial_update_route_as_superuser(
        api_client, superuser, organization, other_organization, integrations_list,
        provider_lotek_panthera, provider_movebank_ewt, route_1, route_2
):
    _test_partial_update_route(
        api_client=api_client,
        user=superuser,
        route=route_1,
        new_data={
            "name": "New Rule Name"
        }
    )


def test_update_route_configuration_as_org_admin(
        api_client, org_admin_user, organization, other_organization, integrations_list,
        provider_lotek_panthera, provider_movebank_ewt, route_1, route_2, er_route_configuration_rangers
):
    _test_partial_update_route(
        api_client=api_client,
        user=org_admin_user,
        route=route_1,
        new_data={  # Set another pre-existent configuration
            "configuration": str(er_route_configuration_rangers.id)
        }
    )


def test_add_destination_in_default_route_as_superuser(
        api_client, superuser, organization, other_organization, integrations_list,
        provider_lotek_panthera, provider_movebank_ewt, route_1, route_2
):
    default_route = provider_lotek_panthera.default_route
    current_destinations = [str(d.id) for d in default_route.destinations.all()]
    _test_partial_update_route(
        api_client=api_client,
        user=superuser,
        route=default_route,
        new_data={  # Add one destination
            "destinations": [*current_destinations, str(integrations_list[1].id)]
        }
    )


def test_add_destination_in_route_as_org_admin(
        api_client, org_admin_user_2, organization, other_organization, integrations_list,
        provider_lotek_panthera, provider_movebank_ewt, route_1, route_2, smart_integration
):
    current_destinations = [str(d.id) for d in route_2.destinations.all()]
    _test_partial_update_route(
        api_client=api_client,
        user=org_admin_user_2,
        route=route_2,
        new_data={  # Add one destination
            "destinations": [*current_destinations, str(smart_integration.id)]
        }
    )


def test_cannot_add_destination_in_route_as_org_viewer(
        api_client, org_viewer_user_2, organization, other_organization, integrations_list,
        provider_lotek_panthera, provider_movebank_ewt, route_1, route_2, smart_integration
):
    current_destinations = [str(d.id) for d in route_2.destinations.all()]
    api_client.force_authenticate(org_viewer_user_2)
    response = api_client.patch(
        reverse("routes-detail", kwargs={"pk": route_2.id}),
        data={  # Add one destination
            "destinations": [*current_destinations, str(smart_integration.id)]
        }
    )
    # Viewers cannot do write operations
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_cannot_add_destination_in_unrelated_route_as_org_admin(
        api_client, org_admin_user, organization, other_organization, integrations_list,
        provider_lotek_panthera, provider_movebank_ewt, route_1, route_2, smart_integration
):
    current_destinations = [str(d.id) for d in route_2.destinations.all()]
    api_client.force_authenticate(org_admin_user)
    response = api_client.patch(
        reverse("routes-detail", kwargs={"pk": route_2.id}),  # Route 2 is owned by other organization
        data={  # Add one destination
            "destinations": [*current_destinations, str(smart_integration.id)]
        }
    )
    # Org admin cannot edit routes owned by other organization
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_cannot_add_unrelated_destination_in_route_as_org_admin(
        api_client, org_admin_user, organization, other_organization, integrations_list,
        provider_lotek_panthera, provider_movebank_ewt, route_1, route_2, smart_integration
):
    current_destinations = [str(d.id) for d in route_1.destinations.all()]
    api_client.force_authenticate(org_admin_user)
    response = api_client.patch(
        reverse("routes-detail", kwargs={"pk": route_1.id}),
        data={  # smart_integration is owned by another organization that this user have no access
            "destinations": [*current_destinations, str(smart_integration.id)]
        }
    )
    # Org admin cannot add destinations owned by other unrelated organizations
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_cannot_change_route_owner_to_unrelated_org_as_org_admin(
        api_client, org_admin_user, organization, other_organization, integrations_list,
        provider_lotek_panthera, provider_movebank_ewt, route_1, route_2, smart_integration
):
    api_client.force_authenticate(org_admin_user)
    response = api_client.patch(
        reverse("routes-detail", kwargs={"pk": route_1.id}),
        data={  # org_admin_user isn't an admin in other_organization
            "owner": str(other_organization)
        }
    )
    # Org admin cannot add destinations owned by other unrelated organizations
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_update_data_provider_in_route_as_superuser(
        api_client, superuser, organization, other_organization, integrations_list,
        provider_lotek_panthera, provider_movebank_ewt, route_1, route_2
):
    default_route = provider_lotek_panthera.default_route
    _test_partial_update_route(
        api_client=api_client,
        user=superuser,
        route=default_route,
        new_data={  # Change the data provider
            "data_providers": [str(provider_movebank_ewt.id)]
        }
    )


def test_update_data_provider_in_route_as_org_admin(
        api_client, org_admin_user, organization, other_organization, integrations_list,
        provider_lotek_panthera, provider_movebank_ewt, route_1, route_2
):
    _test_partial_update_route(
        api_client=api_client,
        user=org_admin_user,
        route=route_1,
        new_data={  # Change the data provider
            "data_providers": [str(integrations_list[2].id)]
        }
    )


def test_cannot_update_data_provider_in_route_as_org_viewer(
        api_client, org_viewer_user_2, organization, other_organization, integrations_list,
        provider_lotek_panthera, provider_movebank_ewt, route_1, route_2, smart_integration
):
    api_client.force_authenticate(org_viewer_user_2)
    response = api_client.patch(
        reverse("routes-detail", kwargs={"pk": route_2.id}),
        data={  # Change the data provider
            "data_providers": [str(integrations_list[7].id)]
        }
    )
    # Viewers cannot do write operations
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_cannot_add_unrelated_provider_in_route_as_org_admin(
        api_client, org_admin_user, organization, other_organization, integrations_list,
        provider_lotek_panthera, provider_movebank_ewt, route_1, route_2, smart_integration
):
    api_client.force_authenticate(org_admin_user)
    response = api_client.patch(
        reverse("routes-detail", kwargs={"pk": route_1.id}),
        data={  # provider_movebank_ewt is owned by another organization that this user have no access
            "data_providers": [str(provider_movebank_ewt.id)]
        }
    )
    # Org admin cannot add destinations owned by other unrelated organizations
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def _test_delete_route(api_client, user, route):
    api_client.force_authenticate(user)
    response = api_client.delete(
        reverse("routes-detail",  kwargs={"pk": route.id}),
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT


def _test_cannot_delete_route(api_client, user, route):
    api_client.force_authenticate(user)
    response = api_client.delete(
        reverse("routes-detail",  kwargs={"pk": route.id}),
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_delete_route_as_superuser(
        api_client, superuser, organization, other_organization, integrations_list, route_1, route_2
):
    _test_delete_route(
        api_client=api_client,
        user=superuser,
        route=route_2
    )


def test_delete_route_as_org_admin(
        api_client, org_admin_user, organization, other_organization, integrations_list, route_1, route_2
):
    _test_delete_route(
        api_client=api_client,
        user=org_admin_user,
        route=route_1
    )


def test_cannot_delete_route_as_org_viewer(
        api_client, org_viewer_user_2, organization, other_organization, integrations_list, route_1, route_2
):
    _test_cannot_delete_route(
        api_client=api_client,
        user=org_viewer_user_2,
        route=route_2
    )


def test_cannot_delete_unrelated_route_as_org_admin(
        api_client, org_admin_user, organization, other_organization, integrations_list, route_1, route_2
):
    _test_cannot_delete_route(
        api_client=api_client,
        user=org_admin_user,
        route=route_2  # Route 2 belongs to other organization where this use doesn't have access
    )


def _test_filter_routes(api_client, user, filters, expected_routes):
    api_client.force_authenticate(user)
    response = api_client.get(
        reverse("routes-list"),
        data=filters
    )
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    routes = response_data["results"]
    # Check that the returned integrations are the expected ones
    expected_route_ids = [str(t.id) for t in expected_routes]
    assert len(routes) == len(expected_route_ids)
    for route in routes:
        assert route.get("id") in expected_route_ids
        assert "name" in route
        assert "owner" in route
        assert "data_providers" in route
        assert "destinations" in route
        assert "configuration" in route
        assert "additional" in route


def test_filter_routes_by_provider_as_superuser(
        api_client, superuser, organization, other_organization,
        integrations_list, provider_movebank_ewt, provider_lotek_panthera,
        route_1, route_2
):
    _test_filter_routes(
        api_client=api_client,
        user=superuser,
        filters={  # Routes having Movebank as provider
            "provider": str(provider_movebank_ewt.id)
        },
        expected_routes=[provider_movebank_ewt.default_route, route_2]
    )


def test_filter_routes_by_destination_as_superuser(
        api_client, superuser, organization, other_organization,
        integrations_list, provider_movebank_ewt, provider_lotek_panthera,
        route_1, route_2
):
    selected_destination = integrations_list[6]
    _test_filter_routes(
        api_client=api_client,
        user=superuser,
        filters={
            "destination": str(selected_destination.id)
        },
        expected_routes=[route_1]
    )


def test_filter_routes_by_destination_url_as_superuser(
        api_client, superuser, organization, other_organization,
        integrations_list, provider_movebank_ewt, provider_lotek_panthera,
        route_1, route_2
):
    selected_destination = integrations_list[5]
    _test_filter_routes(
        api_client=api_client,
        user=superuser,
        filters={
            "destination_url": str(selected_destination.base_url)
        },
        expected_routes=[route_1, route_2]
    )


def test_filter_routes_by_destination_url_as_org_admin(
        api_client, org_admin_user_2, organization, other_organization,
        integrations_list, provider_movebank_ewt, provider_lotek_panthera,
        route_1, route_2
):
    selected_destination = integrations_list[5]
    _test_filter_routes(
        api_client=api_client,
        user=org_admin_user_2,
        filters={
            "provider": str(provider_movebank_ewt.id),
            "destination_url__in": str(selected_destination.base_url)
        },
        expected_routes=[route_2]
    )


def test_global_search_routes_by_route_name_as_superuser(
        api_client, superuser, organization, other_organization,
        integrations_list, provider_movebank_ewt, provider_lotek_panthera,
        route_1, route_2
):
    _test_filter_routes(
        api_client=api_client,
        user=superuser,
        filters={
            "search_fields": "name",
            "search": "Lotek"
        },
        expected_routes=[provider_lotek_panthera.default_route]
    )


def test_global_search_routes_by_destination_url_as_org_admin(
        api_client, org_admin_user, organization, other_organization,
        integrations_list, provider_movebank_ewt, provider_lotek_panthera,
        route_1, route_2
):
    selected_destination = route_1.destinations.last()
    _test_filter_routes(
        api_client=api_client,
        user=org_admin_user,
        filters={
            "search_fields": "destinations__base_url",
            "search": str(selected_destination.base_url)
        },
        expected_routes=[route_1]
    )

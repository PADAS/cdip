import uuid

import pytest
from django.urls import reverse
from gundi_core.schemas.v2 import StreamPrefixEnum
from rest_framework import status
from integrations.models import (
    Route, RouteConfiguration, Source, SourceFilter, get_user_routes_qs, Integration, ensure_default_route
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


def test_list_routes_as_superuser(api_client, superuser, organization, integrations_list_er):
    _test_list_routes(
        api_client=api_client,
        user=superuser,
    )


def test_list_routes_as_org_admin(api_client, org_admin_user, organization, integrations_list_er):
    _test_list_routes(
        api_client=api_client,
        user=org_admin_user,
    )


def test_list_routes_as_org_viewer(api_client, org_viewer_user, organization, integrations_list_er):
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


def test_create_route_as_superuser(api_client, superuser, organization, integrations_list_er, provider_lotek_panthera):
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
                str(i.id) for i in integrations_list_er[2:4]
            ],
            # "configuration": {},  # This should be optional
            "additional": {}
        }
    )


def test_create_route_as_org_admin(
        api_client, org_admin_user_2, organization, other_organization, integrations_list_er, provider_movebank_ewt
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
                str(integrations_list_er[5].id)
            ],
            "additional": {}
        }
    )


def test_create_route_with_configuration_as_org_admin(
        api_client, org_admin_user_2, organization, other_organization, integrations_list_er, provider_movebank_ewt
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
                str(integrations_list_er[5].id)
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
        api_client, org_admin_user_2, organization, other_organization, integrations_list_er, provider_movebank_ewt, route_2
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
                str(integrations_list_er[5].id)
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
        api_client, org_viewer_user, organization, other_organization, integrations_list_er, provider_movebank_ewt, route_2
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
                str(integrations_list_er[5].id)
            ],
            "configuration": str(route_2.configuration.id),  # Reuse config from other route
            "additional": {}
        }
    )


def test_cannot_create_route_for_other_organization_as_org_admin(
        api_client, org_admin_user, organization, other_organization, integrations_list_er, provider_movebank_ewt, route_2
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
                str(integrations_list_er[5].id)
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
        api_client, superuser, organization, other_organization, integrations_list_er, route_1, route_2
):
    _test_retrieve_route_details(
        api_client=api_client,
        user=superuser,
        route=integrations_list_er[0].default_route
    )


def test_retrieve_route_details_as_org_admin(
        api_client, org_admin_user, organization, other_organization, integrations_list_er, route_1, route_2
):
    _test_retrieve_route_details(
        api_client=api_client,
        user=org_admin_user,
        route=route_1
    )


def test_retrieve_route_details_as_org_viewer(
        api_client, org_viewer_user_2, organization, other_organization, integrations_list_er, route_1, route_2
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
        api_client, org_viewer_user_2, organization, other_organization, integrations_list_er, route_1, route_2
):
    _test_cannot_retrieve_unrelated_route_details(
        api_client=api_client,
        user=org_viewer_user_2,
        route=route_1  # This route belongs to an integration owned by other organization
    )


def test_cannot_retrieve_unrelated_route_details_as_org_admin(
        api_client, org_admin_user, organization, other_organization, integrations_list_er, route_1, route_2
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
        api_client, superuser, organization, other_organization, integrations_list_er,
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
        api_client, superuser, organization, other_organization, integrations_list_er,
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
        api_client, org_admin_user, organization, other_organization, integrations_list_er,
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
        api_client, superuser, organization, other_organization, integrations_list_er,
        provider_lotek_panthera, provider_movebank_ewt, route_1, route_2
):
    default_route = provider_lotek_panthera.default_route
    current_destinations = [str(d.id) for d in default_route.destinations.all()]
    _test_partial_update_route(
        api_client=api_client,
        user=superuser,
        route=default_route,
        new_data={  # Add one destination
            "destinations": [*current_destinations, str(integrations_list_er[1].id)]
        }
    )


def test_add_destination_in_route_as_org_admin(
        api_client, org_admin_user_2, organization, other_organization, integrations_list_er,
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
        api_client, org_viewer_user_2, organization, other_organization, integrations_list_er,
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
        api_client, org_admin_user, organization, other_organization, integrations_list_er,
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
        api_client, org_admin_user, organization, other_organization, integrations_list_er,
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
        api_client, org_admin_user, organization, other_organization, integrations_list_er,
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
        api_client, superuser, organization, other_organization, integrations_list_er,
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
        api_client, org_admin_user, organization, other_organization, integrations_list_er,
        provider_lotek_panthera, provider_movebank_ewt, route_1, route_2
):
    _test_partial_update_route(
        api_client=api_client,
        user=org_admin_user,
        route=route_1,
        new_data={  # Change the data provider
            "data_providers": [str(integrations_list_er[2].id)]
        }
    )


def test_cannot_update_data_provider_in_route_as_org_viewer(
        api_client, org_viewer_user_2, organization, other_organization, integrations_list_er,
        provider_lotek_panthera, provider_movebank_ewt, route_1, route_2, smart_integration
):
    api_client.force_authenticate(org_viewer_user_2)
    response = api_client.patch(
        reverse("routes-detail", kwargs={"pk": route_2.id}),
        data={  # Change the data provider
            "data_providers": [str(integrations_list_er[7].id)]
        }
    )
    # Viewers cannot do write operations
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_cannot_add_unrelated_provider_in_route_as_org_admin(
        api_client, org_admin_user, organization, other_organization, integrations_list_er,
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
        api_client, superuser, organization, other_organization, integrations_list_er, route_1, route_2
):
    _test_delete_route(
        api_client=api_client,
        user=superuser,
        route=route_2
    )


def test_delete_route_as_org_admin(
        api_client, org_admin_user, organization, other_organization, integrations_list_er, route_1, route_2
):
    _test_delete_route(
        api_client=api_client,
        user=org_admin_user,
        route=route_1
    )


def test_cannot_delete_route_as_org_viewer(
        api_client, org_viewer_user_2, organization, other_organization, integrations_list_er, route_1, route_2
):
    _test_cannot_delete_route(
        api_client=api_client,
        user=org_viewer_user_2,
        route=route_2
    )


def test_cannot_delete_unrelated_route_as_org_admin(
        api_client, org_admin_user, organization, other_organization, integrations_list_er, route_1, route_2
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
        integrations_list_er, provider_movebank_ewt, provider_lotek_panthera,
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
        integrations_list_er, provider_movebank_ewt, provider_lotek_panthera,
        route_1, route_2
):
    selected_destination = integrations_list_er[6]
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
        integrations_list_er, provider_movebank_ewt, provider_lotek_panthera,
        route_1, route_2
):
    selected_destination = integrations_list_er[5]
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
        integrations_list_er, provider_movebank_ewt, provider_lotek_panthera,
        route_1, route_2
):
    selected_destination = integrations_list_er[5]
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
        integrations_list_er, provider_movebank_ewt, provider_lotek_panthera,
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
        integrations_list_er, provider_movebank_ewt, provider_lotek_panthera,
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


# ---------------------------------------------------------------------------
# Field mappings — schema validation + update-in-place of RouteConfiguration
# ---------------------------------------------------------------------------
#
# ``RouteConfiguration.data["field_mappings"]`` is a 3-level nested dict:
#     { PROVIDER_UUID: { action_type: { DESTINATION_UUID: rule } } }
# where action_type is a StreamPrefixEnum value and rule has the shape of VALID_RULE
# below. These tests cover the schema validation introduced in the serializer
# and the update-in-place behavior on PATCH.


VALID_RULE = {
    "destination_field": "event_type",
    "provider_field": "event_details__species",
    "default": "animal_detected",
    "map": {"lion": "lion_sighting"},
}


def _build_field_mappings(provider_id, destination_id, *, rule=None, action_type="ev"):
    """Build a single-entry field_mappings dict for one (provider, action, destination)."""
    return {
        str(provider_id): {
            action_type: {str(destination_id): rule or dict(VALID_RULE)}
        }
    }


def _post_route_with_field_mappings(
    api_client, user, organization, provider, destination, field_mappings
):
    api_client.force_authenticate(user)
    return api_client.post(
        reverse("routes-list"),
        data={
            "name": "Field mappings test route",
            "owner": str(organization.id),
            "data_providers": [str(provider.id)],
            "destinations": [str(destination.id)],
            "configuration": {
                "name": "config",
                "data": {"field_mappings": field_mappings},
            },
            "additional": {},
        },
        format="json",
    )


# -- Happy path ------------------------------------------------------------


def test_create_route_with_valid_field_mappings(
    api_client, superuser, organization, integrations_list_er, provider_lotek_panthera
):
    destination = integrations_list_er[0]
    field_mappings = _build_field_mappings(provider_lotek_panthera.id, destination.id)

    response = _post_route_with_field_mappings(
        api_client, superuser, organization,
        provider_lotek_panthera, destination, field_mappings,
    )

    assert response.status_code == status.HTTP_201_CREATED
    route = Route.objects.get(id=response.json()["id"])
    stored_rule = (
        route.configuration.data["field_mappings"]
        [str(provider_lotek_panthera.id)]["ev"][str(destination.id)]
    )
    assert stored_rule["destination_field"] == "event_type"


@pytest.mark.parametrize(
    "action_type", [stream_type.value for stream_type in StreamPrefixEnum]
)
def test_create_route_accepts_every_stream_type_in_field_mappings(
    api_client, superuser, organization, integrations_list_er, provider_lotek_panthera,
    action_type,
):
    # GUNDI-5548: the platform routes every StreamPrefixEnum value (e.g. txt for
    # inReach text messages), so the serializer must accept them all.
    destination = integrations_list_er[0]
    field_mappings = _build_field_mappings(
        provider_lotek_panthera.id, destination.id, action_type=action_type
    )

    response = _post_route_with_field_mappings(
        api_client, superuser, organization,
        provider_lotek_panthera, destination, field_mappings,
    )

    assert response.status_code == status.HTTP_201_CREATED, response.content


def test_patch_route_resending_stored_txt_field_mappings_passes(
    api_client, superuser, route_2, provider_movebank_ewt
):
    # GUNDI-5548 repro: routes written by the InReach V1→V2 migration store txt
    # mappings alongside obv; re-saving that same configuration must not 400.
    destination = route_2.destinations.first()
    provider_id = str(provider_movebank_ewt.id)
    stored_data = {
        "field_mappings": {
            provider_id: {
                "obv": {str(destination.id): dict(VALID_RULE)},
                "txt": {str(destination.id): dict(VALID_RULE)},
            }
        }
    }
    config = route_2.configuration
    config.data = stored_data
    config.save()

    api_client.force_authenticate(superuser)
    response = api_client.patch(
        reverse("routes-detail", kwargs={"pk": route_2.id}),
        data={"configuration": {"name": config.name, "data": stored_data}},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK, response.content


# -- Schema validation -----------------------------------------------------


def _fm_with_invalid_action_type(provider_id, destination_id):
    return {str(provider_id): {"xx": {str(destination_id): VALID_RULE}}}


def _fm_missing_destination_field(provider_id, destination_id):
    return {str(provider_id): {"ev": {str(destination_id): {
        "provider_field": "x",
        "map": {"a": "b"},
    }}}}


def _fm_map_without_provider_field(provider_id, destination_id):
    return {str(provider_id): {"ev": {str(destination_id): {
        "destination_field": "event_type",
        "map": {"a": "b"},
    }}}}


def _fm_missing_default_and_map(provider_id, destination_id):
    return {str(provider_id): {"ev": {str(destination_id): {
        "destination_field": "event_type",
    }}}}


def _fm_with_non_uuid_provider_key(provider_id, destination_id):
    return {"not-a-uuid": {"ev": {str(destination_id): VALID_RULE}}}


INVALID_FIELD_MAPPING_CASES = [
    pytest.param(_fm_with_invalid_action_type, "xx", id="invalid-action-type"),
    pytest.param(_fm_missing_destination_field, "destination_field", id="missing-destination-field"),
    pytest.param(_fm_map_without_provider_field, "provider_field", id="map-without-provider-field"),
    pytest.param(_fm_missing_default_and_map, "default", id="missing-default-and-map"),
    pytest.param(_fm_with_non_uuid_provider_key, "not-a-uuid", id="provider-key-not-uuid"),
]


@pytest.mark.parametrize("build_field_mappings, error_fragment", INVALID_FIELD_MAPPING_CASES)
def test_create_route_rejects_invalid_field_mappings(
    api_client,
    superuser,
    organization,
    integrations_list_er,
    provider_lotek_panthera,
    build_field_mappings,
    error_fragment,
):
    destination = integrations_list_er[0]
    field_mappings = build_field_mappings(provider_lotek_panthera.id, destination.id)

    response = _post_route_with_field_mappings(
        api_client, superuser, organization,
        provider_lotek_panthera, destination, field_mappings,
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert error_fragment in response.content.decode()


def test_create_route_rejects_unknown_integration_uuid(
    api_client, superuser, organization, integrations_list_er, provider_lotek_panthera
):
    destination = integrations_list_er[0]
    unknown_destination_id = uuid.uuid4()
    field_mappings = _build_field_mappings(provider_lotek_panthera.id, unknown_destination_id)

    response = _post_route_with_field_mappings(
        api_client, superuser, organization,
        provider_lotek_panthera, destination, field_mappings,
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "unknown Integration" in response.content.decode()


# -- Route-context cross-check --------------------------------------------


def test_create_route_rejects_provider_not_in_data_providers(
    api_client,
    superuser,
    organization,
    integrations_list_er,
    provider_lotek_panthera,
    provider_movebank_ewt,
):
    # provider_movebank_ewt is a valid Integration but isn't attached to this route
    destination = integrations_list_er[0]
    field_mappings = _build_field_mappings(provider_movebank_ewt.id, destination.id)

    response = _post_route_with_field_mappings(
        api_client, superuser, organization,
        provider_lotek_panthera, destination, field_mappings,
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "data_providers" in response.content.decode()


# -- Update-in-place of the RouteConfiguration row -------------------------


def test_patch_route_updates_existing_configuration_in_place(
    api_client, superuser, route_2, provider_movebank_ewt
):
    # route_2 already has er_route_configuration_elephants attached — we expect
    # the PATCH to update that same row in place instead of creating a new one.
    original_config_id = route_2.configuration.id
    destination = route_2.destinations.first()
    new_configuration = {
        "name": route_2.configuration.name,
        "data": {
            "subject_type": "elephant",
            "field_mappings": _build_field_mappings(
                provider_movebank_ewt.id, destination.id
            ),
        },
    }

    api_client.force_authenticate(superuser)
    response = api_client.patch(
        reverse("routes-detail", kwargs={"pk": route_2.id}),
        data={"configuration": new_configuration},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK, response.content
    route_2.refresh_from_db()
    assert route_2.configuration.id == original_config_id, (
        "expected the existing RouteConfiguration row to be updated in place"
    )
    assert "field_mappings" in route_2.configuration.data
    assert RouteConfiguration.objects.filter(id=original_config_id).count() == 1


def test_patch_route_configuration_without_field_mappings_passes(
    api_client, superuser, route_2
):
    # data without field_mappings: the schema validator must not run
    api_client.force_authenticate(superuser)
    response = api_client.patch(
        reverse("routes-detail", kwargs={"pk": route_2.id}),
        data={
            "configuration": {
                "name": "still elephants",
                "data": {"subject_type": "elephant"},
            }
        },
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK, response.content


# ---------------------------------------------------------------------------
# DELETE /v2/routes/{id}/configuration/ — unlink + hard-delete the config row
# ---------------------------------------------------------------------------
#
# Mirrors the Django admin's "delete row" behavior for a RouteConfiguration but
# is safe when the same configuration is shared between routes: in that case
# the row is only detached from the current route, never destroyed.


def test_delete_route_configuration_as_superuser_removes_the_row(
    api_client, superuser, route_2
):
    config_id = route_2.configuration.id

    api_client.force_authenticate(superuser)
    response = api_client.delete(
        reverse("routes-delete-configuration", kwargs={"pk": route_2.id})
    )

    assert response.status_code == status.HTTP_204_NO_CONTENT
    route_2.refresh_from_db()
    assert route_2.configuration is None
    assert not RouteConfiguration.objects.filter(id=config_id).exists()


def test_delete_route_configuration_as_org_admin_removes_the_row(
    api_client, org_admin_user_2, route_2
):
    config_id = route_2.configuration.id

    api_client.force_authenticate(org_admin_user_2)
    response = api_client.delete(
        reverse("routes-delete-configuration", kwargs={"pk": route_2.id})
    )

    assert response.status_code == status.HTTP_204_NO_CONTENT
    route_2.refresh_from_db()
    assert route_2.configuration is None
    assert not RouteConfiguration.objects.filter(id=config_id).exists()


def test_delete_route_configuration_keeps_row_when_shared_with_another_route(
    api_client, superuser, route_1, route_2
):
    # Share the same RouteConfiguration between route_1 and route_2
    shared_config = route_2.configuration
    route_1.configuration = shared_config
    route_1.save()

    api_client.force_authenticate(superuser)
    response = api_client.delete(
        reverse("routes-delete-configuration", kwargs={"pk": route_2.id})
    )

    assert response.status_code == status.HTTP_204_NO_CONTENT
    route_2.refresh_from_db()
    route_1.refresh_from_db()
    assert route_2.configuration is None
    # The row still exists because route_1 keeps referencing it
    assert RouteConfiguration.objects.filter(id=shared_config.id).exists()
    assert route_1.configuration_id == shared_config.id


def test_delete_route_configuration_is_idempotent_when_already_empty(
    api_client, superuser, route_1
):
    assert route_1.configuration is None  # sanity

    api_client.force_authenticate(superuser)
    response = api_client.delete(
        reverse("routes-delete-configuration", kwargs={"pk": route_1.id})
    )

    assert response.status_code == status.HTTP_204_NO_CONTENT


def test_cannot_delete_route_configuration_as_org_viewer(
    api_client, org_viewer_user_2, route_2
):
    api_client.force_authenticate(org_viewer_user_2)
    response = api_client.delete(
        reverse("routes-delete-configuration", kwargs={"pk": route_2.id})
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    # The configuration is still attached to the route
    route_2.refresh_from_db()
    assert route_2.configuration is not None


def test_cannot_delete_unrelated_route_configuration_as_org_admin(
    api_client, org_admin_user, route_2
):
    # org_admin_user belongs to `organization`, not to `other_organization` (which owns route_2)
    api_client.force_authenticate(org_admin_user)
    response = api_client.delete(
        reverse("routes-delete-configuration", kwargs={"pk": route_2.id})
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    route_2.refresh_from_db()
    assert route_2.configuration is not None


# ---- The filters block cdip-routing reads (GUNDI-5178) --------------------


def test_route_detail_carries_the_filters_block(
        api_client, superuser, organization, route_1, lotek_sources, provider_lotek_panthera
):
    api_client.force_authenticate(superuser)
    response = api_client.get(reverse("routes-detail", kwargs={"pk": route_1.id}))

    assert response.status_code == status.HTTP_200_OK, response.content
    source_filter = route_1.source_filters.get()
    filters = response.json()["filters"]

    rule = filters[str(source_filter.destination_id)]
    assert rule["mode"] == "whitelist"
    assert rule["type"] == "list"
    assert rule["enabled"] is True
    assert set(rule["by_provider"][str(provider_lotek_panthera.id)]) == {
        s.external_id for s in lotek_sources
    }


def test_route_list_does_not_carry_the_filters_block(
        api_client, superuser, organization, route_1, lotek_sources
):
    # A page of routes would multiply every filter's device list for a view that never
    # needs it; only the detail view pays that cost.
    api_client.force_authenticate(superuser)
    response = api_client.get(reverse("routes-list"))

    assert response.status_code == status.HTTP_200_OK, response.content
    assert all("filters" not in route for route in response.json()["results"])


def test_route_without_filters_reports_an_empty_block(
        api_client, superuser, organization, route_1
):
    route_1.source_filters.all().delete()
    api_client.force_authenticate(superuser)
    response = api_client.get(reverse("routes-detail", kwargs={"pk": route_1.id}))

    assert response.status_code == status.HTTP_200_OK, response.content
    assert response.json()["filters"] == {}


def test_filters_block_groups_identical_external_ids_by_provider(
        api_client, superuser, organization, route_1, integrations_list_er,
        lotek_sources, provider_lotek_panthera
):
    # The reason for the grouping: external_id is unique per provider, not globally. Two
    # providers may each own a device called the same thing, and a flat list would let the
    # wrong one satisfy the rule.
    second_provider = integrations_list_er[2]
    route_1.data_providers.add(second_provider)
    borrowed = Source.objects.create(
        integration=second_provider, external_id=lotek_sources[0].external_id
    )
    source_filter = route_1.source_filters.get()
    source_filter.sources.add(borrowed)

    api_client.force_authenticate(superuser)
    response = api_client.get(reverse("routes-detail", kwargs={"pk": route_1.id}))

    by_provider = response.json()["filters"][str(source_filter.destination_id)]["by_provider"]
    assert by_provider[str(second_provider.id)] == [borrowed.external_id]
    assert borrowed.external_id in by_provider[str(provider_lotek_panthera.id)]
    # Same string under two providers, kept apart.
    assert str(second_provider.id) != str(provider_lotek_panthera.id)


def test_disabled_filter_still_travels_with_its_flag(
        api_client, superuser, organization, route_1
):
    # Routing honours `enabled` rather than the rule being absent, so the operator can
    # switch a rule off without losing the device list.
    source_filter = route_1.source_filters.get()
    source_filter.enabled = False
    source_filter.save()

    api_client.force_authenticate(superuser)
    response = api_client.get(reverse("routes-detail", kwargs={"pk": route_1.id}))

    rule = response.json()["filters"][str(source_filter.destination_id)]
    assert rule["enabled"] is False


def test_filters_block_is_scoped_to_the_route(
        api_client, superuser, organization, other_organization, route_1, route_2
):
    api_client.force_authenticate(superuser)
    response = api_client.get(reverse("routes-detail", kwargs={"pk": route_1.id}))

    filters = response.json()["filters"]
    other_destination = str(route_2.source_filters.get().destination_id)
    assert other_destination not in filters


def test_filters_block_omits_types_it_cannot_carry(
        api_client, superuser, organization, route_1, lotek_sources, provider_lotek_panthera
):
    # The block is keyed by destination, so two filters on one arrow would collapse into a
    # single entry and the list rule, the one routing enforces, could lose. A non-list
    # filter describes its selection in `selector`, which this block does not carry, so it
    # is left out instead of overwriting its neighbour.
    list_filter = route_1.source_filters.get()
    SourceFilter.objects.create(
        type=SourceFilter.SourceFilterTypes.GEO_BOUNDARY,
        mode=SourceFilter.FilterModes.WHITELIST,
        routing_rule=route_1,
        destination=list_filter.destination,
        selector={"polygon": []},
        # Ordered after the list rule, which is the case that used to overwrite it:
        # Meta.ordering decides which of the two reaches the destination key last.
        order_number=list_filter.order_number + 1,
    )

    api_client.force_authenticate(superuser)
    response = api_client.get(reverse("routes-detail", kwargs={"pk": route_1.id}))

    assert response.status_code == status.HTTP_200_OK, response.content
    rule = response.json()["filters"][str(list_filter.destination_id)]
    assert rule["type"] == "list"
    assert set(rule["by_provider"][str(provider_lotek_panthera.id)]) == {
        s.external_id for s in lotek_sources
    }


def test_filters_block_omits_a_destination_no_longer_on_the_route(
        api_client, superuser, organization, route_1
):
    # Route update prunes these, but a removal that bypasses the API leaves the filter
    # pointing at an Integration that still exists, so the cascade never fires. Routing must
    # not be handed a rule for an arrow the route no longer has.
    source_filter = route_1.source_filters.get()
    route_1.destinations.remove(source_filter.destination)

    api_client.force_authenticate(superuser)
    response = api_client.get(reverse("routes-detail", kwargs={"pk": route_1.id}))

    assert response.status_code == status.HTTP_200_OK, response.content
    assert str(source_filter.destination_id) not in response.json()["filters"]


# --- GUNDI-5731: POST /v2/routes/ must maintain Integration.default_route -----

def _post_route(api_client, user, owner, providers, destinations, name="Route"):
    api_client.force_authenticate(user)
    response = api_client.post(
        reverse("routes-list"),
        data={
            "name": name,
            "owner": str(owner.id),
            "data_providers": [str(p.id) for p in providers],
            "destinations": [str(d.id) for d in destinations],
            "additional": {},
        },
        format="json",
    )
    assert response.status_code == status.HTTP_201_CREATED, response.content
    return Route.objects.get(id=response.json()["id"])


def test_create_route_sets_default_for_provider_without_one(
    api_client, superuser, organization, integration_type_lotek, integrations_list_er
):
    """GUNDI-5731 scenario 1: a connection created without a default route,
    then 'Create Route' with a destination → that route becomes the default."""
    provider = Integration.objects.create(
        type=integration_type_lotek, owner=organization,
        name="Lotek without default", base_url="https://api.test.lotek.com",
    )
    assert provider.default_route is None

    route = _post_route(api_client, superuser, organization, [provider], [integrations_list_er[0]])

    provider.refresh_from_db()
    assert provider.default_route == route


def test_create_route_switches_empty_placeholder_default_to_new_route(
    api_client, superuser, organization, integration_type_lotek, integrations_list_er
):
    """GUNDI-5731 scenario 2 (spec §2.3): connection created WITH an empty
    default route, then 'Create Route + destination' → the default must move to
    the route carrying the destinations, not stay on the empty one."""
    provider = Integration.objects.create(
        type=integration_type_lotek, owner=organization,
        name="Lotek with placeholder", base_url="https://api.test.lotek.com",
    )
    ensure_default_route(integration=provider)
    placeholder = provider.default_route
    assert not placeholder.destinations.exists()

    route = _post_route(api_client, superuser, organization, [provider], [integrations_list_er[0]])

    provider.refresh_from_db()
    assert provider.default_route == route
    assert Route.objects.filter(pk=placeholder.pk).exists()  # the placeholder is left alone


def test_create_reverse_flow_route_sets_default_for_destination_site(
    api_client, superuser, organization, integration_type_er, provider_lotek_panthera
):
    """GUNDI-5731 entry point 2 (handleEnableReverseFlow): an ER site that so far
    was destination-only becomes a provider on a new route → that route is its default."""
    er_site = Integration.objects.create(
        type=integration_type_er, owner=organization,
        name="ER site enabling reverse flow", base_url="https://reverse.pamdas.org",
    )
    assert er_site.default_route is None

    route = _post_route(api_client, superuser, organization, [er_site], [provider_lotek_panthera], name="Reverse")

    er_site.refresh_from_db()
    assert er_site.default_route == route


# --- refusals surface as 409 --------------------------------------------------

@pytest.fixture
def ambiguous_provider(organization, integration_type_lotek, integrations_list_er):
    """default=R1, also on R2 and R3, all delivering. Deleting R1 or removing
    the provider from it has two candidates → refused."""
    from integrations.models import RouteProvider, RouteDestination
    provider = Integration.objects.create(
        type=integration_type_lotek, owner=organization, name="Ambiguous", base_url="https://api.test.lotek.com",
    )
    routes = []
    for name in ("R1", "R2", "R3"):
        route = Route.objects.create(owner=organization, name=name)
        RouteProvider.objects.bulk_create([RouteProvider(integration=provider, route=route)])
        RouteDestination.objects.bulk_create([RouteDestination(integration=integrations_list_er[0], route=route)])
        routes.append(route)
    Integration.objects.filter(pk=provider.pk).update(default_route=routes[0])
    provider.refresh_from_db()
    return provider, routes


def test_delete_route_with_ambiguous_default_returns_409_with_candidates(api_client, superuser, ambiguous_provider):
    provider, (r1, r2, r3) = ambiguous_provider
    api_client.force_authenticate(superuser)

    response = api_client.delete(reverse("routes-detail", kwargs={"pk": r1.id}))

    assert response.status_code == status.HTTP_409_CONFLICT
    body = response.json()
    assert "Cannot choose a default route" in body["detail"]
    assert {c["id"] for c in body["candidates"]} == {str(r2.id), str(r3.id)}
    assert all(set(c) == {"id", "name"} for c in body["candidates"])
    assert Route.objects.filter(pk=r1.pk).exists()
    provider.refresh_from_db()
    assert provider.default_route == r1


def test_patch_route_removing_provider_with_ambiguous_default_returns_409(api_client, superuser, ambiguous_provider):
    provider, (r1, r2, r3) = ambiguous_provider
    api_client.force_authenticate(superuser)

    response = api_client.patch(
        reverse("routes-detail", kwargs={"pk": r1.id}),
        data={"name": "renamed", "data_providers": []},
        format="json",
    )

    assert response.status_code == status.HTTP_409_CONFLICT
    r1.refresh_from_db()
    assert r1.name == "R1"                       # the whole update rolled back
    assert r1.data_providers.filter(pk=provider.pk).exists()


def test_create_route_refused_as_ambiguous_leaves_no_orphan_route(api_client, superuser, organization, integration_type_lotek, integrations_list_er):
    """Empty placeholder default + two delivering routes: joining a new empty route is ambiguous → 409, and the new Route must not survive."""
    from integrations.models import RouteProvider, RouteDestination
    provider = Integration.objects.create(type=integration_type_lotek, owner=organization, name="Placeholder default", base_url="https://api.test.lotek.com")
    placeholder = Route.objects.create(owner=organization, name="Placeholder")
    RouteProvider.objects.bulk_create([RouteProvider(integration=provider, route=placeholder)])
    for name in ("R1", "R2"):
        r = Route.objects.create(owner=organization, name=name)
        RouteProvider.objects.bulk_create([RouteProvider(integration=provider, route=r)])
        RouteDestination.objects.bulk_create([RouteDestination(integration=integrations_list_er[0], route=r)])
    Integration.objects.filter(pk=provider.pk).update(default_route=placeholder)
    routes_before = Route.objects.count()
    api_client.force_authenticate(superuser)

    response = api_client.post(
        reverse("routes-list"),
        data={"name": "New empty", "owner": str(organization.id), "data_providers": [str(provider.id)], "destinations": [], "additional": {}},
        format="json",
    )

    assert response.status_code == status.HTTP_409_CONFLICT
    assert Route.objects.count() == routes_before


def test_delete_route_with_one_other_route_reassigns_and_succeeds(api_client, superuser, organization, integration_type_lotek, integrations_list_er):
    from integrations.models import RouteProvider, RouteDestination
    provider = Integration.objects.create(
        type=integration_type_lotek, owner=organization, name="Two routes", base_url="https://api.test.lotek.com",
    )
    r1, r2 = (Route.objects.create(owner=organization, name=n) for n in ("R1", "R2"))
    RouteProvider.objects.bulk_create([RouteProvider(integration=provider, route=r) for r in (r1, r2)])
    RouteDestination.objects.bulk_create([RouteDestination(integration=integrations_list_er[0], route=r) for r in (r1, r2)])
    Integration.objects.filter(pk=provider.pk).update(default_route=r1)
    api_client.force_authenticate(superuser)

    response = api_client.delete(reverse("routes-detail", kwargs={"pk": r1.id}))

    assert response.status_code == status.HTTP_204_NO_CONTENT
    provider.refresh_from_db()
    assert provider.default_route == r2

import pytest
from django.urls import reverse
from rest_framework import status


pytestmark = pytest.mark.django_db


def _test_list_connections(api_client, user, provider_list):
    api_client.force_authenticate(user)
    response = api_client.get(
        reverse("connections-list"),
    )
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    connections = response_data["results"]
    assert len(connections) == len(provider_list)
    sorted_providers = sorted(provider_list, key=lambda p: str(p.id))
    sorted_connections = sorted(connections, key=lambda c: c["provider"]["id"])
    for provider, connection in zip(sorted_providers, sorted_connections):
        # Check the provider
        assert "provider" in connection
        connection_provider = connection["provider"]
        assert str(provider.id) == connection_provider.get("id")
        assert str(provider.name) == connection_provider.get("name")
        assert "owner" in connection_provider
        provider_owner = connection_provider.get("owner")
        assert "id" in provider_owner
        assert "name" in provider_owner
        assert "type" in connection_provider
        provider_type = connection_provider.get("type")
        assert "id" in provider_type
        assert "name" in provider_type
        assert "value" in provider_type
        # Check destinations
        assert "destinations" in connection
        expected_destination_ids = [str(dest_id) for dest_id in provider.destinations.values_list("id", flat=True)]
        for destination in connection["destinations"]:
            assert destination.get("id") in expected_destination_ids
            assert "name" in destination
            assert "owner" in destination
            destination_owner = destination.get("owner")
            assert "id" in destination_owner
            assert "name" in destination_owner
        # Check routing rules
        assert "routing_rules" in connection
        expected_routing_rules_ids = [str(rule_id) for rule_id in provider.routing_rules.values_list("id", flat=True)]
        for rule in connection["routing_rules"]:
            assert rule.get("id") in expected_routing_rules_ids
            assert "name" in rule
        # Check owner
        assert "owner" in connection
        assert str(provider.owner.id) == connection["owner"].get("id")
        assert provider.owner.name == connection["owner"].get("name")
        assert provider.owner.description == connection["owner"].get("description")


def test_list_connections_as_superuser(api_client, superuser, organization, provider_lotek_panthera, provider_movebank_ewt, integrations_list,
                                       route_1,
                                       route_2):
    _test_list_connections(
        api_client=api_client,
        user=superuser,
        # The superuser can see all the connections
        provider_list=integrations_list + [provider_lotek_panthera, provider_movebank_ewt]
    )


def test_list_connections_as_org_admin(api_client, org_admin_user, organization, provider_lotek_panthera, provider_movebank_ewt, integrations_list,
                                       route_1,
                                       route_2):
    _test_list_connections(
        api_client=api_client,
        user=org_admin_user,  # Belongs to one organization
        # Org admins can only see providers of their organizations
        provider_list=integrations_list[:5] + [provider_lotek_panthera]
    )


def test_list_connections_as_org_admin_2(api_client, org_admin_user_2, organization, provider_lotek_panthera, provider_movebank_ewt, integrations_list,
                                         route_1,
                                         route_2):
    _test_list_connections(
        api_client=api_client,
        user=org_admin_user_2,  # Belongs to one organization
        # Org admins can only see providers of their organizations
        provider_list=integrations_list[5:]+ [provider_movebank_ewt]
    )


def test_list_connections_as_org_viewer(api_client, org_viewer_user, organization, provider_lotek_panthera, provider_movebank_ewt, integrations_list,
                                        route_1,
                                        route_2):
    _test_list_connections(
        api_client=api_client,
        user=org_viewer_user,  # Belongs to one organization
        # Org viewer can only see providers of their organizations
        provider_list=integrations_list[:5] + [provider_lotek_panthera]
    )


def _test_filter_connections(api_client, user, filters, expected_integrations):
    api_client.force_authenticate(user)
    response = api_client.get(
        reverse("connections-list"),
        data=filters
    )
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    connections = response_data["results"]
    # Check that the returned integrations are the expected ones
    expected_integrations_ids = [str(c.id) for c in expected_integrations]
    assert len(connections) == len(expected_integrations_ids)
    for conn in connections:
        assert conn.get("id") in expected_integrations_ids


def test_filter_connections_by_provider_type_as_superuser(
        api_client, superuser, organization, provider_lotek_panthera, provider_movebank_ewt,
        integrations_list, route_1, route_2
):
    _test_filter_connections(
        api_client=api_client,
        user=superuser,
        filters={
            "provider_type": provider_movebank_ewt.type.value
        },
        expected_integrations=[provider_movebank_ewt]
    )


def test_filter_connections_by_provider_type_as_org_admin(
        api_client, org_admin_user_2, organization, provider_lotek_panthera, provider_movebank_ewt,
        integrations_list, route_1, route_2
):
    _test_filter_connections(
        api_client=api_client,
        user=org_admin_user_2,
        filters={
            "provider_type": provider_movebank_ewt.type.value
        },
        expected_integrations=[provider_movebank_ewt]
    )


def test_filter_connections_by_provider_type_as_org_viewer(
        api_client, org_viewer_user_2, organization, provider_lotek_panthera, provider_movebank_ewt,
        integrations_list, route_1, route_2
):
    _test_filter_connections(
        api_client=api_client,
        user=org_viewer_user_2,
        filters={
            "provider_type": provider_movebank_ewt.type.value
        },
        expected_integrations=[provider_movebank_ewt]
    )


def test_filter_connections_by_destination_type_as_superuser(
        api_client, superuser, organization, provider_lotek_panthera, provider_movebank_ewt,
        integrations_list, route_1, route_2, integration_type_er
):
    _test_filter_connections(
        api_client=api_client,
        user=superuser,
        filters={
            "destination_type": integration_type_er.value
        },
        expected_integrations=[provider_lotek_panthera, provider_movebank_ewt]
    )


def test_filter_connections_by_destination_type_as_org_admin(
        api_client, org_admin_user, organization, provider_lotek_panthera, provider_movebank_ewt,
        integrations_list, route_1, route_2, integration_type_er
):
    _test_filter_connections(
        api_client=api_client,
        user=org_admin_user,
        filters={
            "destination_type": integration_type_er.value
        },
        expected_integrations=[provider_lotek_panthera]
    )


def test_filter_connections_by_destination_type_as_org_viewer(
        api_client, org_viewer_user, organization, provider_lotek_panthera, provider_movebank_ewt,
        integrations_list, route_1, route_2, integration_type_er
):
    _test_filter_connections(
        api_client=api_client,
        user=org_viewer_user,
        filters={
            "destination_type": integration_type_er.value
        },
        expected_integrations=[provider_lotek_panthera]
    )


def test_filter_connections_by_multiple_destination_urls_as_superuser(
        api_client, superuser, organization, provider_lotek_panthera, provider_movebank_ewt,
        integrations_list, route_1, route_2, integration_type_er
):
    selected_destinations = route_2.destinations.all()
    _test_filter_connections(
        api_client=api_client,
        user=superuser,
        filters={
            "destination_url__in": ",".join(
                [i.base_url for i in selected_destinations]
            )
        },
        expected_integrations=[provider_lotek_panthera, provider_movebank_ewt]
    )


def test_filter_connections_by_multiple_destination_urls_as_org_admin(
        api_client, org_admin_user, organization, provider_lotek_panthera, provider_movebank_ewt,
        integrations_list, route_1, route_2, integration_type_er
):
    selected_destinations = route_1.destinations.all()
    _test_filter_connections(
        api_client=api_client,
        user=org_admin_user,
        filters={
            "destination_url__in": ",".join(
                [i.base_url for i in selected_destinations]
            )
        },
        expected_integrations=[provider_lotek_panthera]
    )


def test_filter_connections_by_multiple_destination_urls_as_org_viewer(
        api_client, org_viewer_user_2, organization, provider_lotek_panthera, provider_movebank_ewt,
        integrations_list, route_1, route_2, integration_type_er
):
    selected_destinations = route_1.destinations.all()
    _test_filter_connections(
        api_client=api_client,
        user=org_viewer_user_2,
        filters={
            "destination_url__in": ",".join(
                [i.base_url for i in selected_destinations]
            )
        },
        expected_integrations=[provider_movebank_ewt]
    )


def test_filter_connections_by_owner_exact_as_superuser(
        api_client, superuser, organization, other_organization, provider_lotek_panthera, provider_movebank_ewt,
        integrations_list, route_1, route_2, integration_type_er
):
    _test_filter_connections(
        api_client=api_client,
        user=superuser,
        filters={
            "owner": str(other_organization.id)
        },
        expected_integrations=integrations_list[5:]+[provider_movebank_ewt]
    )


def test_filter_connections_by_multiple_owners_as_superuser(
        api_client, superuser, organization, other_organization, provider_lotek_panthera, provider_movebank_ewt,
        integrations_list, route_1, route_2, integration_type_er
):
    _test_filter_connections(
        api_client=api_client,
        user=superuser,
        filters={
            "owner__in": ",".join([str(organization.id), str(other_organization.id)])
        },
        expected_integrations=integrations_list + [provider_lotek_panthera, provider_movebank_ewt]
    )


def test_filter_connections_by_owner_exact_as_org_admin(
        api_client, org_admin_user, organization, other_organization, provider_lotek_panthera, provider_movebank_ewt,
        integrations_list, route_1, route_2, integration_type_er
):
    _test_filter_connections(
        api_client=api_client,
        user=org_admin_user,
        filters={
            "owner": str(organization.id)
        },
        expected_integrations=integrations_list[:5] + [provider_lotek_panthera]
    )


def test_filter_connections_by_multiple_owners_as_org_admin(
        api_client, org_admin_user, organization, other_organization, provider_lotek_panthera, provider_movebank_ewt,
        integrations_list, route_1, route_2, integration_type_er
):
    _test_filter_connections(
        api_client=api_client,
        user=org_admin_user,
        filters={
            "owner__in": ",".join([str(organization.id), str(other_organization.id)])
        },
        expected_integrations=integrations_list[:5] + [provider_lotek_panthera]
    )


def test_filter_connections_by_owner_exact_as_org_viewer(
        api_client, org_viewer_user, organization, other_organization, provider_lotek_panthera, provider_movebank_ewt,
        integrations_list, route_1, route_2, integration_type_er
):
    _test_filter_connections(
        api_client=api_client,
        user=org_viewer_user,
        filters={
            "owner": str(organization.id)
        },
        expected_integrations=integrations_list[:5] + [provider_lotek_panthera]
    )


def test_filter_connections_by_multiple_owners_as_org_viewer(
        api_client, org_viewer_user_2, organization, other_organization, provider_lotek_panthera, provider_movebank_ewt,
        integrations_list, route_1, route_2, integration_type_er
):
    _test_filter_connections(
        api_client=api_client,
        user=org_viewer_user_2,
        filters={
            "owner__in": ",".join([str(organization.id), str(other_organization.id)])
        },
        expected_integrations=integrations_list[5:] + [provider_movebank_ewt]
    )


def _test_global_search_connections(
        api_client, user, search_term, expected_integrations,  extra_filters=None, search_fields=None
):
    api_client.force_authenticate(user)
    query_params = {
        "search": search_term,
    }
    if search_fields:
        query_params["search_fields"] = search_fields
    if extra_filters:
        query_params.update(extra_filters)
    response = api_client.get(
        reverse('connections-list'),
        data=query_params
    )
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    connections = response_data["results"]
    # Check that the returned integrations are the expected ones
    expected_integrations_ids = [str(i.id) for i in expected_integrations]
    assert len(connections) == len(expected_integrations_ids)
    for conn in connections:
        assert conn.get("id") in expected_integrations_ids


def test_global_search_connections_as_superuser(
        api_client, superuser, organization, other_organization,
        integration_type_er, integration_type_movebank, integration_type_lotek,
        integration_type_smart, smart_action_auth, smart_action_push_events,
        integrations_list, provider_movebank_ewt, provider_lotek_panthera,
        route_1, route_2
):
    _test_global_search_connections(
        api_client=api_client,
        user=superuser,
        search_term="pamdas.org",  # Looking connections with earth ranger sites
        expected_integrations=integrations_list + [provider_movebank_ewt, provider_lotek_panthera]  # Connected providers
    )


def test_global_search_connections_as_org_admin(
        api_client, org_admin_user, organization, other_organization,
        integration_type_er, integration_type_movebank, integration_type_lotek,
        integration_type_smart, smart_action_auth, smart_action_push_events,
        integrations_list, provider_movebank_ewt, provider_lotek_panthera,
        route_1, route_2
):
    _test_global_search_connections(
        api_client=api_client,
        user=org_admin_user,
        search_term="Lewa",  # Looking connections owned by Lewa
        expected_integrations=integrations_list[:5]+[provider_lotek_panthera]
    )


def test_global_search_connections_as_org_viewer(
        api_client, org_viewer_user_2, organization, other_organization,
        integration_type_er, integration_type_movebank, integration_type_lotek,
        integration_type_smart, smart_action_auth, smart_action_push_events,
        integrations_list, provider_movebank_ewt, provider_lotek_panthera,
        route_1, route_2
):
    _test_global_search_connections(
        api_client=api_client,
        user=org_viewer_user_2,
        search_term="Move",  # Looking for connections with Movebank
        expected_integrations=[provider_movebank_ewt]
    )

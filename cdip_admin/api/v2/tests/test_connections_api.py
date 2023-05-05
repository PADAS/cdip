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
        assert str(provider.id) == connection["provider"].get("id")
        assert str(provider.name) == connection["provider"].get("name")
        # Check destinations
        assert "destinations" in connection
        expected_destination_ids = [str(dest_id) for dest_id in provider.destinations.values_list("id", flat=True)]
        for destination in connection["destinations"]:
            assert destination.get("id") in expected_destination_ids
            assert "name" in destination
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


def test_list_connections_as_superuser(api_client, superuser, organization, provider_lotek_panthera, provider_movebank_ewt, integrations_list, routing_rule_1, routing_rule_2):
    _test_list_connections(
        api_client=api_client,
        user=superuser,
        # The superuser can see all the connections
        provider_list=[provider_lotek_panthera, provider_movebank_ewt]
    )


def test_list_connections_as_org_admin(api_client, org_admin_user, organization, provider_lotek_panthera, provider_movebank_ewt, integrations_list, routing_rule_1, routing_rule_2):
    _test_list_connections(
        api_client=api_client,
        user=org_admin_user,  # Belongs to one organization
        # Org admins can only see providers of their organizations
        provider_list=[provider_lotek_panthera]
    )


def test_list_connections_as_org_admin_2(api_client, org_admin_user_2, organization, provider_lotek_panthera, provider_movebank_ewt, integrations_list, routing_rule_1, routing_rule_2):
    _test_list_connections(
        api_client=api_client,
        user=org_admin_user_2,  # Belongs to one organization
        # Org admins can only see providers of their organizations
        provider_list=[provider_movebank_ewt]
    )


def test_list_connections_as_org_viewer(api_client, org_viewer_user, organization, provider_lotek_panthera, provider_movebank_ewt, integrations_list, routing_rule_1, routing_rule_2):
    _test_list_connections(
        api_client=api_client,
        user=org_viewer_user,  # Belongs to one organization
        # Org viewer can only see providers of their organizations
        provider_list=[provider_lotek_panthera]
    )

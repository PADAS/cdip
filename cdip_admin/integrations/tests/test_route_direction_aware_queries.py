import pytest

from integrations.models import Integration, Route


pytestmark = pytest.mark.django_db


def _make_integration(organization, integration_type, name):
    return Integration.objects.create(
        type=integration_type,
        name=name,
        owner=organization,
        base_url="https://api.test.lotek.com",
    )


def _make_route(organization, name, provider, destinations, direction=Route.Direction.FORWARD):
    route = Route.objects.create(owner=organization, name=name, direction=direction)
    route.data_providers.add(provider)
    route.destinations.add(*destinations)
    return route


@pytest.fixture
def provider_and_destination(organization, integration_type_lotek):
    provider = _make_integration(organization, integration_type_lotek, "P")
    destination = _make_integration(organization, integration_type_lotek, "D")
    forward_route = _make_route(organization, "P to D", provider, [destination])
    # D acting as a return leg's provider -- an auto-created role, not a real
    # connection D's owner set up. Mirrors what GUNDI-5730 U1 will create.
    return_route = _make_route(
        organization, "D to P (return)", destination, [provider],
        direction=Route.Direction.RETURN,
    )
    return provider, destination, forward_route, return_route


def test_providers_manager_excludes_a_return_leg_only_provider(provider_and_destination):
    provider, destination, _, _ = provider_and_destination
    provider_ids = set(Integration.providers.all().values_list("id", flat=True))
    assert provider.id in provider_ids
    assert destination.id not in provider_ids


def test_routing_rules_excludes_the_return_leg(provider_and_destination):
    provider, destination, forward_route, return_route = provider_and_destination
    assert list(provider.routing_rules.values_list("id", flat=True)) == [forward_route.id]
    assert list(destination.routing_rules.values_list("id", flat=True)) == []


def test_is_used_as_provider_ignores_the_return_leg_role(provider_and_destination):
    provider, destination, _, _ = provider_and_destination
    assert provider.is_used_as_provider is True
    assert destination.is_used_as_provider is False


def test_is_used_as_destination_ignores_the_return_leg_role(provider_and_destination):
    provider, destination, _, _ = provider_and_destination
    # provider is only a "destination" through the return leg, which doesn't count.
    assert provider.is_used_as_destination is False
    assert destination.is_used_as_destination is True


def test_destinations_property_only_follows_forward_routes(provider_and_destination):
    provider, destination, _, _ = provider_and_destination
    assert list(provider.destinations.values_list("id", flat=True)) == [destination.id]
    # destination's only provider-role Route is the return leg, so it has no
    # real destinations of its own.
    assert list(destination.destinations.values_list("id", flat=True)) == []

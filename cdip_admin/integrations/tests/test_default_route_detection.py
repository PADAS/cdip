"""Detection layer (spec §5.2): one queryset defines what a broken default route is."""
import uuid

import pytest

from integrations.models import (
    Integration,
    Route,
    RouteDestination,
    RouteProvider,
    DefaultRouteState,
    annotate_default_route_state,
    filter_by_default_route_state,
    get_default_route_state,
    providers_without_valid_default_route,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def make_provider(organization, integration_type_lotek):
    def _make(name="Provider"):
        return Integration.objects.create(
            type=integration_type_lotek, owner=organization,
            name=f"{name} {uuid.uuid4().hex[:6]}", base_url="https://api.test.lotek.com",
        )
    return _make


@pytest.fixture
def make_route(organization):
    def _make(name="Route", providers=(), destinations=()):
        route = Route.objects.create(owner=organization, name=f"{name} {uuid.uuid4().hex[:6]}")
        RouteProvider.objects.bulk_create([RouteProvider(integration=p, route=route) for p in providers])
        RouteDestination.objects.bulk_create([RouteDestination(integration=d, route=route) for d in destinations])
        return route
    return _make


def set_default(integration, route):
    Integration.objects.filter(pk=integration.pk).update(default_route=route)
    integration.refresh_from_db()


@pytest.fixture
def zoo(make_provider, make_route, destination_movebank):
    """One provider per state, plus an exempt destination-only integration."""
    valid = make_provider("valid")
    set_default(valid, make_route("valid", providers=[valid], destinations=[destination_movebank]))

    valid_empty_alone = make_provider("valid-empty-alone")           # empty default, no other route delivers
    set_default(valid_empty_alone, make_route("empty", providers=[valid_empty_alone]))
    make_route("also-empty", providers=[valid_empty_alone])

    missing = make_provider("missing")
    make_route("m", providers=[missing])

    not_member = make_provider("not-member")
    make_route("nm", providers=[not_member], destinations=[destination_movebank])
    set_default(not_member, make_route("orphan"))

    empty_default = make_provider("empty-default")
    set_default(empty_default, make_route("placeholder", providers=[empty_default]))
    make_route("real", providers=[empty_default], destinations=[destination_movebank])

    return {
        "valid": valid, "valid_empty_alone": valid_empty_alone, "missing": missing,
        "not_member": not_member, "empty_default": empty_default, "exempt": destination_movebank,
    }


def test_get_default_route_state_classifies_each_shape(zoo):
    assert get_default_route_state(zoo["valid"]) == DefaultRouteState.VALID
    assert get_default_route_state(zoo["valid_empty_alone"]) == DefaultRouteState.VALID
    assert get_default_route_state(zoo["missing"]) == DefaultRouteState.MISSING
    assert get_default_route_state(zoo["not_member"]) == DefaultRouteState.NOT_MEMBER
    assert get_default_route_state(zoo["empty_default"]) == DefaultRouteState.EMPTY_DEFAULT


def test_destination_only_integration_is_exempt(zoo):
    assert get_default_route_state(zoo["exempt"]) is None
    assert zoo["exempt"].pk not in providers_without_valid_default_route().values_list("pk", flat=True)


def test_providers_without_valid_default_route_returns_exactly_the_violators(zoo):
    violators = set(providers_without_valid_default_route().values_list("pk", flat=True))

    assert violators == {zoo["missing"].pk, zoo["not_member"].pk, zoo["empty_default"].pk}


def test_annotations_are_mutually_exclusive_per_row(zoo):
    rows = annotate_default_route_state(Integration.providers.all()).values(
        "pk", "default_route_missing", "default_route_not_member", "default_route_empty",
    )
    for row in rows:
        flags = [row["default_route_missing"], row["default_route_not_member"], row["default_route_empty"]]
        assert sum(bool(f) for f in flags) <= 1, row


@pytest.mark.parametrize("state, key", [
    (DefaultRouteState.MISSING, "missing"),
    (DefaultRouteState.NOT_MEMBER, "not_member"),
    (DefaultRouteState.EMPTY_DEFAULT, "empty_default"),
])
def test_filter_by_state_returns_one_provider_each(zoo, state, key):
    assert set(filter_by_default_route_state(Integration.objects.all(), state).values_list("pk", flat=True)) == {zoo[key].pk}


def test_filter_by_valid_returns_the_valid_providers_only(zoo):
    valid = set(filter_by_default_route_state(Integration.objects.all(), DefaultRouteState.VALID).values_list("pk", flat=True))

    assert {zoo["valid"].pk, zoo["valid_empty_alone"].pk} <= valid
    assert not ({zoo["missing"].pk, zoo["not_member"].pk, zoo["empty_default"].pk, zoo["exempt"].pk} & valid)


def test_violation_queryset_is_a_single_statement(zoo, django_assert_num_queries):
    with django_assert_num_queries(1):
        list(providers_without_valid_default_route())

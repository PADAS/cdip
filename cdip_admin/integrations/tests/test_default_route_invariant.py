"""Tests for the default-route invariant (spec: docs/superpowers/specs/2026-09-18-default-route-invariant-design.md).

Setup helpers bypass signals (bulk_create / QuerySet.update) so a test's
starting state is exactly what it says, even once the receivers exist.
"""
import uuid

import pytest

from activity_log.models import ActivityLog
from integrations.models import (
    Integration,
    Route,
    RouteDestination,
    RouteProvider,
    AmbiguousDefaultRouteError,
    decide_default_route,
    resolve_default_route,
    DEFAULT_ROUTE_AUTO_ASSIGNED,
)

pytestmark = pytest.mark.django_db


# --- helpers -----------------------------------------------------------------

@pytest.fixture
def make_provider(organization, integration_type_lotek):
    def _make(name="Provider"):
        return Integration.objects.create(
            type=integration_type_lotek,
            owner=organization,
            name=f"{name} {uuid.uuid4().hex[:6]}",
            base_url="https://api.test.lotek.com",
        )
    return _make


@pytest.fixture
def make_destination(organization, integration_type_er):
    def _make(name="ER Site"):
        return Integration.objects.create(
            type=integration_type_er,
            owner=organization,
            name=f"{name} {uuid.uuid4().hex[:6]}",
            base_url=f"https://{uuid.uuid4().hex[:8]}.pamdas.org",
        )
    return _make


@pytest.fixture
def make_route(organization):
    """Create a route and link providers/destinations WITHOUT firing signals."""
    def _make(name="Route", providers=(), destinations=()):
        route = Route.objects.create(owner=organization, name=f"{name} {uuid.uuid4().hex[:6]}")
        RouteProvider.objects.bulk_create([RouteProvider(integration=p, route=route) for p in providers])
        RouteDestination.objects.bulk_create([RouteDestination(integration=d, route=route) for d in destinations])
        return route
    return _make


def set_default(integration, route):
    """Set default_route without firing signals, then refresh the instance."""
    Integration.objects.filter(pk=integration.pk).update(default_route=route)
    integration.refresh_from_db()


def auto_assign_logs(integration):
    return ActivityLog.objects.filter(integration=integration, value=DEFAULT_ROUTE_AUTO_ASSIGNED)


# --- decide_default_route ----------------------------------------------------

def test_decide_no_routes_means_null(make_provider, make_route):
    provider = make_provider()
    orphan_default = make_route("Orphan")          # provider is NOT on it
    set_default(provider, orphan_default)

    decision = decide_default_route(provider)

    assert decision.route is None
    assert decision.changed is True


def test_decide_null_default_with_one_route_picks_it(make_provider, make_route):
    provider = make_provider()
    route = make_route("Only", providers=[provider])

    decision = decide_default_route(provider)

    assert decision.route == route
    assert decision.changed is True


def test_decide_keeps_valid_default(make_provider, make_destination, make_route):
    provider, er = make_provider(), make_destination()
    default = make_route("Default", providers=[provider], destinations=[er])
    make_route("Other", providers=[provider], destinations=[er])
    set_default(provider, default)

    decision = decide_default_route(provider)

    assert decision.route == default
    assert decision.changed is False


def test_decide_keeps_empty_default_when_no_other_route_delivers(make_provider, make_route):
    provider = make_provider()
    empty_default = make_route("Empty", providers=[provider])
    make_route("Also empty", providers=[provider])
    set_default(provider, empty_default)

    decision = decide_default_route(provider)

    assert decision.route == empty_default
    assert decision.changed is False


def test_decide_switches_empty_default_to_the_one_route_that_delivers(make_provider, make_destination, make_route):
    provider, er = make_provider(), make_destination()
    empty_default = make_route("Empty", providers=[provider])
    real = make_route("Real", providers=[provider], destinations=[er])
    set_default(provider, empty_default)

    decision = decide_default_route(provider)

    assert decision.route == real
    assert decision.changed is True


def test_decide_prefers_joining_route_when_default_is_null(make_provider, make_destination, make_route):
    provider, er = make_provider(), make_destination()
    make_route("A", providers=[provider], destinations=[er])
    joining = make_route("B", providers=[provider], destinations=[er])

    decision = decide_default_route(provider, joining_route=joining)

    assert decision.route == joining


def test_decide_does_not_prefer_an_empty_joining_route_over_a_delivering_one(make_provider, make_destination, make_route):
    provider, er = make_provider(), make_destination()
    empty_default = make_route("Empty default", providers=[provider])
    real = make_route("Real", providers=[provider], destinations=[er])
    joining_empty = make_route("Joining empty", providers=[provider])
    set_default(provider, empty_default)

    decision = decide_default_route(provider, joining_route=joining_empty)

    assert decision.route == real


def test_decide_raises_when_several_candidates(make_provider, make_destination, make_route):
    provider, er = make_provider(), make_destination()
    a = make_route("A", providers=[provider], destinations=[er])
    b = make_route("B", providers=[provider], destinations=[er])

    with pytest.raises(AmbiguousDefaultRouteError) as excinfo:
        decide_default_route(provider)

    assert excinfo.value.integration == provider
    assert {r.pk for r in excinfo.value.candidates} == {a.pk, b.pk}
    assert a.name in str(excinfo.value) and b.name in str(excinfo.value)


def test_decide_excludes_leaving_and_excluded_routes(make_provider, make_destination, make_route):
    provider, er = make_provider(), make_destination()
    default = make_route("Default", providers=[provider], destinations=[er])
    doomed = make_route("Doomed", providers=[provider], destinations=[er])
    survivor = make_route("Survivor", providers=[provider], destinations=[er])
    set_default(provider, default)

    decision = decide_default_route(provider, leaving_route=default, exclude_route_ids=[doomed.pk])

    assert decision.route == survivor
    assert decision.changed is True


# --- resolve_default_route ---------------------------------------------------

def test_resolve_assigns_and_logs_once(make_provider, make_route):
    provider = make_provider()
    route = make_route("Only", providers=[provider])

    assigned = resolve_default_route(provider, via="unit_test")

    provider.refresh_from_db()
    assert assigned == route
    assert provider.default_route == route
    log = auto_assign_logs(provider).get()
    assert log.origin == ActivityLog.Origin.PORTAL
    assert log.log_level == ActivityLog.LogLevels.WARNING
    assert log.log_type == ActivityLog.LogTypes.EVENT
    assert log.title == f"Default route set to '{route.name}'"
    assert log.details == {"route_id": str(route.pk), "via": "unit_test", "previous_default_route_id": None}
    assert log.is_reversible is False


def test_resolve_is_idempotent(make_provider, make_route):
    provider = make_provider()
    make_route("Only", providers=[provider])

    resolve_default_route(provider, via="unit_test")
    resolve_default_route(provider, via="unit_test")

    assert auto_assign_logs(provider).count() == 1


def test_resolve_records_previous_default(make_provider, make_destination, make_route):
    provider, er = make_provider(), make_destination()
    empty_default = make_route("Empty", providers=[provider])
    real = make_route("Real", providers=[provider], destinations=[er])
    set_default(provider, empty_default)

    resolve_default_route(provider, via="unit_test")

    log = auto_assign_logs(provider).get()
    assert log.details["previous_default_route_id"] == str(empty_default.pk)
    assert log.details["route_id"] == str(real.pk)


def test_resolve_to_null_does_not_log(make_provider, make_route):
    provider = make_provider()
    orphan = make_route("Orphan")
    set_default(provider, orphan)

    assert resolve_default_route(provider, via="unit_test") is None
    provider.refresh_from_db()
    assert provider.default_route is None
    assert auto_assign_logs(provider).count() == 0

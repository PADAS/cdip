"""Tests for the default-route invariant (spec: docs/superpowers/specs/2026-09-18-default-route-invariant-design.md).

Setup helpers bypass signals (bulk_create / QuerySet.update) so a test's
starting state is exactly what it says, even once the receivers exist.
"""
import uuid

import pytest
from django.db import transaction

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


def test_decide_null_default_prefers_the_route_that_delivers(make_provider, make_destination, make_route):
    provider, er = make_provider(), make_destination()
    make_route("Empty", providers=[provider])
    real = make_route("Real", providers=[provider], destinations=[er])

    decision = decide_default_route(provider)

    assert decision.route == real
    assert decision.changed is True


def test_decide_null_default_does_not_pick_an_empty_joining_route_over_a_delivering_one(make_provider, make_destination, make_route):
    provider, er = make_provider(), make_destination()
    real = make_route("Real", providers=[provider], destinations=[er])
    joining_empty = make_route("Joining empty", providers=[provider])

    decision = decide_default_route(provider, joining_route=joining_empty)

    assert decision.route == real


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


def test_resolve_survives_a_failed_activity_log_write(make_provider, make_route, mocker):
    """A failed log INSERT must neither undo the repair nor poison the caller's transaction.

    Only the auto-assignment log write (value=DEFAULT_ROUTE_AUTO_ASSIGNED) is made to
    fail; ``Integration`` also carries ``ChangeLogMixin``, which makes its own
    unrelated ``ActivityLog.objects.create`` call from ``save()`` on every save
    (including the ``integration.save(update_fields=["default_route"])`` this
    resolve does) and must be left alone so it doesn't abort the transaction first.
    """
    provider = make_provider()
    route = make_route("Only", providers=[provider])

    from django.db import connection

    original_create = ActivityLog.objects.create

    def failing_insert(**kwargs):
        if kwargs.get("value") != DEFAULT_ROUTE_AUTO_ASSIGNED:
            return original_create(**kwargs)
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1/0")   # IntegrityError/DataError-class failure inside the transaction

    mocker.patch("activity_log.models.ActivityLog.objects.create", side_effect=failing_insert)

    with transaction.atomic():
        assert resolve_default_route(provider, via="unit_test") == route
        provider.refresh_from_db()          # would raise TransactionManagementError if poisoned

    assert provider.default_route == route


# --- entry point 1: a provider joins a route ---------------------------------

def test_route_provider_create_sets_null_default(make_provider, make_route):
    provider = make_provider()
    route = make_route("New")

    RouteProvider.objects.create(integration=provider, route=route)

    provider.refresh_from_db()
    assert provider.default_route == route
    assert auto_assign_logs(provider).get().details["via"] == "route_provider_added"


def test_data_providers_add_sets_null_default(make_provider, make_route):
    provider = make_provider()
    route = make_route("New")

    route.data_providers.add(provider)

    provider.refresh_from_db()
    assert provider.default_route == route
    assert auto_assign_logs(provider).count() == 1


def test_data_providers_set_sets_null_default(make_provider, make_route):
    provider = make_provider()
    route = make_route("New")

    route.data_providers.set([provider])

    provider.refresh_from_db()
    assert provider.default_route == route


def test_reverse_add_sets_null_default(make_provider, make_route):
    provider = make_provider()
    route = make_route("New")

    provider.routing_rules_by_provider.add(route)

    provider.refresh_from_db()
    assert provider.default_route == route


def test_join_switches_empty_default_to_route_that_already_delivers(make_provider, make_destination, make_route):
    provider, er = make_provider(), make_destination()
    placeholder = make_route("Placeholder", providers=[provider])
    set_default(provider, placeholder)
    real = make_route("Real", destinations=[er])

    real.data_providers.add(provider)

    provider.refresh_from_db()
    assert provider.default_route == real
    log = auto_assign_logs(provider).get()
    assert log.details["via"] == "route_provider_added"
    assert log.details["previous_default_route_id"] == str(placeholder.pk)


def test_join_keeps_default_that_delivers(make_provider, make_destination, make_route):
    provider, er = make_provider(), make_destination()
    default = make_route("Default", providers=[provider], destinations=[er])
    set_default(provider, default)
    other = make_route("Other", destinations=[er])

    other.data_providers.add(provider)

    provider.refresh_from_db()
    assert provider.default_route == default
    assert auto_assign_logs(provider).count() == 0


# --- entry point 1b: a route gains destinations (DRF adds providers first) ----

def test_adding_destinations_after_providers_switches_empty_default(make_provider, make_destination, make_route):
    """Mirrors POST /v2/routes/: ModelSerializer writes data_providers, then destinations."""
    provider, er = make_provider(), make_destination()
    placeholder = make_route("Placeholder", providers=[provider])
    set_default(provider, placeholder)
    new_route = make_route("New")

    new_route.data_providers.add(provider)      # new_route is still empty → default stays
    provider.refresh_from_db()
    assert provider.default_route == placeholder

    new_route.destinations.add(er)              # now it delivers → switch

    provider.refresh_from_db()
    assert provider.default_route == new_route
    assert auto_assign_logs(provider).get().details["via"] == "route_destination_added"


def test_route_destination_create_switches_empty_default(make_provider, make_destination, make_route):
    provider, er = make_provider(), make_destination()
    placeholder = make_route("Placeholder", providers=[provider])
    set_default(provider, placeholder)
    new_route = make_route("New", providers=[provider])

    RouteDestination.objects.create(integration=er, route=new_route)

    provider.refresh_from_db()
    assert provider.default_route == new_route


def test_adding_destination_to_default_route_itself_changes_nothing(make_provider, make_destination, make_route):
    provider, er = make_provider(), make_destination()
    default = make_route("Default", providers=[provider])
    set_default(provider, default)

    default.destinations.add(er)

    provider.refresh_from_db()
    assert provider.default_route == default
    assert auto_assign_logs(provider).count() == 0


# --- raw / convergence ---------------------------------------------------------

def test_raw_save_is_skipped(make_provider, make_route):
    provider = make_provider()
    route = make_route("Fixture-loaded")

    RouteProvider(integration=provider, route=route).save_base(raw=True)

    provider.refresh_from_db()
    assert provider.default_route is None


def test_ensure_default_route_converges_without_auto_assign_log(make_provider):
    from integrations.models import ensure_default_route
    provider = make_provider()

    ensure_default_route(integration=provider)

    provider.refresh_from_db()
    assert provider.default_route is not None
    assert provider.default_route.data_providers.filter(pk=provider.pk).exists()
    assert auto_assign_logs(provider).count() == 0


# --- entry point 4: default_route set directly --------------------------------

def test_setting_default_route_directly_adds_provider_membership(make_provider, make_route):
    provider = make_provider()
    route = make_route("Chosen")

    provider.default_route = route
    provider.save()

    assert RouteProvider.objects.filter(integration=provider, route=route).exists()
    provider.refresh_from_db()
    assert provider.default_route == route
    assert auto_assign_logs(provider).count() == 0   # a human chose it; nothing was auto-assigned


def test_setting_default_route_via_update_fields_adds_membership(make_provider, make_route):
    provider = make_provider()
    route = make_route("Chosen")

    provider.default_route = route
    provider.save(update_fields=["default_route"])

    assert RouteProvider.objects.filter(integration=provider, route=route).exists()


def test_saving_unrelated_fields_does_not_touch_membership(make_provider, make_route):
    provider = make_provider()
    orphan = make_route("Orphan")
    set_default(provider, orphan)                     # broken state, set without signals

    provider.name = "renamed"
    provider.save(update_fields=["name"])

    assert not RouteProvider.objects.filter(integration=provider, route=orphan).exists()


def test_raw_integration_save_is_skipped(make_provider, make_route):
    provider = make_provider()
    route = make_route("Chosen")
    provider.default_route = route

    provider.save_base(raw=True)

    assert not RouteProvider.objects.filter(integration=provider, route=route).exists()


# --- entry point 2: a provider leaves a route ----------------------------------

@pytest.fixture
def provider_on_three_delivering_routes(make_provider, make_destination, make_route):
    """default=R1; also on R2 and R3; all three deliver. Removing from R1 is ambiguous."""
    provider, er = make_provider(), make_destination()
    r1 = make_route("R1", providers=[provider], destinations=[er])
    r2 = make_route("R2", providers=[provider], destinations=[er])
    r3 = make_route("R3", providers=[provider], destinations=[er])
    set_default(provider, r1)
    return provider, r1, r2, r3


def test_remove_from_default_route_with_one_other_reassigns(make_provider, make_destination, make_route):
    provider, er = make_provider(), make_destination()
    r1 = make_route("R1", providers=[provider], destinations=[er])
    r2 = make_route("R2", providers=[provider], destinations=[er])
    set_default(provider, r1)

    r1.data_providers.remove(provider)

    provider.refresh_from_db()
    assert provider.default_route == r2
    log = auto_assign_logs(provider).get()
    assert log.details["via"] == "route_provider_removed"
    assert log.details["previous_default_route_id"] == str(r1.pk)


def test_remove_from_default_route_with_several_others_refuses(provider_on_three_delivering_routes):
    provider, r1, r2, r3 = provider_on_three_delivering_routes

    with pytest.raises(AmbiguousDefaultRouteError) as excinfo:
        with transaction.atomic():
            r1.data_providers.remove(provider)

    assert {r.pk for r in excinfo.value.candidates} == {r2.pk, r3.pk}
    provider.refresh_from_db()
    assert provider.default_route == r1
    assert RouteProvider.objects.filter(integration=provider, route=r1).exists()


def test_remove_from_only_route_nulls_default(make_provider, make_route):
    provider = make_provider()
    only = make_route("Only", providers=[provider])
    set_default(provider, only)

    only.data_providers.remove(provider)

    provider.refresh_from_db()
    assert provider.default_route is None
    assert auto_assign_logs(provider).count() == 0


def test_remove_from_non_default_route_keeps_default(make_provider, make_destination, make_route):
    provider, er = make_provider(), make_destination()
    default = make_route("Default", providers=[provider], destinations=[er])
    other = make_route("Other", providers=[provider], destinations=[er])
    set_default(provider, default)

    other.data_providers.remove(provider)

    provider.refresh_from_db()
    assert provider.default_route == default
    assert auto_assign_logs(provider).count() == 0


def test_clear_providers_nulls_default_of_single_route_provider(make_provider, make_route):
    provider = make_provider()
    only = make_route("Only", providers=[provider])
    set_default(provider, only)

    only.data_providers.clear()

    provider.refresh_from_db()
    assert provider.default_route is None


def test_reverse_clear_nulls_default(make_provider, make_destination, make_route):
    provider, er = make_provider(), make_destination()
    r1 = make_route("R1", providers=[provider], destinations=[er])
    make_route("R2", providers=[provider], destinations=[er])
    set_default(provider, r1)

    provider.routing_rules_by_provider.clear()

    provider.refresh_from_db()
    assert provider.default_route is None


def test_set_replacing_provider_reassigns_the_leaver(make_provider, make_destination, make_route):
    leaver, newcomer, er = make_provider("Leaver"), make_provider("Newcomer"), make_destination()
    r1 = make_route("R1", providers=[leaver], destinations=[er])
    r2 = make_route("R2", providers=[leaver], destinations=[er])
    set_default(leaver, r1)

    r1.data_providers.set([newcomer])

    leaver.refresh_from_db(); newcomer.refresh_from_db()
    assert leaver.default_route == r2
    assert newcomer.default_route == r1


def test_route_provider_queryset_delete_reassigns(make_provider, make_destination, make_route):
    provider, er = make_provider(), make_destination()
    r1 = make_route("R1", providers=[provider], destinations=[er])
    r2 = make_route("R2", providers=[provider], destinations=[er])
    set_default(provider, r1)

    RouteProvider.objects.filter(integration=provider, route=r1).delete()

    provider.refresh_from_db()
    assert provider.default_route == r2
    assert auto_assign_logs(provider).count() == 1


def test_deleting_the_integration_itself_is_not_blocked(provider_on_three_delivering_routes):
    provider, *_ = provider_on_three_delivering_routes
    provider_id = provider.pk

    provider.delete()

    assert not Integration.objects.filter(pk=provider_id).exists()

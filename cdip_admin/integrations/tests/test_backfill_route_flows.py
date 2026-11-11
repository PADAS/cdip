import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from integrations.models import Integration, Route


pytestmark = pytest.mark.django_db


def _make_integration(organization, integration_type, name):
    return Integration.objects.create(
        type=integration_type,
        name=name,
        owner=organization,
        base_url="https://api.test.lotek.com",
    )


def _make_route(organization, name, provider, destinations):
    route = Route.objects.create(owner=organization, name=name)
    route.data_providers.add(provider)
    route.destinations.add(*destinations)
    return route


def _clear_flow_id(route):
    # Simulates a pre-GUNDI-5730 Route: Route.save() auto-assigns flow_id on
    # create, so legacy data has to be faked with a bare queryset .update(),
    # which skips save() -- the same way the real legacy rows got there.
    Route.objects.filter(pk=route.pk).update(flow_id=None)
    route.refresh_from_db()


def test_backfills_flow_id_on_forward_routes_missing_it(organization, integration_type_lotek):
    a = _make_integration(organization, integration_type_lotek, "A")
    b = _make_integration(organization, integration_type_lotek, "B")
    route = _make_route(organization, "A to B", a, [b])
    _clear_flow_id(route)

    call_command("backfill_route_flows", "--fix")

    route.refresh_from_db()
    assert route.flow_id == route.id


def test_links_a_return_leg_whose_name_and_structure_both_match(organization, integration_type_lotek):
    a = _make_integration(organization, integration_type_lotek, "A")
    b = _make_integration(organization, integration_type_lotek, "B")
    forward = _make_route(organization, "A to B", a, [b])
    _clear_flow_id(forward)
    legacy_return = _make_route(organization, "B → A", b, [a])
    _clear_flow_id(legacy_return)

    call_command("backfill_route_flows", "--fix")

    forward.refresh_from_db()
    legacy_return.refresh_from_db()
    assert forward.flow_id == forward.id
    assert legacy_return.flow_id == forward.id
    assert legacy_return.direction == Route.Direction.RETURN
    assert legacy_return.return_for_destination_id == b.id


def test_dry_run_changes_nothing(organization, integration_type_lotek):
    a = _make_integration(organization, integration_type_lotek, "A")
    b = _make_integration(organization, integration_type_lotek, "B")
    forward = _make_route(organization, "A to B", a, [b])
    _clear_flow_id(forward)
    legacy_return = _make_route(organization, "B → A", b, [a])
    _clear_flow_id(legacy_return)

    call_command("backfill_route_flows")  # no --fix

    forward.refresh_from_db()
    legacy_return.refresh_from_db()
    assert forward.flow_id is None
    assert legacy_return.flow_id is None
    assert legacy_return.direction == Route.Direction.FORWARD


def test_skips_ambiguous_structural_match(organization, integration_type_lotek):
    a = _make_integration(organization, integration_type_lotek, "A")
    b = _make_integration(organization, integration_type_lotek, "B")
    forward_1 = _make_route(organization, "A to B (1)", a, [b])
    forward_2 = _make_route(organization, "A to B (2)", a, [b])
    legacy_return = _make_route(organization, "B → A", b, [a])
    _clear_flow_id(legacy_return)

    with pytest.raises(CommandError):
        call_command("backfill_route_flows", "--fix")

    legacy_return.refresh_from_db()
    # Not converted -- still direction=FORWARD, so it correctly gets its OWN
    # flow_id (every forward Route needs one), not linked to either candidate.
    assert legacy_return.direction == Route.Direction.FORWARD
    assert legacy_return.flow_id == legacy_return.id
    assert legacy_return.return_for_destination_id is None


def test_skips_candidate_whose_name_does_not_match_despite_unique_structural_match(
    organization, integration_type_lotek
):
    a = _make_integration(organization, integration_type_lotek, "A")
    b = _make_integration(organization, integration_type_lotek, "B")
    forward = _make_route(organization, "A to B", a, [b])
    # Still looks like a return-leg name (has the separator), but doesn't match
    # the exact stamp for this pair -- e.g. an integration got renamed after
    # the fact. Worth a human's review, not a silent guess.
    renamed_return = _make_route(organization, "B → Something else", b, [a])

    with pytest.raises(CommandError):
        call_command("backfill_route_flows", "--fix")

    renamed_return.refresh_from_db()
    assert renamed_return.direction == Route.Direction.FORWARD


def test_leaves_a_plain_route_with_a_structural_mirror_alone(organization, integration_type_lotek):
    # The forward half of a real bidirectional pair, once its return leg is
    # correctly linked, structurally mirrors that return leg too -- it must
    # not also be evaluated as if IT might be a return leg.
    a = _make_integration(organization, integration_type_lotek, "A")
    b = _make_integration(organization, integration_type_lotek, "B")
    forward = _make_route(organization, "A to B", a, [b])
    legacy_return = _make_route(organization, "B → A", b, [a])

    call_command("backfill_route_flows", "--fix")

    forward.refresh_from_db()
    assert forward.direction == Route.Direction.FORWARD


def test_leaves_an_ordinary_route_with_no_reverse_counterpart_alone(organization, integration_type_lotek):
    a = _make_integration(organization, integration_type_lotek, "A")
    b = _make_integration(organization, integration_type_lotek, "B")
    plain = _make_route(organization, "Just a normal route", a, [b])

    call_command("backfill_route_flows", "--fix")

    plain.refresh_from_db()
    assert plain.direction == Route.Direction.FORWARD
    assert plain.return_for_destination_id is None


def test_skips_reciprocal_mirror_routes_instead_of_converting_either(organization, integration_type_lotek):
    # A → B and B → A each pass the name+structure check with the OTHER as
    # their "forward" Route -- genuinely ambiguous which side is real.
    # Converting both would leave this flow with no forward leg at all.
    a = _make_integration(organization, integration_type_lotek, "A")
    b = _make_integration(organization, integration_type_lotek, "B")
    route_1 = _make_route(organization, "A → B", a, [b])
    route_2 = _make_route(organization, "B → A", b, [a])

    with pytest.raises(CommandError):
        call_command("backfill_route_flows", "--fix")

    route_1.refresh_from_db()
    route_2.refresh_from_db()
    assert route_1.direction == Route.Direction.FORWARD
    assert route_2.direction == Route.Direction.FORWARD


def test_skips_duplicate_candidates_matching_the_same_slot(organization, integration_type_lotek):
    # Two separate legacy return-leg-looking rows both structurally and
    # nominally match the SAME forward Route and destination. Applying both
    # would violate unique_return_leg_per_flow_destination after the first
    # write commits -- reject both instead of guessing which one is real.
    a = _make_integration(organization, integration_type_lotek, "A")
    b = _make_integration(organization, integration_type_lotek, "B")
    forward = _make_route(organization, "A to B", a, [b])
    _clear_flow_id(forward)
    duplicate_1 = _make_route(organization, "B → A", b, [a])
    duplicate_2 = _make_route(organization, "B → A", b, [a])

    with pytest.raises(CommandError):
        call_command("backfill_route_flows", "--fix")

    duplicate_1.refresh_from_db()
    duplicate_2.refresh_from_db()
    assert duplicate_1.direction == Route.Direction.FORWARD
    assert duplicate_2.direction == Route.Direction.FORWARD


def test_rejects_a_candidate_whose_slot_is_already_linked(organization, integration_type_lotek):
    a = _make_integration(organization, integration_type_lotek, "A")
    b = _make_integration(organization, integration_type_lotek, "B")
    forward = _make_route(organization, "A to B", a, [b])
    already_linked = Route.objects.create(
        owner=organization, name="B → A", flow_id=forward.flow_id,
        direction=Route.Direction.RETURN, return_for_destination=b,
    )
    already_linked.data_providers.add(b)
    already_linked.destinations.add(a)
    another_candidate = _make_route(organization, "B → A", b, [a])

    with pytest.raises(CommandError):
        call_command("backfill_route_flows", "--fix")

    another_candidate.refresh_from_db()
    assert another_candidate.direction == Route.Direction.FORWARD


def test_reports_a_stale_default_route_without_changing_it(organization, integration_type_lotek):
    # Detected, not repaired here: what B's default_route SHOULD become once
    # this route stops being a valid forward route is GUNDI-5893's design
    # question. This tool must surface the gap, not silently leave it or
    # silently guess a replacement.
    a = _make_integration(organization, integration_type_lotek, "A")
    b = _make_integration(organization, integration_type_lotek, "B")
    forward = _make_route(organization, "A to B", a, [b])
    _clear_flow_id(forward)
    legacy_return = _make_route(organization, "B → A", b, [a])
    _clear_flow_id(legacy_return)
    b.default_route = legacy_return
    b.save(update_fields=["default_route"])

    call_command("backfill_route_flows", "--fix")

    legacy_return.refresh_from_db()
    b.refresh_from_db()
    assert legacy_return.direction == Route.Direction.RETURN
    assert b.default_route_id == legacy_return.id  # untouched, only flagged

"""Keep ``Integration.default_route`` a real invariant.

Spec: docs/superpowers/specs/2026-09-18-default-route-invariant-design.md (§4, §5.1).

The routing service resolves a provider's destinations through
``Integration.default_route`` only, so for every integration that is a provider
on at least one route the default must (1) be set, (2) be one of its routes and
(3) not be an empty route while another of its routes has destinations.

This module holds the *decision* (``decide_default_route``) and the *apply +
log* step (``resolve_default_route``). ``integrations/signals.py`` calls them
from receivers; ``reassign_default_route`` is the FK's ``on_delete`` callable.
It lives beside ``models.py`` (not in ``signals.py``) because ``models.py`` has
to import the ``on_delete`` callable, and ``signals.py`` imports ``models``.
Model classes are looked up lazily for the same reason.
"""
import logging
from typing import NamedTuple, Optional

from django.apps import apps
from django.db import transaction

logger = logging.getLogger(__name__)

DEFAULT_ROUTE_AUTO_ASSIGNED = "default_route_auto_assigned"


class AmbiguousDefaultRouteError(Exception):
    """Raised when an integration needs a new default route and more than one
    of its routes could be it. Nothing is routed somewhere nobody chose; a human
    has to pick (Admin → Integration → Default Routing Rule)."""

    def __init__(self, integration, candidates):
        self.integration = integration
        self.candidates = list(candidates)
        names = ", ".join(f"'{route.name}' ({route.pk})" for route in self.candidates)
        super().__init__(
            f"Cannot choose a default route for integration '{integration.name}' "
            f"({integration.pk}): it is a provider on several routes: {names}. "
            "Set its default route explicitly and retry."
        )


class DefaultRouteDecision(NamedTuple):
    route: Optional[object]  # a Route, or None when the integration is a provider on no route
    changed: bool            # True when ``route`` differs from the stored default


def route_has_destinations(route) -> bool:
    RouteDestination = apps.get_model("integrations", "RouteDestination")
    return RouteDestination.objects.filter(route_id=route.pk).exists()


def decide_default_route(integration, *, leaving_route=None, joining_route=None, exclude_route_ids=()):
    """Return the default route ``integration`` should have.

    ``leaving_route`` / ``exclude_route_ids``: routes the integration is about to
    stop being a provider on (or that are being deleted) — never candidates.
    ``joining_route``: a route it is joining (may not be in the DB relation yet);
    when a choice has to be made and this route is among the candidates, it wins
    (§4.1 rows 1–2: "provider joins a route" → that route).

    Candidate selection prefers routes that deliver (have at least one
    destination) whenever any candidate does, regardless of whether the current
    default is set, valid, or NULL — an empty route is only chosen when none of
    the candidates deliver. ``joining_route`` then narrows within that
    preference, so an empty joining route never beats a delivering one.

    Raises ``AmbiguousDefaultRouteError`` when several routes could be the new
    default and ``joining_route`` does not disambiguate.
    """
    Route = apps.get_model("integrations", "Route")
    excluded = set(exclude_route_ids)
    if leaving_route is not None:
        excluded.add(leaving_route.pk)

    routes = {
        route.pk: route
        for route in Route.objects.filter(data_providers=integration.pk).exclude(pk__in=excluded)
    }
    if joining_route is not None and joining_route.pk not in excluded:
        routes.setdefault(joining_route.pk, joining_route)

    current_id = integration.default_route_id
    if not routes:
        # Not (or no longer) a provider: NULL is the correct value (§4.1 row 3).
        return DefaultRouteDecision(None, current_id is not None)

    current = routes.get(current_id)  # None when NULL, not a member, or leaving/excluded
    if current is not None:
        others_that_deliver = [
            route for route in routes.values()
            if route.pk != current.pk and route_has_destinations(route)
        ]
        if not others_that_deliver or route_has_destinations(current):
            return DefaultRouteDecision(current, False)  # §4 holds
        candidates = others_that_deliver  # §4 clause 3: empty default beside a delivering route
    else:
        candidates = list(routes.values())

    delivering = [c for c in candidates if route_has_destinations(c)]
    if delivering:
        candidates = delivering  # no-op when `current` was set: already delivering-only above

    if joining_route is not None and any(c.pk == joining_route.pk for c in candidates):
        candidates = [c for c in candidates if c.pk == joining_route.pk]

    if len(candidates) == 1:
        chosen = candidates[0]
        return DefaultRouteDecision(chosen, chosen.pk != current_id)
    raise AmbiguousDefaultRouteError(integration, candidates)


def resolve_default_route(integration, *, leaving_route=None, joining_route=None, exclude_route_ids=(), via=""):
    """Apply ``decide_default_route`` to the database and log the change.

    Idempotent: a second call for the same state changes nothing and logs
    nothing, so entry points that fire more than once for one logical operation
    converge. ``via`` names the entry point in the ActivityLog row.
    """
    decision = decide_default_route(
        integration,
        leaving_route=leaving_route,
        joining_route=joining_route,
        exclude_route_ids=exclude_route_ids,
    )
    if not decision.changed:
        return decision.route
    previous_id = integration.default_route_id
    integration.default_route = decision.route
    integration.save(update_fields=["default_route"])
    if decision.route is not None:
        _log_auto_assignment(integration, decision.route, previous_id, via)
    return decision.route


def reassign_default_route(collector, field, sub_objs, using):
    """``on_delete`` for ``Integration.default_route`` (replaces ``SET_NULL``).

    Runs at *collection* time, before anything is deleted. ``sub_objs`` are the
    integrations whose default is one of the routes being deleted. For each,
    decide the new default among the routes that will survive and schedule the
    update through ``collector.add_field_update`` — the same mechanism
    ``SET_NULL``/``SET()`` use.

    Why a custom on_delete rather than a pre_delete receiver alone:

    * An ambiguity is refused *here*, during ``Collector.collect()``, i.e. before
      ``Collector.delete()`` opens its ``atomic(savepoint=False)`` block. A raise
      from a ``pre_delete`` receiver happens inside that block and marks the
      caller's transaction for rollback (``TransactionManagementError`` on the
      next query), so callers could not recover and report the refusal.
    * Every route in the same delete is excluded from the candidates at once
      (``collector.data[Route]``), independent of signal ordering.

    (In Django 4.2 ``SET_NULL`` itself is lazy — ``lazy_sub_objs = True`` — so a
    reassignment made in ``pre_delete`` would in fact survive it; the collector
    race the original design assumed does not occur. The callable is kept for
    the two reasons above.)

    Integrations that are themselves being deleted in the same cascade (an
    Organization delete takes its routes and its integrations together) just get
    NULL, exactly as before. The collector may reach this field before it has
    collected the organization's integrations, so ownership is checked too.

    Raises ``AmbiguousDefaultRouteError`` (aborting the whole delete) when a
    surviving default cannot be chosen.
    """
    Route = apps.get_model("integrations", "Route")
    Integration = apps.get_model("integrations", "Integration")
    Organization = apps.get_model("organizations", "Organization")
    doomed_routes = {route.pk for route in collector.data.get(Route, ())}
    doomed_integrations = {integration.pk for integration in collector.data.get(Integration, ())}
    doomed_owners = {organization.pk for organization in collector.data.get(Organization, ())}
    for integration in sub_objs:
        if integration.pk in doomed_integrations or integration.owner_id in doomed_owners:
            collector.add_field_update(field, None, [integration])
            continue
        decision = decide_default_route(integration, exclude_route_ids=doomed_routes)
        collector.add_field_update(field, decision.route, [integration])


def _log_auto_assignment(integration, route, previous_id, via):
    ActivityLog = apps.get_model("activity_log", "ActivityLog")
    try:
        # A savepoint: on Postgres a failed INSERT aborts the surrounding
        # transaction, and this call runs inside the caller's transaction
        # (an m2m signal's atomic(savepoint=False) block, the Collector's
        # atomic, or the admin's). Without a savepoint to roll back to, a
        # logging failure would poison that transaction and fail the
        # caller's next query too — logging must never undo the repair.
        with transaction.atomic():
            ActivityLog.objects.create(
                log_level=ActivityLog.LogLevels.WARNING,
                log_type=ActivityLog.LogTypes.EVENT,
                origin=ActivityLog.Origin.PORTAL,
                integration=integration,
                value=DEFAULT_ROUTE_AUTO_ASSIGNED,
                title=f"Default route set to '{route.name}'"[:200],
                details={
                    "route_id": str(route.pk),
                    "via": via,
                    "previous_default_route_id": str(previous_id) if previous_id else None,
                },
                is_reversible=False,
            )
    except Exception:  # logging must never undo a repair
        logger.exception(
            "Could not log default route auto-assignment",
            extra={"integration_id": str(integration.pk), "route_id": str(route.pk), "via": via},
        )

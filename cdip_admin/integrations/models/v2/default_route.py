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


def _log_auto_assignment(integration, route, previous_id, via):
    ActivityLog = apps.get_model("activity_log", "ActivityLog")
    try:
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

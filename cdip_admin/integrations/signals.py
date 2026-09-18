import logging

from django.db.models import QuerySet
from django.db.models.signals import m2m_changed, post_delete, post_save, pre_delete
from django.dispatch import receiver

from .models.v2 import (
    Integration,
    IntegrationConfiguration,
    Route,
    RouteDestination,
    RouteProvider,
    resolve_default_route,
)

logger = logging.getLogger(__name__)


# IntegrationAction post-save backfill lives on the model itself
# (IntegrationAction._post_save in models/v2/models.py) to match the codebase
# convention for v2 model lifecycle hooks. The pre_delete receiver below stays
# here because the periodic-task cleanup tied to historical-model deletes
# needs to fire on signal dispatch, not the model save() path.


@receiver(pre_delete, sender=IntegrationConfiguration)
def on_integration_config_delete(sender, **kwargs):
    config = kwargs.get("instance")
    if config and config.periodic_task:
        config.periodic_task.delete()


@receiver(post_delete, sender=RouteProvider)
def disable_pull_tasks_when_no_longer_a_provider(sender, **kwargs):
    """Pause scheduled pull actions when an integration stops being a provider.

    `RouteProvider._post_save` enables an integration's periodic pull tasks when
    it's added as a provider to a route. This is the mirror image: when a
    provider link is removed (route edited via `data_providers.set(...)`, or the
    route deleted), disable those tasks if the integration is no longer a
    provider in ANY route — otherwise they keep firing pull_events /
    pull_observations on what is now a destination-only integration. See
    GUNDI-5400.

    A signal (rather than RouteProvider.delete()) is used because removals go
    through `QuerySet.delete()` on the through model, which bypasses the
    model's delete() but still dispatches post_delete.
    """
    instance = kwargs.get("instance")
    if not instance:
        return
    try:
        integration = Integration.objects.get(pk=instance.integration_id)
    except Integration.DoesNotExist:
        # The integration itself was deleted (cascade) — its tasks go with it.
        return
    if integration.is_used_as_provider:
        # Still a provider via another route; leave the tasks enabled.
        return
    for config in integration.periodic_pull_action_configurations:
        if config.periodic_task and config.periodic_task.enabled:
            config.periodic_task.enabled = False
            config.periodic_task.save()


# ---------------------------------------------------------------------------
# Default route invariant (spec: docs/superpowers/specs/2026-09-18-default-route-invariant-design.md §5.1)
#
# Django splits "a provider joined a route" in two: RouteProvider.objects.create()
# fires post_save on the through model, while route.data_providers.add()/.set()
# bulk-insert and fire only m2m_changed. Both are handled; the helper is
# idempotent so double-firing converges.
# ---------------------------------------------------------------------------

def _provider_route_pairs(instance, reverse, pk_set):
    """(integration, route) pairs for an m2m_changed event on Route.data_providers.

    reverse=False: ``instance`` is the Route and ``pk_set`` holds Integration ids.
    reverse=True: ``instance`` is the Integration and ``pk_set`` holds Route ids.
    Fresh instances are fetched so cached ``default_route`` values are not stale.
    """
    if not pk_set:
        return []
    if reverse:
        return [(instance, route) for route in Route.objects.filter(pk__in=pk_set)]
    return [(integration, instance) for integration in Integration.objects.filter(pk__in=pk_set)]


@receiver(post_save, sender=RouteProvider)
def on_route_provider_saved(sender, instance, created, raw=False, **kwargs):
    """Entry point 1 (RouteProvider.objects.create / .save)."""
    if raw or not created:
        return
    integration = Integration.objects.get(pk=instance.integration_id)
    resolve_default_route(integration, joining_route=instance.route, via="route_provider_added")


@receiver(m2m_changed, sender=RouteProvider)
def on_route_providers_m2m_changed(sender, instance, action, reverse, pk_set, **kwargs):
    """Entry points 1 and 2 for route.data_providers.add/.set/.remove/.clear and the reverse accessor.

    ``pre_remove``/``pre_clear`` (not post_*) so the relationship still exists
    and "other routes" is computable; a raised AmbiguousDefaultRouteError aborts
    the operation inside the caller's transaction.
    """
    if action == "post_add":
        for integration, route in _provider_route_pairs(instance, reverse, pk_set):
            resolve_default_route(integration, joining_route=route, via="route_provider_added")
    elif action == "pre_remove":
        for integration, route in _provider_route_pairs(instance, reverse, pk_set):
            resolve_default_route(integration, leaving_route=route, via="route_provider_removed")
    elif action == "pre_clear":
        if reverse:  # instance is the Integration: it leaves every route
            route_ids = list(instance.routing_rules_by_provider.values_list("pk", flat=True))
            resolve_default_route(instance, exclude_route_ids=route_ids, via="route_provider_removed")
        else:        # instance is the Route: every provider leaves it
            for integration in Integration.objects.filter(routing_rules_by_provider=instance):
                resolve_default_route(integration, leaving_route=instance, via="route_provider_removed")


def _reconsider_providers_of(route):
    """Entry point 1b: a route gained destinations. Any provider on it whose
    default is an empty route should now switch to this one (§4 clause 3)."""
    for integration in Integration.objects.filter(routing_rules_by_provider=route):
        resolve_default_route(integration, joining_route=route, via="route_destination_added")


@receiver(post_save, sender=RouteDestination)
def on_route_destination_saved(sender, instance, created, raw=False, **kwargs):
    if raw or not created:
        return
    _reconsider_providers_of(instance.route)


@receiver(m2m_changed, sender=RouteDestination)
def on_route_destinations_m2m_changed(sender, instance, action, reverse, pk_set, **kwargs):
    if action != "post_add":
        return
    routes = Route.objects.filter(pk__in=pk_set) if reverse else [instance]
    for route in routes:
        _reconsider_providers_of(route)


@receiver(post_save, sender=Integration)
def on_integration_saved_ensure_membership(sender, instance, raw=False, update_fields=None, **kwargs):
    """Entry point 4: ``default_route`` set directly (admin, ORM, ensure_default_route).

    An integration must be a provider on its default route (§4 clause 2), so
    add the RouteProvider row if it is missing — what ensure_default_route()
    already does for the API path. post_save (not pre_save) because the
    through-row needs the integration's PK.
    """
    if raw or instance.default_route_id is None:
        return
    if update_fields is not None and "default_route" not in update_fields:
        return
    if not RouteProvider.objects.filter(integration_id=instance.pk, route_id=instance.default_route_id).exists():
        RouteProvider.objects.create(integration=instance, route_id=instance.default_route_id)


def _origin_model(origin):
    """Model class behind ``pre_delete``'s ``origin`` (the instance or queryset
    whose .delete() started the cascade), or None."""
    if origin is None:
        return None
    if isinstance(origin, QuerySet):
        return origin.model
    return type(origin)


def _routes_leaving_in_this_delete(instance, origin):
    """Every route ``instance.integration`` is leaving in the delete that ``origin`` started.

    The Collector sends pre_delete for every RouteProvider row it collected
    BEFORE deleting any of them, so a sibling row for the same integration
    would otherwise look like a surviving route and get picked as the new
    default. Re-evaluating ``origin`` here is safe: nothing is deleted yet.
    """
    leaving = {instance.route_id}
    if isinstance(origin, QuerySet):
        if issubclass(origin.model, Route):
            leaving |= set(origin.values_list("pk", flat=True))
        elif issubclass(origin.model, RouteProvider):
            leaving |= set(
                origin.filter(integration_id=instance.integration_id).values_list("route_id", flat=True)
            )
    elif isinstance(origin, Route):
        leaving.add(origin.pk)
    return leaving


@receiver(pre_delete, sender=RouteProvider)
def on_route_provider_pre_delete(sender, instance, **kwargs):
    """Entry point 2 for RouteProvider rows deleted directly or cascaded from a Route delete.

    Only runs when the delete started at a Route or a RouteProvider. When it
    started at the Integration (or anything that cascades to it, e.g. an
    Organization) the provider itself is going away and reassigning its default
    would be pointless — and could refuse a legitimate delete.
    """
    origin_model = _origin_model(kwargs.get("origin"))
    if origin_model is Route or (origin_model is not None and issubclass(origin_model, Route)):
        via = "route_deleted"
    elif origin_model is None or issubclass(origin_model, RouteProvider):
        via = "route_provider_removed"
    else:
        return
    try:
        integration = Integration.objects.get(pk=instance.integration_id)
    except Integration.DoesNotExist:
        return
    resolve_default_route(integration, exclude_route_ids=_routes_leaving_in_this_delete(instance, kwargs.get("origin")), via=via)

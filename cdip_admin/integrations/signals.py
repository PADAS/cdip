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
    """Entry point 1 (route.data_providers.add/.set, integration.routing_rules_by_provider.add)."""
    if action == "post_add":
        for integration, route in _provider_route_pairs(instance, reverse, pk_set):
            resolve_default_route(integration, joining_route=route, via="route_provider_added")


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

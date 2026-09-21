from enum import Enum

from django.db.models import Subquery, Q, Exists, OuterRef, ExpressionWrapper, BooleanField
from datetime import timezone, timedelta, datetime
from activity_log.models import ActivityLog
from organizations.models import Organization
from accounts.utils import get_user_organizations_qs
from django.apps import apps
from .models import IntegrationStatus, HealthCheckSettings


# Enum for connection statuses
class ConnectionStatus(str, Enum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DISABLED = "disabled"
    NEEDS_REVIEW = "needs_review"


class DefaultRouteState(str, Enum):
    """Where an integration stands against the default-route invariant (spec §4).
    Only meaningful for providers; destination-only integrations are exempt."""
    VALID = "valid"
    MISSING = "missing"              # §4 clause 1: default_route is NULL
    NOT_MEMBER = "not_member"        # §4 clause 2: not a provider on its default route
    EMPTY_DEFAULT = "empty_default"  # §4 clause 3: default has no destinations while another route does


DEFAULT_ROUTE_STATUS_DETAILS = {
    DefaultRouteState.MISSING: (
        "No default route — data from this provider cannot be routed. "
        "Assign one in Admin → Integration, or run check_default_routes --fix."
    ),
    DefaultRouteState.NOT_MEMBER: (
        "Default route is not one of this provider's routes — data from this provider cannot be routed. "
        "Assign one in Admin → Integration, or run check_default_routes --fix."
    ),
    DefaultRouteState.EMPTY_DEFAULT: (
        "Default route has no destinations while another route does — data from this provider is not delivered. "
        "Assign one in Admin → Integration, or run check_default_routes --fix."
    ),
}

_DEFAULT_ROUTE_STATE_ANNOTATION = {
    DefaultRouteState.MISSING: "default_route_missing",
    DefaultRouteState.NOT_MEMBER: "default_route_not_member",
    DefaultRouteState.EMPTY_DEFAULT: "default_route_empty",
}


def annotate_default_route_state(queryset):
    """Annotate an Integration queryset with three booleans, one per §4 clause.

    Each is an Exists() subquery, so the whole thing stays one SQL statement.
    Used by the status pipeline, the admin filter and check_default_routes so
    the three cannot disagree about what "broken" means.
    """
    RouteProvider = apps.get_model("integrations", "RouteProvider")
    RouteDestination = apps.get_model("integrations", "RouteDestination")
    is_member_of_default = Exists(
        RouteProvider.objects.filter(integration_id=OuterRef("pk"), route_id=OuterRef("default_route_id"))
    )
    default_has_destinations = Exists(
        RouteDestination.objects.filter(route_id=OuterRef("default_route_id"))
    )
    some_route_has_destinations = Exists(
        RouteDestination.objects.filter(route__routeprovider__integration_id=OuterRef("pk"))
    )
    has_default = Q(default_route__isnull=False)
    return queryset.annotate(
        default_route_missing=ExpressionWrapper(Q(default_route__isnull=True), output_field=BooleanField()),
        default_route_not_member=ExpressionWrapper(has_default & ~is_member_of_default, output_field=BooleanField()),
        default_route_empty=ExpressionWrapper(
            has_default & is_member_of_default & ~default_has_destinations & some_route_has_destinations,
            output_field=BooleanField(),
        ),
    )


def _providers_only(queryset):
    return queryset.filter(routing_rules_by_provider__isnull=False).distinct()


def filter_by_default_route_state(queryset, state):
    """Restrict an Integration queryset to providers in the given state."""
    annotated = annotate_default_route_state(_providers_only(queryset))
    if state == DefaultRouteState.VALID:
        return annotated.filter(default_route_missing=False, default_route_not_member=False, default_route_empty=False)
    return annotated.filter(**{_DEFAULT_ROUTE_STATE_ANNOTATION[DefaultRouteState(state)]: True})


def providers_without_valid_default_route():
    """Providers violating §4 (any clause). One statement, no Python loop."""
    Integration = apps.get_model("integrations", "Integration")
    return annotate_default_route_state(Integration.providers.all()).filter(
        Q(default_route_missing=True) | Q(default_route_not_member=True) | Q(default_route_empty=True)
    )


def get_default_route_state(integration):
    """State of one integration, or None when it is a provider on no route (exempt)."""
    Integration = apps.get_model("integrations", "Integration")
    row = annotate_default_route_state(Integration.providers.filter(pk=integration.pk)).values(
        "default_route_missing", "default_route_not_member", "default_route_empty",
    ).first()
    if row is None:
        return None
    if row["default_route_missing"]:
        return DefaultRouteState.MISSING
    if row["default_route_not_member"]:
        return DefaultRouteState.NOT_MEMBER
    if row["default_route_empty"]:
        return DefaultRouteState.EMPTY_DEFAULT
    return DefaultRouteState.VALID


def ensure_default_route(integration, route_name=None):
    """Give `integration` a default Route, creating one if it has none.

    The name cascades route_name -> integration.name -> "<type> Route"; blank is
    not a distinct signal, so an empty Route Name field in the portal falls back
    to the connection's name. The two names are independent after creation --
    renaming one never renames the other.
    """
    # Ensure that a default routing rule group is set for integrations
    if not integration.default_route:
        # Avoid circular imports related to models
        Route = apps.get_model('integrations', 'Route')
        # Strip before testing, not after: `or` short-circuits, so a
        # whitespace-only route_name would win the chain and skip integration.name.
        given_name = (route_name or "").strip() or (integration.name or "").strip()
        # Route.name is validated with allow_blank=False so it can't be left
        # blank; 190 leaves room for the " (N)" suffix below (max_length=200).
        base_name = (given_name or f"{integration.type.name} Route")[:190]
        # (owner, name) has no unique constraint, so get_or_create would adopt an
        # unrelated route of the owner's and inherit its destinations.
        name = base_name
        collision_count = 2
        while Route.objects.filter(owner_id=integration.owner_id, name=name).exists():
            name = f"{base_name} ({collision_count})"
            collision_count += 1
        routing_rule = Route.objects.create(
            owner_id=integration.owner_id,
            name=name,
        )
        integration.default_route = routing_rule
        integration.save()
    # Add the integration a provider in its default routing rule
    if not integration.default_route.data_providers.filter(id=integration.id).exists():
        RouteProvider = apps.get_model('integrations', 'RouteProvider')
        RouteProvider.objects.create(integration=integration, route=integration.default_route)


def get_user_integrations_qs(user):
    # Return a list with the integrations that the currently authenticated user is allowed to see.
    user_organizations = get_user_organizations_qs(user=user)
    Integration = apps.get_model('integrations', 'Integration')
    integrations = Integration.objects.filter(
        owner__in=Subquery(user_organizations.values('id'))
    )
    return integrations


def get_integrations_owners_qs(integrations_qs):
    return Organization.objects.filter(
        id__in=Subquery(integrations_qs.values("owner_id"))
    )


def get_user_sources_qs(user):
    # Return a list with the devices that the currently authenticated user is allowed to see.
    integrations = get_user_integrations_qs(user=user)
    Source = apps.get_model('integrations', 'Source')
    return Source.objects.filter(integration__in=Subquery(integrations.values("id")))


def get_user_routes_qs(user):
    # Return a list with the routes that the currently authenticated user is allowed to see.
    user_organizations = get_user_organizations_qs(user=user)
    Route = apps.get_model('integrations', 'Route')
    return Route.objects.filter(owner__in=Subquery(user_organizations.values('id')))


def calculate_integration_status(integration_id):
    """
    Calculate the status of an integration based on the activity logs and other parameters
    """
    healthcheck_settings, _ = HealthCheckSettings.objects.get_or_create(integration_id=integration_id)
    integration_status, _ = IntegrationStatus.objects.get_or_create(integration_id=integration_id)
    integration_status.status = IntegrationStatus.Status.HEALTHY
    integration_status.status_details = "No issues detected"
    time_window = datetime.now(timezone.utc) - timedelta(minutes=healthcheck_settings.time_window_minutes)
    errors_threshold = healthcheck_settings.error_count_threshold
    integration = integration_status.integration

    if not integration.enabled:
        integration_status.status = IntegrationStatus.Status.DISABLED
        integration_status.status_details = "Integration is disabled"
        integration_status.save()
        return integration_status.status

    # A broken default route is the *cause* of downstream errors, so it is
    # checked before the dispatcher / error-threshold branches and names itself
    # (spec §5.2). Destination-only integrations return None here and are exempt.
    default_route_state = get_default_route_state(integration)
    if default_route_state is not None and default_route_state != DefaultRouteState.VALID:
        integration_status.status = IntegrationStatus.Status.UNHEALTHY
        integration_status.status_details = DEFAULT_ROUTE_STATUS_DETAILS[default_route_state]
        integration_status.save()
        return integration_status.status

    # When the dispatcher is in ERROR (e.g. GCP quota exhausted), short-circuit
    # to UNHEALTHY immediately rather than waiting for the activity-log error
    # threshold to accumulate. Use a queryset filter rather than the OneToOne
    # descriptor: the descriptor raises DispatcherDeployment.DoesNotExist when
    # no row exists yet (legacy/freshly-created integrations).
    DispatcherDeployment = apps.get_model("deployments", "DispatcherDeployment")
    deployment = DispatcherDeployment.objects.filter(integration=integration).first()

    if deployment and deployment.status == DispatcherDeployment.Status.ERROR:
        integration_status.status = IntegrationStatus.Status.UNHEALTHY
        if deployment.failure_reason == DispatcherDeployment.FailureReason.QUOTA_EXHAUSTED:
            integration_status.status_details = (
                "Dispatcher deployment blocked by GCP quota — Cloud Run service ceiling reached"
            )
        else:
            integration_status.status_details = "Dispatcher deployment failed"
    elif ActivityLog.objects.filter(
        origin=ActivityLog.Origin.INTEGRATION,
        integration=integration,
        log_level=ActivityLog.LogLevels.ERROR,
        created_at__gte=time_window
    ).count() >= errors_threshold:
        integration_status.status = IntegrationStatus.Status.UNHEALTHY
        integration_status.status_details = "Errors were detected while executing the integration"
    elif ActivityLog.objects.filter(
        origin=ActivityLog.Origin.DISPATCHER,
        integration=integration,
        log_level=ActivityLog.LogLevels.ERROR,
        created_at__gte=time_window
    ).count() >= errors_threshold:
        integration_status.status = IntegrationStatus.Status.UNHEALTHY
        integration_status.status_details = "Errors were detected while pushing data to the destination"
    elif healthcheck_settings.retriable_error_count_threshold and ActivityLog.objects.filter(
        origin=ActivityLog.Origin.DISPATCHER,
        integration=integration,
        log_level=ActivityLog.LogLevels.WARNING,
        value__in=("observation_delivery_failed", "observation_update_failed"),
        created_at__gte=time_window
        # Existence at offset N-1 instead of COUNT(*): warning volume is
        # unbounded during exactly the outages this branch detects
    )[healthcheck_settings.retriable_error_count_threshold - 1:].exists():
        # Retriable (transient) delivery failures are logged as warnings and don't
        # count toward the error threshold above. But a sustained volume of them
        # means the destination is down or overloaded, which must still alarm.
        # A threshold of 0 disables this check (guarded above; the N-1 offset
        # requires N >= 1).
        integration_status.status = IntegrationStatus.Status.UNHEALTHY
        integration_status.status_details = "Sustained delivery errors - destination may be down or overloaded"
    integration_status.save()
    return integration_status.status


def filter_connections_by_status(queryset, status):
    provider_disabled_q = Q(status__status=IntegrationStatus.Status.DISABLED.value)
    destinations_disabled_q = Q(
        routing_rules_by_provider__destinations__status__status=IntegrationStatus.Status.DISABLED.value)
    provider_healthy_q = Q(status__status=IntegrationStatus.Status.HEALTHY.value)
    provider_unhealthy_q = Q(status__status=IntegrationStatus.Status.UNHEALTHY.value)
    destinations_unhealthy_q = Q(
        routing_rules_by_provider__destinations__status__status=IntegrationStatus.Status.UNHEALTHY.value
    )
    connection_unhealthy_q = Q(
        provider_unhealthy_q | (destinations_unhealthy_q & ~provider_disabled_q)
    )
    connection_needs_review_q = Q(provider_healthy_q & destinations_disabled_q)
    connection_healthy_q = Q(provider_healthy_q & ~Q(destinations_unhealthy_q | destinations_disabled_q))
    if status == ConnectionStatus.UNHEALTHY.value:
        return queryset.filter(connection_unhealthy_q)
    if status == ConnectionStatus.NEEDS_REVIEW.value:
        return queryset.filter(connection_needs_review_q)
    if status == ConnectionStatus.DISABLED.value:
        return queryset.filter(provider_disabled_q)
    if status == ConnectionStatus.HEALTHY.value:
        return queryset.filter(connection_healthy_q)
    return queryset

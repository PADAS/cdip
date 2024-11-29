from enum import Enum

from django.db.models import Subquery, Q
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


def ensure_default_route(integration):
    # Ensure that a default routing rule group is set for integrations
    if not integration.default_route:
        # Avoid circular imports related to models
        Route = apps.get_model('integrations', 'Route')
        name = integration.name + " - Default Route"
        routing_rule, _ = Route.objects.get_or_create(
            owner_id=integration.owner.id,
            name=name,
        )
        integration.default_route = routing_rule
        integration.save()
    # Add the integration a provider in its default routing rule
    if not integration.default_route.data_providers.filter(id=integration.id).exists():
        integration.default_route.data_providers.add(integration)


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
    if not integration_status.integration.enabled:
        integration_status.status = IntegrationStatus.Status.DISABLED
        integration_status.status_details = "Integration is disabled"
    elif ActivityLog.objects.filter(
        origin=ActivityLog.Origin.INTEGRATION,
        integration=integration_status.integration,
        log_level=ActivityLog.LogLevels.ERROR,
        created_at__gte=time_window
    ).count() >= errors_threshold:
        integration_status.status = IntegrationStatus.Status.UNHEALTHY
        integration_status.status_details = "Errors where detected while executing the integration"
    elif ActivityLog.objects.filter(
        origin=ActivityLog.Origin.DISPATCHER,
        integration=integration_status.integration,
        log_level=ActivityLog.LogLevels.ERROR,
        created_at__gte=time_window
    ).count() >= errors_threshold:
        integration_status.status = IntegrationStatus.Status.UNHEALTHY
        integration_status.status_details = "Errors where detected while pushing data to the destination"
    integration_status.save()
    return integration_status.status


def filter_connections_by_status(queryset, status):
    provider_disabled_q = Q(status__status=IntegrationStatus.Status.DISABLED.value)
    destinations_disabled_q = Q(routing_rules_by_provider__destinations__status__status=IntegrationStatus.Status.DISABLED.value)
    destinations_unhealthy_q = Q(
        routing_rules_by_provider__destinations__status__status=IntegrationStatus.Status.UNHEALTHY.value
    )
    connection_unhealthy_q = Q(
        Q(status__status=IntegrationStatus.Status.UNHEALTHY.value) | destinations_unhealthy_q
    )
    provider_healthy_q = Q(status__status=IntegrationStatus.Status.HEALTHY.value)
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

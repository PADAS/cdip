from django.db.models import Subquery
from organizations.models import Organization
from accounts.utils import get_user_organizations_qs
from django.apps import apps


def ensure_default_route(integration):
    # Ensure that a default routing rule group is set for integrations
    if not integration.default_route:
        # Avoid circular imports related to models
        RoutingRule = apps.get_model('integrations', 'RoutingRule')
        name = integration.name + " - Default Route"
        routing_rule, _ = RoutingRule.objects.get_or_create(
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

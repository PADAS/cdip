from django.db.models import Subquery

from accounts.utils import get_user_organizations_qs
from .models import Integration, IntegrationType, RoutingRule


def ensure_default_routing_rule(integration):
    # Ensure that a default routing rule group is set for integrations
    if not integration.default_routing_rule:
        name = integration.name + " - Default Route"
        routing_rule, _ = RoutingRule.objects.get_or_create(
            owner_id=integration.owner.id,
            name=name,
        )
        integration.default_routing_rule = routing_rule
        integration.save()
    # Add the integration a provider in its default routing rule
    if not integration.default_routing_rule.data_providers.filter(id=integration.id).exists():
        integration.default_routing_rule.data_providers.add(integration)


def get_user_integrations_qs(user):
    # Return a list with the integrations that the currently authenticated user is allowed to see.
    user_organizations = get_user_organizations_qs(user=user)
    integrations = Integration.objects.filter(
        owner__in=Subquery(user_organizations.values('id'))
    )
    return integrations

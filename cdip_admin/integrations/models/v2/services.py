from .models import RoutingRuleType, RoutingRule


def ensure_default_routing_rule(integration):
    # Ensure that a default routing rule group is set for integrations
    if not integration.default_routing_rule:
        name = integration.name + " - Default Route"
        default_routing_type, _ = RoutingRuleType.objects.get_or_create(
            value="default_routing_type",
            name="Default Routing Type"
        )
        routing_rule, _ = RoutingRule.objects.get_or_create(
            owner_id=integration.owner.id,
            name=name,
            type=default_routing_type
        )
        integration.default_routing_rule = routing_rule
        integration.save()
    # Add the integration a provider in its default routing rule
    if not integration.default_routing_rule.data_providers.filter(id=integration.id).exists():
        integration.default_routing_rule.data_providers.add(integration)

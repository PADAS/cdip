from django.db import migrations


def backfill_routeconfiguration_owner(apps, schema_editor):
    # Pre-GUNDI-5698, a RouteConfiguration carried no owner and could be
    # attached to a Route from any organization. This assigns each existing
    # config the owner of its first referencing Route (by id, for a
    # deterministic pick), so the organization-scoping check added to
    # RouteCreateUpdateSerializer.validate_configuration has something to
    # compare against. Configs already referenced by routes from more than
    # one organization are a real pre-existing cross-org share -- the first
    # route's owner wins and the rest are reported below for a human to
    # review, since from this migration alone there's no way to tell which
    # side the sharing was intentional on.
    RouteConfiguration = apps.get_model("integrations", "RouteConfiguration")

    linked = 0
    orphaned = 0
    cross_org = []

    for config in RouteConfiguration.objects.filter(owner__isnull=True).iterator():
        routes = list(
            config.routing_rules_by_configuration.order_by("id").select_related("owner")
        )
        if not routes:
            orphaned += 1
            continue
        owners = {route.owner_id for route in routes}
        if len(owners) > 1:
            cross_org.append((config.id, [(r.id, r.owner_id) for r in routes]))
        config.owner_id = routes[0].owner_id
        config.save(update_fields=["owner"])
        linked += 1

    print(
        f"\nRouteConfiguration owner backfill: {linked} linked, "
        f"{orphaned} left unowned (no referencing route), "
        f"{len(cross_org)} pre-existing cross-org shares found."
    )
    if cross_org:
        print(
            "Cross-org shares (config_id -> [(route_id, route_owner_id), ...]) "
            "-- the first route's owner was kept; review the others:"
        )
        for config_id, routes in cross_org:
            print(f"  {config_id} -> {routes}")


class Migration(migrations.Migration):

    dependencies = [
        ("integrations", "0119_routeconfiguration_owner"),
    ]

    operations = [
        migrations.RunPython(
            backfill_routeconfiguration_owner,
            reverse_code=migrations.RunPython.noop,
        ),
    ]

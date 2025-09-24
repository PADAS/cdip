import copy
import json
import logging

from datetime import datetime, timezone
from collections import defaultdict
from django.core.management.base import BaseCommand
from django.db import transaction

from integrations.models import (
    Organization,
    Integration,
    IntegrationType,
    IntegrationAction,
    IntegrationConfiguration,
    Route,
    RouteConfiguration
)


DEFAULT_FIELD_MAPPING = {"default": "", "destination_field": "provider_key"}


class Command(BaseCommand):

    help = "Vectronic v1 plugins migration script (to Gundi v2)"

    def add_arguments(self, parser):
        parser.add_argument(
            '--sites',
            nargs='+',
            type=str,
            required=False,
            help='List of ER sites to read and migrate plugins from'
        )
        parser.add_argument(
            "--max",
            type=int,
            default=10,
            required=False,
            help="Specify the maximum number of plugins to migrate",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            default=False,
            help="If present, migrate all the plugins, regardless of the other option"
        )

    def handle(self, *args, **options):

        # TODO: FOR LOCAL EXECUTION ONLY! Remove if running in pod
        logging.getLogger('django.db.backends').setLevel(logging.WARNING)
        logging.getLogger('activity_log.mixins').setLevel(logging.ERROR)
        logging.getLogger('integrations.tasks').setLevel(logging.WARNING)

        self.stdout.write(f" -- Starting Vectronic v1 plugins migration script -- \n\n")
        if plugins_to_migrate := self._get_plugins(options=options):
            try:
                vectronic_integration_type = IntegrationType.objects.get(
                    value="vectronic"
                )
            except IntegrationType.DoesNotExist:
                self.stdout.write(f" -- Vectronic integration type does not exist in Gundi v2 -- ")
                return

            try:
                v2_action = IntegrationAction.objects.get(
                    value="pull_observations",
                    integration_type=vectronic_integration_type
                )
            except IntegrationAction.DoesNotExist:
                self.stdout.write(f" -- Vectronic 'pull_observations' action does not exist in Gundi v2 -- ")
                return

            v2_integrations_created = 0
            v2_integrations_skipped = 0
            v2_integrations_with_error = 0
            v2_integration_configs_created = 0
            destination_integration_created = 0

            # Read destinations JSON
            with open('er-prod.gundi-tokens.json', 'r') as f:
                destinations_data = json.load(f)

            for tenant_site, collars in plugins_to_migrate.items():
                self.stdout.write(f"\n -- Got {len(collars)} collars for {tenant_site} site to migrate -- \n\n")
                try:
                    with transaction.atomic():
                        formatted_tenant_site = f"https://{tenant_site}"
                        vectronic_plugin_names = set([c["vectronic_plugin_name"] for c in collars])
                        provider_keys = set([c["provider_key"] for c in collars])

                        plugin_owner = Integration.objects.filter(
                            type__value="earth_ranger",
                            base_url=formatted_tenant_site
                        ).first()

                        if not plugin_owner:
                            self.stdout.write(f"\n -- WARNING: No Earthranger site found for {tenant_site} in Gundi v2, will use Gundi org as owner -- ")
                            plugin_owner = Organization.objects.get(
                                name="----- [Internal] Gundi"
                            )
                        else:
                            plugin_owner = plugin_owner.owner

                        integration, created = Integration.objects.get_or_create(
                            type=vectronic_integration_type,
                            name=f"[V1 to V2] - Vectronic - {formatted_tenant_site} (Plugins: {', '.join(vectronic_plugin_names)})",
                            owner=plugin_owner
                        )
                        if created:
                            # New integration created
                            v2_integrations_created += 1
                            self.stdout.write(f" -- Created new integration: {integration.name} (ID: {integration.id}) from v1 plugin -- ")

                            # Get or create the pull_observations action config for this integration
                            action_config, created = IntegrationConfiguration.objects.get_or_create(
                                integration=integration,
                                action=v2_action
                            )
                            if created:
                                # Create collars dict to be stored in config
                                collars_list = []
                                for collar in collars:
                                    if not collar["collar_key"]:
                                        self.stdout.write(f"\n -- WARNING: Collar {collar['manufacturer_id']} has no collar key, will create it as 'N/A'... -- ")
                                    collars_list.append({
                                        "name": "Migrated Plugin",
                                        "parsedData": {
                                            "collarID": collar["manufacturer_id"],
                                            "collarType": "N/A",
                                            "comType": "N/A",
                                            "comID": "N/A",
                                            "key": collar.get("collar_key", "N/A"),
                                        },
                                        "uploadDate": datetime.now(tz=timezone.utc).strftime("%m/%d/%Y, %I:%M:%S %p")
                                    })
                                action_config.data = {"files": json.dumps(collars_list), "default_lookback_hours": 12}
                                action_config.save()
                                v2_integration_configs_created += 1
                                self.stdout.write(f" -- Created new configuration for action '{v2_action.name}' for integration: {integration.name} (ID: {integration.id})")

                            # Get or create integration route
                            route_name = f"{integration.name} - Default Route"
                            routing_rule, _ = Route.objects.get_or_create(
                                name=route_name,
                                owner=plugin_owner
                            )

                            # Set routing rule for the integration and add provider
                            integration.default_route = routing_rule
                            integration.default_route.data_providers.add(integration)

                            field_mappings = {
                                str(integration.id): {
                                    "obv": {}
                                }
                            }

                            er_integration_type = IntegrationType.objects.get(
                                value="earth_ranger"
                            )

                            destination_integration, created = Integration.objects.get_or_create(
                                type=er_integration_type,
                                owner=plugin_owner,
                                base_url=formatted_tenant_site,
                                name=f"{plugin_owner.name} - {formatted_tenant_site} (For Vectronic)"
                            )
                            if created:
                                destination_integration_created += 1

                                # Create AUTH action config for the destination integration (ER)
                                er_auth_action = IntegrationAction.objects.get(
                                    type=IntegrationAction.ActionTypes.AUTHENTICATION,
                                    name="Auth",
                                    value="auth",
                                    description="Earth Ranger Auth action",
                                    integration_type=er_integration_type
                                )

                                # Get destination from destinations_data JSON
                                destination = next(
                                    (d for d in destinations_data if d.get("tenant_domain") == tenant_site),
                                    None
                                )

                                if not destination:
                                    self.stdout.write(f"\n -- WARNING: No destination found for {tenant_site} in destinations JSON, will create destination without credentials -- ")
                                else:
                                    er_auth_config, created = IntegrationConfiguration.objects.get_or_create(
                                        integration=destination_integration,
                                        action=er_auth_action,
                                        data={"token": destination["gundi_token"], "authentication_type": "token"}
                                    )
                                    if created:
                                        self.stdout.write(f" -- Created new configuration for action '{er_auth_action.name}' for destination integration: {destination_integration.name} (ID: {destination_integration.id})")

                                self.stdout.write(f" -- Created new integration: {destination_integration.name} (ID: {destination_integration.id}) for site: {formatted_tenant_site} -- ")

                            integration.default_route.destinations.add(destination_integration)

                            # add legacy provider_key field mapping
                            for provider_key in provider_keys:
                                inbound_field_mapping = copy.deepcopy(DEFAULT_FIELD_MAPPING)
                                inbound_field_mapping["default"] = provider_key

                                field_mappings[str(integration.id)]["obv"][str(destination_integration.id)] = inbound_field_mapping

                            field_mappings_result = {
                                "field_mappings": field_mappings
                            }
                            route_config, _ = RouteConfiguration.objects.get_or_create(
                                name=integration.default_route.name + " - Default Configuration",
                                defaults={
                                    "data": field_mappings_result
                                }
                            )
                            integration.default_route.configuration = route_config
                            integration.default_route.save()
                            integration.save()

                            self.stdout.write(f" -- Integration {integration.name} (ID: {integration.id}) was migrated correctly for tenant site {formatted_tenant_site}. Collars migrated: {len(collars)} -- \n")
                        else:
                            v2_integrations_skipped += 1
                            self.stdout.write(f" -- Integration {integration.name} (ID: {integration.id}) already exists, skipping creation... -- \n")

                except Exception as e:
                    v2_integrations_with_error += 1
                    self.stderr.write(f" -- ERROR migrating {len(collars)} collars from tenant site {formatted_tenant_site}: {e}")

            self.stdout.write(f"\n -- Summary -- \n\n")
            self.stdout.write(f" -- Vectronic Integrations with error: {v2_integrations_with_error} -- ")
            self.stdout.write(f" -- Vectronic Integrations skipped: {v2_integrations_skipped} -- ")
            self.stdout.write(f" -- Vectronic Integrations created: {v2_integrations_created} -- ")
            self.stdout.write(f" -- Vectronic Integration Configurations created: {v2_integration_configs_created} -- \n\n")
            self.stdout.write(f" -- Destination Integrations created: {destination_integration_created} -- ")

    def _get_plugins(self, options):
        with open('er-prod.vectronic.json', 'r') as f:
            plugins_data = json.load(f)

        plugins_grouped_by_tenant = defaultdict(list)
        for d in plugins_data:
            domain = d.get('tenant_domain')
            plugins_grouped_by_tenant[domain].append(d)

        plugins_grouped_by_tenant = dict(plugins_grouped_by_tenant)

        for domain, dicts in plugins_grouped_by_tenant.items():
            unique_dicts = sorted(
                (json.loads(s) for s in {json.dumps(d, sort_keys=True) for d in dicts}),
                key=lambda d: d.get('collar_key')
            )
            plugins_grouped_by_tenant[domain] = unique_dicts

        for tenant, plugins in plugins_grouped_by_tenant.items():
            self.stdout.write(f" -- Found {len(plugins)} unique collars for tenant {tenant} -- ")

        if options["all"]:
            self.stdout.write(f"\n -- Migrating ALL tenant sites plugins as per --all option -- ")
            return plugins_grouped_by_tenant

        if options["sites"]:
            self.stdout.write(f"\n -- Migrating tenant sites {options['sites']} -- ")
            selected_tenants = set(options["sites"])
            filtered_plugins = {k: v for k, v in plugins_grouped_by_tenant.items() if k in selected_tenants}
            return filtered_plugins

        return plugins_grouped_by_tenant

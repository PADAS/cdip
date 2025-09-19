import copy

from django.core.management.base import BaseCommand
from django.db import transaction

from integrations.models import (
    Organization,
    Integration,
    IntegrationType,
    IntegrationAction,
    IntegrationConfiguration,
    Route,
    RouteConfiguration,
    BridgeIntegrationType,
    BridgeIntegration
)


DEFAULT_FIELD_MAPPING = {"default": "", "destination_field": "provider_key"}


class Command(BaseCommand):

    help = "Garmin InReach v1 integrations migration script (to Gundi v2)"

    def add_arguments(self, parser):
        parser.add_argument(
            '--inbounds',
            nargs='+',
            type=str,
            required=False,
            help='List of Garmin InReach v1 integration inbounds IDs to migrate'
        )
        parser.add_argument(
            "--max",
            type=int,
            default=10,
            required=False,
            help="Specify the maximum number of inbounds to migrate",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            default=False,
            help="If present, migrate all the selected Garmin InReach v1 inbounds, regardless of the other option"
        )

    def handle(self, *args, **options):
        inbound_type = "Garmin InReach"
        self.stdout.write(f" -- Starting {inbound_type} v1 migration script -- \n\n")
        if inbounds_to_migrate := self._get_v1_bridge_integrations(options=options):

            # Step 1: InReach to ER
            inreach_integration_type = "inreach"
            try:
                inreach_v2_integration_type = IntegrationType.objects.get(
                    value=inreach_integration_type
                )
            except IntegrationType.DoesNotExist:
                self.stdout.write(f" -- Selected integration type {inreach_integration_type} does not exist in Gundi v2 -- ")
                return

            # Get AUTH v2 action
            inreach_auth_action_value = "auth"
            try:
                inreach_v2_auth_action = IntegrationAction.objects.get(
                    value=inreach_auth_action_value,
                    integration_type=inreach_v2_integration_type
                )
            except IntegrationAction.DoesNotExist:
                self.stdout.write(
                    f" -- Selected action {inreach_auth_action_value} does not exist in Gundi v2 for {inreach_integration_type} -- ")
                return

            # Get PUSH v2 action
            inreach_push_action_value = "push_messages"
            try:
                inreach_v2_push_action = IntegrationAction.objects.get(
                    value=inreach_push_action_value,
                    integration_type=inreach_v2_integration_type
                )
            except IntegrationAction.DoesNotExist:
                self.stdout.write(
                    f" -- Selected action {inreach_push_action_value} does not exist in Gundi v2 for {inreach_integration_type} -- ")
                return

            inreach_er_integrations_created = 0
            inreach_er_integrations_skipped = 0
            inreach_er_integrations_with_error = 0
            inreach_er_integration_configs_created = 0
            inreach_er_destination_owners_created = 0
            inreach_er_destination_integration_created = 0

            # Step 2: ER to InReach
            er_integration_type = "api_push" # API PUSH
            try:
                er_v2_integration_type = IntegrationType.objects.get(
                    value=er_integration_type
                )
            except IntegrationType.DoesNotExist:
                self.stdout.write(f" -- Selected integration type {er_integration_type} does not exist in Gundi v2 -- ")
                return

            # Get PULL v2 action
            er_pull_action_value = "receive_data"
            try:
                er_v2_pull_action = IntegrationAction.objects.get(
                    value=er_pull_action_value,
                    integration_type=er_v2_integration_type
                )
            except IntegrationAction.DoesNotExist:
                self.stdout.write(
                    f" -- Selected action {er_pull_action_value} does not exist in Gundi v2 for {er_integration_type} -- ")
                return

            er_inreach_integrations_created = 0
            er_inreach_integrations_skipped = 0
            er_inreach_integrations_with_error = 0
            er_inreach_integration_configs_created = 0
            er_inreach_destination_integration_created = 0

            self.stdout.write(f" -- Got {len(inbounds_to_migrate)} {inbound_type} inbounds to migrate -- \n\n")

            for inbound in inbounds_to_migrate:
                try:
                    with transaction.atomic():
                        inbound_owner, _ = Organization.objects.get_or_create(
                            name=inbound.owner.name
                        )

                        self.stdout.write(f" -- Step 1: Inreach to ER -- \n\n")
                        integration, created = Integration.objects.get_or_create(
                            type=inreach_v2_integration_type,
                            name=f"[V1 to V2] - {inbound.name} (InReach to ER)",
                            owner=inbound_owner
                        )
                        if created:
                            # New integration created
                            inreach_er_integrations_created += 1
                            self.stdout.write(f" -- Created new integration: {integration.name} (ID: {integration.id}) from v1 inbound -- ")

                            # Get or create the AUTH action config for this integration
                            inreach_auth_action_config, created = IntegrationConfiguration.objects.get_or_create(
                                integration=integration,
                                action=inreach_v2_auth_action
                            )
                            if created:
                                inreach_er_integration_configs_created += 1
                                self.stdout.write(f" -- Created new configuration for action '{inreach_v2_auth_action.name}' for integration: {integration.name} (ID: {integration.id})")

                            # Get or create the PUSH action config for this integration
                            inreach_push_action_config, created = IntegrationConfiguration.objects.get_or_create(
                                integration=integration,
                                action=inreach_v2_push_action
                            )
                            if created:
                                inreach_er_integration_configs_created += 1
                                self.stdout.write(
                                    f" -- Created new configuration for action '{inreach_v2_push_action.name}' for integration: {integration.name} (ID: {integration.id})")

                            # Get or create integration route
                            route_name = f"{integration.name} - Default Route"
                            routing_rule, _ = Route.objects.get_or_create(
                                name=route_name,
                                owner=inbound_owner
                            )

                            # Set routing rule for the integration and add provider
                            integration.default_route = routing_rule
                            integration.default_route.data_providers.add(integration)

                            field_mappings = {
                                str(integration.id): {
                                    "obv": {}
                                }
                            }

                            # Read ER destination info from additional
                            er_site = inbound.additional.get("er_site")
                            if "https://" not in er_site:
                                er_site = "https://" + er_site
                            er_token = inbound.additional.get("er_token")
                            er_source_provider = inbound.additional.get("er_source_provider")

                            try:
                                destination_integration_type, created = IntegrationType.objects.get_or_create(
                                    value="earth_ranger"
                                )
                            except IntegrationType.DoesNotExist:
                                self.stdout.write(
                                    " -- ER destination integration type does not exist in Gundi v2 -- ")
                                return

                            # Check if outbound owner exists as organization
                            destination_owner, created = Organization.objects.get_or_create(
                                name=inbound.owner.name
                            )
                            if created:
                                inreach_er_destination_owners_created += 1
                                self.stdout.write(f" -- Created new organization: {destination_owner.name} for destination: {er_site}")

                            # Remove the /api/v1.0 part from the base URL
                            er_site = er_site.replace(
                                "/api/v1.0", ""
                            )

                            destination_integration, created = Integration.objects.get_or_create(
                                type=destination_integration_type,
                                owner=destination_owner,
                                base_url=er_site,
                                name=f"{destination_owner.name} - Earthranger ({er_site}) (Inbound: {inbound.name})"
                            )
                            if created:
                                inreach_er_destination_integration_created += 1

                                # Create AUTH action config for the destination integration (ER)
                                try:
                                    er_auth_action, created = IntegrationAction.objects.get_or_create(
                                        type=IntegrationAction.ActionTypes.AUTHENTICATION,
                                        name="Auth",
                                        value="auth",
                                        description="Earth Ranger Auth action",
                                        integration_type=destination_integration_type
                                    )
                                except IntegrationAction.DoesNotExist:
                                    self.stdout.write(
                                        f" -- ER destination auth action does not exist in Gundi v2 -- ")
                                    return

                                er_auth_config, created = IntegrationConfiguration.objects.get_or_create(
                                    integration=destination_integration,
                                    action=er_auth_action,
                                    data={"token": er_token, "authentication_type": "token"}
                                )
                                if created:
                                    self.stdout.write(f" -- Created new configuration for action '{er_auth_action.name}' for destination integration: {destination_integration.name} (ID: {destination_integration.id})")

                                self.stdout.write(f" -- Created new integration: {destination_integration.name} (ID: {destination_integration.id}) for destination: {er_site}")

                            integration.default_route.destinations.add(destination_integration)

                            # add legacy provider_key field mapping
                            inbound_field_mapping = copy.deepcopy(DEFAULT_FIELD_MAPPING)
                            inbound_field_mapping["default"] = er_source_provider

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

                            self.stdout.write(f" -- Integration {integration.name} (ID: {integration.id}) was migrated correctly from inbound ID {inbound.id}... -- \n\n")
                        else:
                            er_inreach_integrations_skipped += 1
                            self.stdout.write(f" -- Integration {integration.name} (ID: {integration.id}) already exists, skipping creation... -- \n\n")

                except Exception as e:
                    inreach_er_integrations_with_error += 1
                    self.stderr.write(f"\n\n -- ERROR migrating {inbound.name} (ID: {inbound.id}): {e} -- \n\n")

                try:
                    with transaction.atomic():
                        self.stdout.write(f" -- Step 2: ER to Inreach -- \n\n")
                        integration, created = Integration.objects.get_or_create(
                            type=er_v2_integration_type,
                            name=f"[V1 to V2] - {inbound.name} (ER to InReach)",
                            owner=inbound_owner
                        )
                        if created:
                            # New integration created
                            er_inreach_integrations_created += 1
                            self.stdout.write(
                                f" -- Created new integration: {integration.name} (ID: {integration.id}) from v1 inbound -- ")

                            # Get or create the PULL action config for this integration
                            er_pull_action_config, created = IntegrationConfiguration.objects.get_or_create(
                                integration=integration,
                                action=er_v2_pull_action
                            )
                            if created:
                                er_inreach_integration_configs_created += 1
                                self.stdout.write(
                                    f" -- Created new configuration for action '{er_v2_pull_action.name}' for integration: {integration.name} (ID: {integration.id})")

                            # Get or create integration route
                            route_name = f"{integration.name} - Default Route"
                            routing_rule, _ = Route.objects.get_or_create(
                                name=route_name,
                                owner=inbound_owner
                            )

                            # Set routing rule for the integration and add provider
                            integration.default_route = routing_rule
                            integration.default_route.data_providers.add(integration)

                            # Read InReach destination info from additional
                            inreach_url = inbound.additional.get("inreach_url")
                            inreach_username = inbound.additional.get("inreach_username")
                            inreach_password = inbound.additional.get("inreach_password")

                            destination_integration, created = Integration.objects.get_or_create(
                                type=inreach_v2_integration_type,
                                owner=destination_owner,
                                base_url=inreach_url,
                                name=f"{destination_owner.name} - inReach ({inreach_username}) (Inbound: {inbound.name})"
                            )
                            if created:
                                er_inreach_destination_integration_created += 1

                                inreach_auth_config, created = IntegrationConfiguration.objects.get_or_create(
                                    integration=destination_integration,
                                    action=inreach_v2_auth_action,
                                    data={
                                        "api_url": inreach_url,
                                        "password": inreach_password,
                                        "username": inreach_username
                                    }
                                )
                                if created:
                                    self.stdout.write(
                                        f" -- Created new configuration for action '{inreach_v2_auth_action.name}' for destination integration: {destination_integration.name} (ID: {destination_integration.id})")

                            integration.default_route.destinations.add(destination_integration)

                            integration.default_route.save()
                            integration.save()

                            self.stdout.write(
                                f" -- Integration {integration.name} (ID: {integration.id}) was migrated correctly from inbound ID {inbound.id}... -- \n\n")
                        else:
                            inreach_er_integrations_skipped += 1
                            self.stdout.write(f" -- Integration {integration.name} (ID: {integration.id}) already exists, skipping creation... -- \n\n")

                except Exception as e:
                    er_inreach_integrations_with_error += 1
                    self.stderr.write(f"\n\n -- ERROR migrating {inbound.name} (ID: {inbound.id}): {e} -- \n\n")

            self.stdout.write(f"\n -- Summary -- \n\n")
            self.stdout.write(f" -- InReach - ER Integrations with error: {inreach_er_integrations_with_error} -- ")
            self.stdout.write(f" -- InReach - ER Integrations skipped: {inreach_er_integrations_skipped} -- ")
            self.stdout.write(f" -- InReach - ER Integrations created: {inreach_er_integrations_created} -- ")
            self.stdout.write(f" -- InReach - ER Integration Configurations created: {inreach_er_integration_configs_created} -- \n\n")

            self.stdout.write(f" -- ER - InReach Integrations with error: {er_inreach_integrations_with_error} -- ")
            self.stdout.write(f" -- ER - InReach Integrations skipped: {er_inreach_integrations_skipped} -- ")
            self.stdout.write(f" -- ER - InReach Integrations created: {er_inreach_integrations_created} -- ")
            self.stdout.write(f" -- ER - InReach Integration Configurations created: {er_inreach_integration_configs_created} -- \n\n")

    def _get_v1_bridge_integrations(self, options):
        inbound_slug = "er_inreach"
        try:
            inbound_type = BridgeIntegrationType.objects.get(
                slug=inbound_slug
            )
        except BridgeIntegrationType.DoesNotExist:
            self.stdout.write(f" -- ERROR: {inbound_slug.capitalize()} Inbound Integration Type not found -- \n")
            return []

        inbounds = BridgeIntegration.objects.filter(type=inbound_type).all()

        self.stdout.write(f" -- Found {inbounds.count()} {inbound_slug.capitalize()} inbounds -- ")

        if options["all"]:
            self.stdout.write(f" -- Migrating ALL {inbound_slug.capitalize()} inbounds as per --all option -- ")
            return inbounds

        if options['inbounds']:
            self.stdout.write(f" -- Filtering {inbound_slug.capitalize()} inbounds by IDs: {options['inbounds']} -- ")
            inbounds = inbounds.filter(id__in=options['inbounds'])

        if not inbounds:
            self.stdout.write(f" -- ERROR: {inbound_slug.capitalize()} Integrations with IDs {options['inbounds']} not found -- \n")
            return []

        if options['max']:
            self.stdout.write(f" -- Limiting to {options['max']} {inbound_slug.capitalize()} inbounds as per --max option -- ")
            inbounds = inbounds[:options['max']]

        return inbounds

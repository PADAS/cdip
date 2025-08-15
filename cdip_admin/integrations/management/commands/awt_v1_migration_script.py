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
    InboundIntegrationType,
    InboundIntegrationConfiguration
)


ER_DESTINATION_JSON_SCHEMA = {
	"if": {
		"properties": {
			"authentication_type": {
				"const": "token"
			}
		}
	},
	"else": {
		"required": ["username", "password"],
		"properties": {
			"password": {
				"type": "string",
				"title": "Password",
				"format": "password",
				"default": "",
				"example": "mypasswd1234abc",
				"writeOnly": True,
				"description": "Password used to authenticate against Earth Ranger API"
			},
			"username": {
				"type": "string",
				"title": "Username",
				"default": "",
				"example": "myuser",
				"description": "Username used to authenticate against Earth Ranger API"
			}
		}
	},
	"then": {
		"required": ["token"],
		"properties": {
			"token": {
				"type": "string",
				"title": "Token",
				"format": "password",
				"default": "",
				"example": "1b4c1e9c-5ee0-44db-c7f1-177ede2f854a",
				"writeOnly": True,
				"description": "Token used to authenticate against Earth Ranger API"
			}
		}
	},
	"type": "object",
	"title": "AuthenticateConfig",
	"properties": {
		"authentication_type": {
			"allOf": [{
				"$ref": "#/definitions/ERAuthenticationType"
			}],
			"default": "token",
			"description": "Type of authentication to use."
		}
	},
	"definitions": {
		"ERAuthenticationType": {
			"enum": ["token", "username_password"],
			"type": "string",
			"title": "ERAuthenticationType",
			"description": "An enumeration."
		}
	},
	"is_executable": True
}

ER_DESTINATION_UI_SCHEMA = {"ui:order": ["authentication_type", "token", "username", "password"]}
DEFAULT_FIELD_MAPPING = {"default": "awt", "destination_field": "provider_key"}


class Command(BaseCommand):

    help = "AWT v1 integrations migration script (to Gundi v2)"

    def add_arguments(self, parser):
        parser.add_argument(
            '--inbounds',
            nargs='+',
            type=str,
            required=False,
            help='List of AWT integration inbounds IDs to migrate'
        )
        parser.add_argument(
            "--max",
            type=int,
            default=10,
            required=False,
            help="Specify the maximum number of inbounds to migrate",
        )

    def handle(self, *args, **options):
        self.stdout.write(" -- Starting AWT v1 migration script -- \n\n")
        if inbounds_to_migrate := self._get_awt_inbounds(options=options):
            awt_integrations_created = 0
            awt_integrations_skipped = 0
            awt_integrations_with_error = 0
            awt_integration_configs_created = 0
            destination_integration_types_created = 0
            destination_owners_created = 0
            destination_integration_created = 0

            self.stdout.write(f" -- Got {len(inbounds_to_migrate)} AWT inbounds to migrate -- \n\n")

            # Get or create AWT PUSH integration type
            awt_integration_type, _ = IntegrationType.objects.get_or_create(
                name="Africa Wildlife Tracking (Animal Tracker)  [Data Push]",
                value="awt_push_v2"
            )
            # Get or create AWT PUSH action
            awt_push_action, _ = IntegrationAction.objects.get_or_create(
                type=IntegrationAction.ActionTypes.PULL_DATA,
                name="AWT Push",
                value="awt_push_action",
                integration_type=awt_integration_type
            )

            for inbound in inbounds_to_migrate:
                try:
                    with transaction.atomic():
                        inbound_owner, _ = Organization.objects.get_or_create(
                            name=inbound.owner.name
                        )
                        integration, created = Integration.objects.get_or_create(
                            type=awt_integration_type,
                            name=f"[AWT DATA PUSH] - {inbound.name}",
                            owner=inbound_owner,
                            defaults={
                                "base_url": inbound.endpoint,
                                "enabled": False,  # disabled by default for validation purposes
                            }
                        )
                        if created:
                            # New integration created
                            awt_integrations_created += 1
                            self.stdout.write(f" -- Created new integration: {integration.name} (ID: {integration.id}) from v1 inbound -- ")

                            # Get or create the AWT_PUSH action config for this integration
                            action_config, created = IntegrationConfiguration.objects.get_or_create(
                                integration=integration,
                                action=awt_push_action
                            )
                            if created:
                                awt_integration_configs_created += 1
                                self.stdout.write(f" -- Created new configuration for action '{awt_push_action.name}' for integration: {integration.name} (ID: {integration.id})")

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

                            # Read inbound destinations and create integration for each
                            for destination in inbound.destinations.all():
                                if not destination.is_er_site:
                                    self.stdout.write(f" -- Skipping destination {destination.name} (ID: {destination.id}) as it is not an ER site -- ")
                                    continue

                                # Check if outbound type exists as integration type
                                destination_integration_type, created = IntegrationType.objects.get_or_create(
                                    value=destination.type.slug
                                )
                                if created:
                                    destination_integration_types_created += 1
                                    self.stdout.write(f" -- Created new integration type: {destination_integration_type.value} for destination: {destination.name} (ID: {destination.id})")

                                # Check if outbound owner exists as organization
                                destination_owner, created = Organization.objects.get_or_create(
                                    name=destination.owner.name
                                )
                                if created:
                                    destination_owners_created += 1
                                    self.stdout.write(f" -- Created new organization: {destination_owner.name} for destination: {destination.name} (ID: {destination.id})")

                                # Remove the /api/v1.0 part from the base URL
                                destination.endpoint = destination.endpoint.replace(
                                    "/api/v1.0", ""
                                )

                                destination_integration, created = Integration.objects.get_or_create(
                                    type=destination_integration_type,
                                    owner=destination_owner,
                                    base_url=destination.endpoint,
                                    defaults={
                                        "name": destination.name
                                    }
                                )
                                if created:
                                    destination_integration_created += 1

                                    # Create AUTH action config for the destination integration (ER)
                                    er_auth_action, created = IntegrationAction.objects.get_or_create(
                                        type=IntegrationAction.ActionTypes.AUTHENTICATION,
                                        name="Auth",
                                        value="auth",
                                        description="Earth Ranger Auth action",
                                        integration_type=destination_integration_type
                                    )
                                    if created:
                                        er_auth_action.schema = ER_DESTINATION_JSON_SCHEMA
                                        er_auth_action.ui_schema = ER_DESTINATION_UI_SCHEMA
                                        er_auth_action.save()
                                        self.stdout.write(f" -- Created new action: {er_auth_action.name} for destination integration type: {destination_integration_type.value} -- ")

                                    er_auth_config, created = IntegrationConfiguration.objects.get_or_create(
                                        integration=destination_integration,
                                        action=er_auth_action,
                                        data={"token": destination.token, "authentication_type": "token"}
                                    )
                                    if created:
                                        self.stdout.write(f" -- Created new configuration for action '{er_auth_action.name}' for destination integration: {destination_integration.name} (ID: {destination_integration.id})")

                                    self.stdout.write(f" -- Created new integration: {destination_integration.name} (ID: {destination_integration.id}) for destination: {destination.name} (ID: {destination.id})")

                                integration.default_route.destinations.add(destination_integration)

                                field_mappings[str(integration.id)]["obv"][str(destination_integration.id)] = DEFAULT_FIELD_MAPPING

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
                        else:
                            awt_integrations_skipped += 1
                            self.stdout.write(f" -- Integration {integration.name} (ID: {integration.id}) already exists, skipping creation... -- \n")

                except Exception as e:
                    awt_integrations_with_error += 1
                    self.stderr.write(f" -- ERROR migrating {inbound.name} (ID: {inbound.id}): {e}")

            self.stdout.write(f"\n -- Summary -- \n\n")
            self.stdout.write(f" -- AWT Integrations with error: {awt_integrations_with_error} -- ")
            self.stdout.write(f" -- AWT Integrations skipped: {awt_integrations_skipped} -- ")
            self.stdout.write(f" -- AWT Integrations created: {awt_integrations_created} -- ")
            self.stdout.write(f" -- AWT Integration Configurations created: {awt_integration_configs_created} -- \n\n")
            self.stdout.write(f" -- Destination Integration Types created: {destination_integration_types_created} -- ")
            self.stdout.write(f" -- Destination Integration Owners created: {destination_owners_created} -- ")
            self.stdout.write(f" -- Destination Integrations created: {destination_integration_created} -- ")

    def _get_awt_inbounds(self, options):
        try:
            awt_inbound_type = InboundIntegrationType.objects.get(
                name="Africa Wildlife Tracking (AWT)",
                description="Animal Collar	Hadrien Haupt	hadrien@awt.co.za",
                slug="awt"
            )
        except InboundIntegrationType.DoesNotExist:
            self.stdout.write(" -- ERROR: AWT Inbound Integration Type not found -- \n")
            return []

        inbounds = InboundIntegrationConfiguration.objects.filter(type=awt_inbound_type, enabled=True).all()

        self.stdout.write(f" -- Found {inbounds.count()} AWT inbounds -- ")

        if options['inbounds']:
            self.stdout.write(f" -- Filtering AWT inbounds by IDs: {options['inbounds']} -- ")
            inbounds = inbounds.filter(id__in=options['inbounds'])

        if not inbounds:
            self.stdout.write(f" -- ERROR: AWT Integrations with IDs {options['inbounds']} not found -- \n")
            return []

        if options['max']:
            self.stdout.write(f" -- Limiting to {options['max']} AWT inbounds as per --max option -- ")
            inbounds = inbounds[:options['max']]

        return inbounds

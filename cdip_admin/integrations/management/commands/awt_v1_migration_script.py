from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.conf import settings
from deployments.models import DispatcherDeployment
from deployments.utils import (
    get_dispatcher_defaults_from_gcp_secrets,
    get_default_dispatcher_name,
)
from deployments.tasks import deploy_serverless_dispatcher
from integrations.models import (
    Organization,
    Integration,
    IntegrationType,
    IntegrationAction,
    IntegrationConfiguration,
    Route,
    InboundIntegrationType,
    InboundIntegrationConfiguration,
    OutboundIntegrationConfiguration
)
from integrations.utils import get_dispatcher_topic_default_name


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
        if inbounds_to_migrate := self._get_awt_inbounds(options=options):
            awt_integrations_created = 0
            awt_integration_configs_created = 0
            destination_integration_types_created = 0
            destination_owners_created = 0
            destination_integration_created = 0

            self.stdout.write(f" -- Found {len(inbounds_to_migrate)} AWT inbounds to migrate -- \n")

            # Get or create AWT PUSH integration type
            awt_integration_type, _ = IntegrationType.objects.get_or_create(
                name="Africa Wildlife Tracking (Animal Tracker)  [Data Push]",
                value="awt_push_v2"
            )
            # Get or create AWT PUSH action
            awt_push_action, _ = IntegrationAction.objects.get_or_create(
                type=IntegrationAction.ActionTypes.PUSH_DATA,
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
                        )
                        if created:
                            # New integration created
                            awt_integrations_created += 1
                            self.stdout.write(f" -- Created new integration: {integration.name} (ID: {integration.id}) from v1 inbound -- ")

                            integration.enabled = False # enabled by default for validation purposes

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

                            # Read inbound destinations and create integration for each
                            for destination in inbound.destinations.all():
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

                                # if outbound is an ER site, remove the /api/v1.0 part from the base URL
                                if destination.is_er_site:
                                    destination.endpoint = destination.endpoint.replace(
                                        "/api/v1.0", ""
                                    )

                                destination_integration, created = Integration.objects.get_or_create(
                                    type=destination_integration_type,
                                    owner=destination_owner,
                                    base_url=destination.endpoint,
                                )
                                if created:
                                    destination_integration_created += 1
                                    destination_integration.name = destination.name
                                    destination_integration.save()

                                    self.stdout.write(f" -- Created new integration: {destination_integration.name} (ID: {destination_integration.id}) for destination: {destination.name} (ID: {destination.id})")

                                    self.deploy_dispatcher(integration=destination_integration)

                                integration.default_route.destinations.add(destination_integration)

                            integration.save()

                except Exception as e:
                    self.stderr.write(f" -- ERROR migrating {inbound.name} (ID: {inbound.id}): {e}")

            self.stdout.write(f"\n -- Summary -- \n")
            self.stdout.write(f" -- AWT Integrations created: {awt_integrations_created} -- ")
            self.stdout.write(f" -- AWT Integration Configurations created: {awt_integration_configs_created} -- ")
            self.stdout.write(f" -- Destination Integration Types created: {destination_integration_types_created} -- ")
            self.stdout.write(f" -- Destination Integration Owners created: {destination_owners_created} -- ")
            self.stdout.write(f" -- Destination Integrations created: {destination_integration_created} -- ")

    def deploy_dispatcher(self, integration):
        try:
            # Skip if the integration is not an ER, SMART, WPS Watch or TrapTagger site
            if not (integration.is_er_site or integration.is_smart_site or integration.is_wpswatch_site or integration.is_traptagger_site):
                self.stdout.write(
                    f" -- Integration {integration.name} is not an ER, SMART, WPS Watch or TrapTagger site. Skipped... -- "
                )
                return

            self.stdout.write(f" -- Deploying dispatcher for {integration.name}... -- ")

            # Create the topic and the dispatcher
            if integration.is_smart_site:
                secret_id = settings.DISPATCHER_DEFAULTS_SECRET_SMART
            elif integration.is_wpswatch_site:
                secret_id = settings.DISPATCHER_DEFAULTS_SECRET_WPSWATCH
            elif integration.is_traptagger_site:
                secret_id = settings.DISPATCHER_DEFAULTS_SECRET_TRAPTAGGER
            else:
                secret_id = settings.DISPATCHER_DEFAULTS_SECRET

            version = "v2"
            with transaction.atomic():  # Update the integration and create the dispatcher, both or none
                topic_name = get_dispatcher_topic_default_name(
                    integration=integration, gundi_version=version
                )
                integration.additional.update(
                    {"topic": topic_name, "broker": "gcp_pubsub"}
                )
                integration.save()
                DispatcherDeployment.objects.create(
                    name=get_default_dispatcher_name(
                        integration=integration, gundi_version=version
                    ),
                    integration=integration,
                    configuration=get_dispatcher_defaults_from_gcp_secrets(
                        secret_id=secret_id
                    ),
                )
        except Exception as e:
            self.stdout.write(
                f" -- Error deploying dispatcher for {integration.name}: {e} -- "
            )
        else:
            self.stdout.write(
                f" -- Deployment triggered for {integration.name} ({version}) -- "
            )

    def _get_awt_inbounds(self, options):
        awt_inbound_type, _ = InboundIntegrationType.objects.get_or_create(
            name="Africa Wildlife Tracking (AWT)",
            description="Animal Collar	Hadrien Haupt	hadrien@awt.co.za",
            slug="awt"
        )

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

import json

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
from integrations.models import Integration, OutboundIntegrationConfiguration, IntegrationAction, IntegrationType, \
    IntegrationConfiguration
from integrations.utils import get_dispatcher_topic_default_name


class Command(BaseCommand):
    help = "Create or update action configurations."

    def add_arguments(self, parser):
        parser.add_argument(
            "--integration",
            required=False,
            type=str,
            help="Select a single integration by ID",
        )
        parser.add_argument(
            "--integration-type",
            required=False,
            type=str,
            help="Select integrations by type. e.g. inreach, earth_ranger.",
        )
        parser.add_argument(
            "--action",
            type=str,
            help="Select an action by ID. e.g. pull_events, show_permissions",
        )
        parser.add_argument(
            "--data",
            type=str,
            default="{}",
            help="The JSON value to be set in the configuration data field.",
        )
        parser.add_argument(
            "--max",
            type=int,
            default=10,
            help="Specify the maximum number of integrations/configs to process.",
        )

    def handle(self, *args, **options):
        integration_type_slug_id = options.get("integration_type")
        integration_id = options.get("integration")
        action_slug_id = options.get("action")
        try:
            config_data = json.loads(options.get("data"))
        except json.JSONDecodeError:
            self.stderr.write("The provided configuration data is not valid JSON.")
            return
        if not integration_type_slug_id and not integration_id:
            self.stdout.write("Please specify an integration ID or type")
            return
        if integration_id:
            try:
                integration = Integration.objects.get(id=integration_id)
            except Integration.DoesNotExist:
                self.stderr.write(f"Integration '{integration_id}' not found.")
                return
        else:
            integration = None
        if integration_type_slug_id:
            try:
                integration_type = IntegrationType.objects.get(value=integration_type_slug_id)
            except IntegrationType.DoesNotExist:
                self.stderr.write(f"Integration type '{integration_type_slug_id}' not found.")
                return
        elif integration:  # Infer from the integration
            integration_type = integration.type
        else:
            self.stderr.write("Integration type could not be determined.")
            return

        try:
            action = IntegrationAction.objects.get(
                integration_type=integration_type,
                value=action_slug_id
            )
        except IntegrationAction.DoesNotExist:
            self.stderr.write(f"Action '{action_slug_id}' for type {integration_type_slug_id} not found.")
            return

        # Get integrations to process
        if integration_id:
            integrations_to_process = [integration]
        else:
            integrations_to_process = Integration.objects.filter(
                type=integration_type
            )[: options.get("max")]

        # Set configurations
        total_created = 0
        total_updated = 0
        self.stdout.write(f"Processing {len(integrations_to_process)} integrations...")
        for integration in integrations_to_process:
            action_config, created = IntegrationConfiguration.objects.update_or_create(
                integration=integration,
                action=action,
                defaults={"data": config_data}
            )
            if created:
                total_created += 1
                self.stdout.write(f"Created new config for action '{action_slug_id}' on integration '{integration.name}' ({integration.id})")
            else:
                total_updated += 1
                self.stdout.write(f"Updated config for action '{action_slug_id}' on integration '{integration.name}' ({integration.id})")

        self.stdout.write(f"Total created: {total_created}, Total updated: {total_updated}")

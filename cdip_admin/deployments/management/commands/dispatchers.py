from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.conf import settings
from deployments.models import DispatcherDeployment
from deployments.utils import (
    get_dispatcher_defaults_from_gcp_secrets,
    get_default_dispatcher_name,
)
from integrations.models import Integration, OutboundIntegrationConfiguration
from integrations.utils import get_dispatcher_topic_default_name


class Command(BaseCommand):
    help = "Manage serverless dispatcher deployments."

    def add_arguments(self, parser):
        parser.add_argument(
            "--v1",
            action="store_true",
            default=False,
            help="Show deployments for v1 integrations only",
        )
        parser.add_argument(
            "--v2",
            action="store_true",
            default=False,
            help="Show deployments for v2 integrations only",
        )
        parser.add_argument(
            "--type",
            type=str,
            help="Filter deployments by integration type",
        )
        parser.add_argument(
            "--list",
            action="store_true",
            default=False,
            help="List serverless dispatchers",
        )
        parser.add_argument(
            "--list-missing",
            action="store_true",
            default=False,
            help="List integrations using legacy dispatchers",
        )
        parser.add_argument(
            "--deploy",
            type=str,
            help="Deploy serverless dispatcher for the specified integration by ID",
        )
        parser.add_argument(
            "--deploy-missing",
            action="store_true",
            default=False,
            help="Deploy serverless dispatchers for integrations using legacy dispatchers",
        )
        parser.add_argument(
            "--max",
            type=int,
            default=10,
            help="Specify the maximum number of deployments to list or deploy",
        )

    def handle(self, *args, **options):

        if options["list"]:
            self.list_deployments(options=options)
        elif options["list_missing"]:
            self.list_integrations_using_kafka_dispatchers(options=options)
        elif integration_id := options["deploy"]:
            if not options.get("v1") and not options.get("v2"):
                self.stdout.write("Please specify a Gundi version (v1 or v2)")
                return
            integration = None
            if options["v1"]:
                try:
                    integration = OutboundIntegrationConfiguration.objects.get(
                        id=integration_id
                    )
                except OutboundIntegrationConfiguration.DoesNotExist:
                    self.stdout.write(f"Integration {integration_id} v1 not found")
                    return
            if options["v2"]:
                try:
                    integration = Integration.objects.get(id=integration_id)
                except Integration.DoesNotExist:
                    self.stdout.write(f"Integration {integration_id} v2 not found")
                    return
            self.deploy_dispatchers([integration])
        elif options["deploy_missing"]:
            integrations = self._get_integrations_using_kafka_dispatchers()
            if type := options["type"]:
                integrations = integrations.filter(type__slug=type.lower().strip())
            if max_deploys := options["max"]:
                integrations = integrations[:max_deploys]
            self.deploy_dispatchers(integrations)

        self.stdout.write(self.style.SUCCESS("Done."))

    def list_deployments(self, options):
        deployments = DispatcherDeployment.objects.all()
        if options["v1"]:
            deployments = deployments.filter(legacy_integration__isnull=False)
        if options["v2"]:
            deployments = deployments.filter(integration__isnull=False)
        if integration_type := options["type"]:
            if options["v1"]:
                deployments = deployments.filter(
                    legacy_integration__type__slug=integration_type.lower().strip()
                )
            if options["v2"]:
                deployments = deployments.filter(
                    integration__type__value=integration_type.lower().strip()
                )
            if max_deploys := options["max"]:
                deployments = deployments[:max_deploys]
        self.stdout.write(f"{len(deployments)} deployments:")
        if deployments:
            for deployment in deployments:
                if deployment.legacy_integration:
                    type = deployment.legacy_integration.type.slug
                elif deployment.integration:
                    type = deployment.integration.type.value
                else:
                    type = "unknown"
                if deployment.legacy_integration:
                    integration_name = deployment.legacy_integration.name
                    version = "v1"
                elif deployment.integration:
                    integration_name = deployment.integration.name
                    version = "v2"
                else:
                    integration_name = "no integration"
                    version = "unknown version"
                self.stdout.write(
                    f"({version}) ({type}) {deployment.name} - {integration_name} - {deployment.status}"
                )
        else:
            self.stdout.write("No deployments found")

    def deploy_dispatchers(self, integrations):
        for integration in integrations:
            try:
                # Skip if the integration is not an ER, SMART site, or WPS Watch Site
                if not (integration.is_er_site or integration.is_smart_site or integration.is_wpswatch_site):
                    self.stdout.write(
                        f"Integration {integration.name} is not an ER, SMART or WPS Watch site. Skipped"
                    )
                    continue

                # Skip if the integration is already using pubsub
                if integration.additional.get("broker") == "gcp_pubsub":
                    self.stdout.write(
                        f"Integration {integration.name} is already using pubsub. Skipped"
                    )
                    continue

                self.stdout.write(f"Deploying dispatcher for {integration.name}...")

                # Create the topic and the dispatcher
                if integration.is_smart_site:
                    secret_id = settings.DISPATCHER_DEFAULTS_SECRET_SMART
                elif integration.is_wpswatch_site:
                    secret_id = settings.DISPATCHER_DEFAULTS_SECRET_WPSWATCH
                else:
                    secret_id = settings.DISPATCHER_DEFAULTS_SECRET
                if isinstance(integration, OutboundIntegrationConfiguration):
                    version = "v1"
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
                            legacy_integration=integration,
                            configuration=get_dispatcher_defaults_from_gcp_secrets(
                                secret_id=secret_id
                            ),
                        )
                elif isinstance(integration, Integration):
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
                else:
                    self.stdout.write(
                        f"Unknown integration type: {integration}. Skipped"
                    )
                    continue
            except Exception as e:
                self.stdout.write(
                    f"Error deploying dispatcher for {integration.name}: {e}"
                )
            else:
                self.stdout.write(
                    f"Deployment triggered for {integration.name} ({version})"
                )

    def list_integrations_using_kafka_dispatchers(self, options):
        integrations = self._get_integrations_using_kafka_dispatchers()
        if type := options["type"]:
            integrations = integrations.filter(type__slug=type.lower().strip())
        self.stdout.write(
            f"{len(integrations)} integrations using legacy dispatchers (kafka consumers):"
        )
        for integration in integrations:
            self.stdout.write(
                f"({integration.type.slug}) - {integration.name} - {str(integration.id)}"
            )

    def _get_integrations_using_kafka_dispatchers(self):
        return OutboundIntegrationConfiguration.objects.filter(
            ~Q(additional__has_key="broker") | Q(additional__broker="kafka")
        )

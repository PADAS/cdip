from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.conf import settings
from deployments.models import DispatcherDeployment
from deployments.utils import (
    create_dispatcher_for_integration,
    get_dispatcher_defaults_from_gcp_secrets,
    get_default_dispatcher_name,
)
from deployments.tasks import deploy_serverless_dispatcher
from integrations.models import Integration, OutboundIntegrationConfiguration
from integrations.utils import get_dispatcher_topic_default_name


SHARED_POOL_COOLING_DAYS = 7


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
            "--list-unused",
            action="store_true",
            default=False,
            help="List deployments not linked to any integration and whose topic is not used by any integration",
        )
        parser.add_argument(
            "--delete-unused",
            action="store_true",
            default=False,
            help="Delete unused deployments (as listed by --list-unused), tearing down their GCP resources",
        )
        parser.add_argument(
            "--yes",
            action="store_true",
            default=False,
            help="Skip the confirmation prompt when deleting",
        )
        parser.add_argument(
            "--deploy",
            type=str,
            help="Deploy serverless dispatcher for the specified integration by ID",
        )
        parser.add_argument(
            "--recreate",
            action="store_true",
            default=False,
            help="Re-create dispatchers and related subscriptions, copying setings from existent dispatchers",
        )
        parser.add_argument(
            "--deploy-missing",
            action="store_true",
            default=False,
            help="Deploy serverless dispatchers for integrations using legacy dispatchers",
        )
        parser.add_argument(
            "--update-source",
            type=str,
            help="Update source code of serverless dispatchers with the specified version",
        )
        parser.add_argument(
            "--max",
            type=int,
            default=10,
            help="Specify the maximum number of deployments to list or deploy",
        )
        parser.add_argument(
            "--integration",
            type=str,
            help="Select a single integration by ID",
        )
        parser.add_argument(
            "--migrate-to-shared",
            action="store_true",
            default=False,
            help="Move ER integrations onto the shared dispatcher pool topic (old dispatchers are kept for rollback)",
        )
        parser.add_argument(
            "--rollback-shared",
            action="store_true",
            default=False,
            help="Restore an integration's pre-migration topic (requires --integration; only while the old dispatcher still exists)",
        )
        parser.add_argument(
            "--teardown-migrated",
            action="store_true",
            default=False,
            help="Tear down old dispatchers of integrations migrated to the shared pool after the cooling period",
        )
        parser.add_argument(
            "--cooling-days",
            type=int,
            default=None,
            help="Override the shared-pool teardown cooling period (default 7 days). Use with care.",
        )

    def handle(self, *args, **options):

        if options["list"]:
            self.list_deployments(options=options)
        elif options["list_missing"]:
            self.list_integrations_using_kafka_dispatchers(options=options)
        elif options["list_unused"]:
            self.list_unused_deployments(options=options)
        elif options["delete_unused"]:
            if not self.delete_unused_deployments(options=options):
                return  # Aborted; don't report success below
        elif integration_id := options.get("deploy"):
            integration = self._get_integration_by_id(integration_id=integration_id, options=options)
            self.deploy_dispatchers([integration])
        elif options["deploy_missing"]:
            if not options.get("v1") and not options.get("v2"):
                self.stdout.write("Please specify a Gundi version (v1 or v2)")
                return
            integrations = self._get_integrations_using_kafka_dispatchers()
            if type := options["type"]:
                integrations = integrations.filter(type__slug=type.lower().strip())
            if max_deploys := options["max"]:
                integrations = integrations[:max_deploys]
            self.deploy_dispatchers(integrations)
        elif options.get("update_source") or options.get("recreate"):
            source = options.get("update_source")
            recreate = options.get("recreate")
            if not options.get("v1") and not options.get("v2"):
                self.stdout.write("Please specify a Gundi version (v1 or v2)")
                return
            if integration_id := options["integration"]:
                integration = self._get_integration_by_id(integration_id=integration_id, options=options)
                if not integration:
                    self.stderr.write("Integration not found")
                    return
                if source:
                    source = source.lower().strip()
                    new_settings = {"source_code_path": source} if integration.is_er_site else {"docker_image_url": source}
                    integrations_to_update = [integration]
            elif type := options.get("type"):
                # Build the query to get the integrations to update, based on type and version
                related_dispatcher_field = "dispatcher_by_integration" if options.get("v2") else "dispatcher_by_outbound"
                IntegrationModel = Integration if options.get("v2") else OutboundIntegrationConfiguration
                type_cleaned = type.lower().strip()
                integration_type_q = Q(type__value=type_cleaned) if options.get("v2") else Q(type__slug=type_cleaned)
                if source:
                    source_field = "source_code_path" if type_cleaned == "earth_ranger"  else "docker_image_url"
                    source_lookup = f"{related_dispatcher_field}__configuration__deployment_settings__{source_field}"
                    source_outdated_q = ~Q(**{source_lookup: source})
                    integrations_to_update = IntegrationModel.objects.filter(
                        integration_type_q & source_outdated_q
                    ).order_by("name")[:options["max"]]
                    new_settings = {"source_code_path": source} if type_cleaned == "earth_ranger" else {"docker_image_url": source}
                else:
                    integrations_to_update = IntegrationModel.objects.filter(
                        integration_type_q
                    ).order_by("name")[:options["max"]]
                    new_settings = None
            else:
                self.stdout.write("Please specify an integration ID or a type")
                return
            if recreate:
                self.recreate_dispatchers(
                    integrations=integrations_to_update,
                    deployment_settings=new_settings
                )
            else:
                self.update_dispatchers(
                    integrations=integrations_to_update,
                    deployment_settings=new_settings
                )
        elif options["migrate_to_shared"]:
            if not self._require_shared_topic():
                return
            self.migrate_to_shared(
                self._get_migratable_er_integrations(
                    max_count=options["max"], integration_id=options.get("integration")
                )
            )
        elif options["rollback_shared"]:
            if not self._require_shared_topic():
                return
            self.rollback_shared(integration_id=options.get("integration"))
        elif options["teardown_migrated"]:
            if not self._require_shared_topic():
                return
            self.teardown_migrated(options=options)
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

    def _get_unused_deployments(self):
        used_topics = set(
            Integration.objects.filter(additional__has_key="topic").values_list(
                "additional__topic", flat=True
            )
        )
        used_topics |= set(
            OutboundIntegrationConfiguration.objects.filter(
                additional__has_key="topic"
            ).values_list("additional__topic", flat=True)
        )
        used_topics.discard(None)
        used_topics.discard("")
        orphaned_deployments = DispatcherDeployment.objects.filter(
            integration__isnull=True, legacy_integration__isnull=True
        )
        # Filter in Python: a SQL exclude(topic_name__in=...) would silently drop
        # rows with a NULL topic_name, which are precisely unused deployments.
        return [
            deployment
            for deployment in orphaned_deployments
            if not deployment.topic_name or deployment.topic_name not in used_topics
        ]

    def _print_unused_deployments(self, unused_deployments):
        self.stdout.write(f"{len(unused_deployments)} unused deployments:")
        if unused_deployments:
            for deployment in unused_deployments:
                topic = deployment.topic_name or "no topic"
                self.stdout.write(
                    f"{deployment.name} - {topic} - {deployment.status} - {deployment.id}"
                )
        else:
            self.stdout.write("No unused deployments found")

    def list_unused_deployments(self, options):
        self._print_unused_deployments(self._get_unused_deployments())

    def delete_unused_deployments(self, options):
        """Returns False when the user aborts at the prompt, True otherwise."""
        unused_deployments = self._get_unused_deployments()
        self._print_unused_deployments(unused_deployments)
        if not unused_deployments:
            return True
        if not options["yes"]:
            answer = input(
                f"Delete these {len(unused_deployments)} deployments and their GCP resources? [y/N]: "
            )
            if answer.lower().strip() not in ("y", "yes"):
                self.stdout.write("Aborted.")
                return False
        for deployment in unused_deployments:
            # Triggers the delete_serverless_dispatcher task, which tears down
            # the GCP resources and then removes the row.
            deployment.delete()
            self.stdout.write(f"Deletion triggered for {deployment.name} ({deployment.id})")
        return True

    def deploy_dispatchers(self, integrations):
        for integration in integrations:
            try:
                # Skip if the integration is not an ER, SMART, WPS Watch or TrapTagger site
                if not (integration.is_er_site or integration.is_smart_site or integration.is_wpswatch_site or integration.is_traptagger_site):
                    self.stdout.write(
                        f"Integration {integration.name} is not an ER, SMART, WPS Watch or TrapTagger site. Skipped"
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
                if isinstance(integration, OutboundIntegrationConfiguration):
                    version = "v1"
                    if integration.is_smart_site:
                        secret_id = settings.DISPATCHER_DEFAULTS_SECRET_SMART
                    elif integration.is_wpswatch_site:
                        secret_id = settings.DISPATCHER_DEFAULTS_SECRET_WPSWATCH
                    elif integration.is_traptagger_site:
                        secret_id = settings.DISPATCHER_DEFAULTS_SECRET_TRAPTAGGER
                    else:
                        secret_id = settings.DISPATCHER_DEFAULTS_SECRET
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
                        create_dispatcher_for_integration(integration)
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

    def update_dispatchers(self, integrations, env_vars=None, deployment_settings=None):
        self.stdout.write(self.style.SUCCESS(f"Updating dispatchers for {len(integrations)} integrations..."))
        for integration in integrations:
            try:
                # Skip if the integration is not an ER, SMART, WPS Watch or TrapTagger site
                if not (integration.is_er_site or integration.is_smart_site or integration.is_wpswatch_site or integration.is_traptagger_site):
                    self.stdout.write(
                        f"Integration {integration.name} is not an ER, SMART or WPS Watch site. Skipped"
                    )
                    continue

                self.stdout.write(
                    f"Updating dispatcher for {integration.name} with env_vars: {env_vars}, deployment_settings {deployment_settings}..."
                )

                if isinstance(integration, OutboundIntegrationConfiguration):
                    version = "v1"
                    dispatcher_deployment = integration.dispatcher_by_outbound
                elif isinstance(integration, Integration):
                    version = "v2"
                    dispatcher_deployment = integration.dispatcher_by_integration
                else:
                    self.stdout.write(
                        f"Unknown integration type: {integration}. Skipped"
                    )
                    continue
                # Updating the dispatcher configuration will triggers the re-deployment
                if env_vars:
                    dispatcher_deployment.configuration["env_vars"].update(env_vars)
                if deployment_settings:
                    dispatcher_deployment.configuration["deployment_settings"].update(deployment_settings)

                dispatcher_deployment.save()
            except DispatcherDeployment.DoesNotExist:
                self.stderr.write(
                    f"Dispatcher for {integration.name} (id: {integration.id}) does not exist. Please deploy a dispatcher first."
                )
                continue
            except Exception as e:
                self.stderr.write(
                    f"Error deploying dispatcher for {integration.name} (id: {integration.id}): {e}"
                )
                continue
            else:
                self.stdout.write(
                    f"Update triggered for {integration.name} ({version})\nDispatcher: {dispatcher_deployment.name}"
                )


    def recreate_dispatchers(self, integrations, env_vars=None, deployment_settings=None):
        self.stdout.write(self.style.SUCCESS(f"Re-creating dispatchers for {len(integrations)} integrations..."))
        for integration in integrations:
            try:
                # Skip if the integration is not an ER, SMART, WPS Watch, or TrapTagger site
                if not (integration.is_er_site or integration.is_smart_site or integration.is_wpswatch_site or integration.is_traptagger_site):
                    self.stdout.write(
                        f"Integration {integration.name} is not an ER, SMART or WPS Watch site. Skipped"
                    )
                    continue

                self.stdout.write(
                    f"Re-creating dispatcher for {integration.name} with env_vars: {env_vars}, deployment_settings {deployment_settings}..."
                )

                if isinstance(integration, OutboundIntegrationConfiguration):
                    version = "v1"
                    dispatcher_deployment = integration.dispatcher_by_outbound
                elif isinstance(integration, Integration):
                    version = "v2"
                    dispatcher_deployment = integration.dispatcher_by_integration
                else:
                    self.stdout.write(
                        f"Unknown integration type: {integration}. Skipped"
                    )
                    continue

                deploy_serverless_dispatcher.delay(
                    deployment_id=dispatcher_deployment.id,
                    force_recreate=True,
                    deployment_settings=deployment_settings
                )

            except DispatcherDeployment.DoesNotExist:
                self.stderr.write(
                    f"Dispatcher for {integration.name} (id: {integration.id}) does not exist. Please deploy a dispatcher first."
                )
                continue
            except Exception as e:
                self.stderr.write(
                    f"Error recreating dispatcher for {integration.name} (id: {integration.id}): {e}"
                )
                continue
            else:
                self.stdout.write(
                    f"Dispatcher re-create triggered for {integration.name} ({version})\nDispatcher: {dispatcher_deployment.name}"
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

    def _get_integration_by_id(self, integration_id, options):
        integration = None
        if options["v1"]:
            try:
                integration = OutboundIntegrationConfiguration.objects.get(
                    id=integration_id
                )
            except OutboundIntegrationConfiguration.DoesNotExist:
                self.stdout.write(f"Integration {integration_id} v1 not found")
                return None
        if options["v2"]:
            try:
                integration = Integration.objects.get(id=integration_id)
            except Integration.DoesNotExist:
                self.stdout.write(f"Integration {integration_id} v2 not found")
                return None
        return integration

    def _require_shared_topic(self):
        if not settings.ER_SHARED_DISPATCHER_TOPIC:
            self.stderr.write(
                "ER_SHARED_DISPATCHER_TOPIC is not set - shared-pool verbs are disabled in this environment."
            )
            return False
        return True

    def _get_migratable_er_integrations(self, max_count, integration_id=None):
        if max_count is not None and max_count <= 0:
            return []
        shared = settings.ER_SHARED_DISPATCHER_TOPIC
        qs = Integration.objects.filter(dispatcher_by_integration__isnull=False)
        if integration_id:
            qs = qs.filter(id=integration_id)
        candidates = []
        for integration in qs.order_by("name"):
            if not integration.is_er_site:
                continue
            additional = integration.additional or {}
            if additional.get("dedicated_dispatcher"):
                continue
            if additional.get("topic") == shared:
                continue  # already migrated (or manually moved); teardown handles it
            candidates.append(integration)
            if len(candidates) >= max_count:
                break
        return candidates

    def migrate_to_shared(self, integrations):
        from django.utils import timezone
        shared = settings.ER_SHARED_DISPATCHER_TOPIC
        self.stdout.write(self.style.SUCCESS(
            f"Migrating {len(integrations)} ER integrations to shared topic {shared}..."
        ))
        for integration in integrations:
            try:
                additional = integration.additional or {}
                deployment = integration.dispatcher_by_integration
                pre_migration_topic = additional.get("topic") or deployment.topic_name
                updated = {
                    **additional,
                    "broker": "gcp_pubsub",
                    "topic": shared,
                    "pre_migration_topic": pre_migration_topic,
                    "shared_pool_migrated_at": timezone.now().isoformat(),
                }
                Integration.objects.filter(pk=integration.pk).update(additional=updated)
                self.stdout.write(
                    f"Migrated {integration.name} ({integration.id}) from {pre_migration_topic}. "
                    f"Old dispatcher {deployment.name} kept for rollback."
                )
            except Exception as e:
                self.stderr.write(f"Error migrating {integration.name} ({integration.id}): {e}")
                continue

    def rollback_shared(self, integration_id=None):
        self.stderr.write("rollback_shared: not implemented yet")

    def teardown_migrated(self, options=None):
        self.stderr.write("teardown_migrated: not implemented yet")

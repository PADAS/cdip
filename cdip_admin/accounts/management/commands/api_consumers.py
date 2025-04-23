import base64
import json

from django.core.management.base import BaseCommand

from integrations.models import Integration, InboundIntegrationConfiguration
from integrations.utils import get_api_key, get_api_consumer_info, patch_api_consumer_info


class Command(BaseCommand):
    help = "Manage API consumers."

    def add_arguments(self, parser):
        parser.add_argument(
            "--v1",
            action="store_true",
            default=False,
            help="Select api consumers for v1 integrations only",
        )
        parser.add_argument(
            "--v2",
            action="store_true",
            default=False,
            help="Select api consumers for v2 integrations only",
        )
        parser.add_argument(
            "--list",
            action="store_true",
            default=True,
            help="List serverless dispatchers",
        )
        parser.add_argument(
            "--integration",
            type=str,
            help="Select a single integration by ID",
        )
        parser.add_argument(
            "--get-key",
            action="store_true",
            default=False,
            help="Retrieve the API key of the selected integrations",
        )
        parser.add_argument(
            "--set-integration-type",
            action="store_true",
            default=False,
            help="Update the consumer info with the integration type for the selected integration(s)",
        )
        parser.add_argument(
            "--max",
            type=int,
            default=10,
            help="Apply the operation in a maximum number of integrations",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Don't apply real changes."
        )

    def handle(self, *args, **options):
        # Select integrations
        if options["v1"] and options["v2"]:
            self.stderr.write("Please select either v1 or v2 integrations, not both.")
            return
        if options["v1"]:
            integrations = InboundIntegrationConfiguration.objects.all()
        elif options["v2"]:
            integrations = Integration.objects.all()
        else:
            self.stderr.write("Please select either v1 or v2 integrations.")
            exit(1)
        if options["integration"]:
            integrations = integrations.filter(id=options["integration"])
        if options["max"]:
            integrations = integrations[: options["max"]]

        # Apply operations
        if options["set_integration_type"]:
            self.add_integration_type(
                integrations=integrations,
                dry_run=options["dry_run"]
            )
        else:  # Describe consumers
            self.describe_consumers(
                integrations=integrations,
                include_apikey=options["get_key"],
            )

    def add_integration_type(self, integrations, dry_run=False):
        self.stdout.write(f"Updating consumer info for {integrations.count()} integrations...")
        updated = 0
        for integration in integrations:
            try:
                self.stdout.write(f"Reading consumer info for integration {integration} ({integration.id})...")
                current_consumer_info = get_api_consumer_info(integration)
                self.stdout.write(f"Consumer info: {current_consumer_info}")
                consumer_custom_id = current_consumer_info["custom_id"]
                decoded_data = json.loads(base64.b64decode(consumer_custom_id).decode("utf-8").strip())
                self.stdout.write(f"Decoded data: {decoded_data}")
                self.stdout.write(f"Setting integration type...")
                decoded_data["integration_type"] = getattr(integration.type, "value", getattr(integration.type, "slug", "unknown"))
                self.stdout.write(f"New data: {decoded_data}")
                new_consumer_custom_id_json = json.dumps(decoded_data).encode("utf-8")
                new_consumer_custom_id = base64.b64encode(new_consumer_custom_id_json)
                consumer_info_patch_data = {
                    "custom_id": new_consumer_custom_id
                }
                self.stdout.write(f"Patching consumer info with: {consumer_info_patch_data}")
                if dry_run:
                    self.stdout.write("Dry run, not applying changes.")
                    continue
                patch_api_consumer_info(
                    integration=integration,
                    data=consumer_info_patch_data,
                )
            except Exception as e:
                self.stderr.write(
                    f"Error updating consumer info for integration {integration}: {type(e).__name__}: {e}"
                )
                continue
            else:
                updated += 1
                self.stdout.write(
                    f"Consumer info for integration {integration} ({integration.id}) updated successfully."
                )
        self.stdout.write(f"Consumer info updated for {updated} integrations.")
        return updated

    def describe_consumers(self, integrations, include_apikey=False):
        self.stdout.write(f"Describing consumers for {integrations.count()} integrations...")
        for integration in integrations:
            self.stdout.write(f"Reading consumer info for integration {integration} ({integration.id})...")
            current_consumer_info = get_api_consumer_info(integration)
            self.stdout.write(f"Consumer info: {current_consumer_info}")
            consumer_custom_id = current_consumer_info["custom_id"]
            decoded_data = json.loads(base64.b64decode(consumer_custom_id).decode("utf-8").strip())
            self.stdout.write(f"Decoded data: {decoded_data}")
            if include_apikey:
                self.stdout.write(f"Getting API key...")
                try:
                    api_key = get_api_key(integration)
                except Exception as e:
                    self.stderr.write(
                        f"Error getting API key for integration {integration}: {type(e).__name__}: {e}"
                    )
                    continue
                else:
                    self.stdout.write(f"API key: {api_key}")

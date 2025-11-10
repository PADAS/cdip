import copy
import logging

from django.core.management.base import BaseCommand
from django.db import transaction
from integrations.models import Integration, RouteConfiguration


DEFAULT_FIELD_MAPPING = {"default": "", "destination_field": "provider_key"}


class Command(BaseCommand):

    help = "Gundi v2 field mapping creation script"

    def add_arguments(self, parser):
        parser.add_argument(
            "--connection-id",
            type=str,
            required=True,
            help="Specify the Gundi v2 connection ID [REQUIRED]",
        )
        parser.add_argument(
            "--destination-id",
            type=str,
            required=True,
            help="Specify the Gundi v2 destination ID [REQUIRED]",
        )
        parser.add_argument(
            '--provider-key',
            type=str,
            required=True,
            help='Provider key to be used in field mapping creation [REQUIRED]'
        )

    def handle(self, *args, **options):

        # TODO: FOR LOCAL EXECUTION ONLY! Remove if running in pod
        logging.getLogger('django.db.backends').setLevel(logging.WARNING)
        logging.getLogger('activity_log.mixins').setLevel(logging.ERROR)
        logging.getLogger('integrations.tasks').setLevel(logging.WARNING)

        connection_id = options["connection_id"]
        destination_id = options["destination_id"]
        provider_key = options["provider_key"]

        try:
            with transaction.atomic():
                try:
                    source_integration = Integration.objects.get(
                        id=connection_id,
                    )
                except Integration.DoesNotExist:
                    self.stdout.write(f" -- ERROR: Connection ID {connection_id} does not exist in Gundi v2 -- ")
                    return

                try:
                    destination_integration = Integration.objects.get(
                        id=destination_id,
                    )
                except Integration.DoesNotExist:
                    self.stdout.write(f" -- ERROR: Destination ID {destination_id} does not exist in Gundi v2 -- ")
                    return

            self.stdout.write(f" -- Connection: {source_integration.name} -- \n")
            self.stdout.write(f" -- Destination: {destination_integration.name} -- \n")
            self.stdout.write(f" -- Provider Key: {provider_key} -- \n\n")

            field_mappings = {
                str(source_integration.id): {
                    "obv": {}
                }
            }

            inbound_field_mapping = copy.deepcopy(DEFAULT_FIELD_MAPPING)
            inbound_field_mapping["default"] = provider_key

            field_mappings[str(source_integration.id)]["obv"][str(destination_integration.id)] = inbound_field_mapping

            field_mappings_result = {
                "field_mappings": field_mappings
            }
            route_config, created = RouteConfiguration.objects.get_or_create(
                name=f"{source_integration.default_route.name} (Integration ID: {str(source_integration.id)}) - Default Config",
                defaults={
                    "data": field_mappings_result
                }
            )

            if not created:
                # A route config already exists for this migration, we need to update it
                route_config.data = field_mappings_result
                route_config.save()

            source_integration.default_route.configuration = route_config
            source_integration.default_route.save()
            source_integration.save()

            self.stdout.write(f" -- Connection '{source_integration.name}' (ID: '{source_integration.id}') route config (field_mapping) created correctly... -- \n")
            self.stdout.write(f" -- Name: '{route_config.name}', ID: '{route_config.id}' ... -- \n\n")

        except Exception as e:
            self.stderr.write(f" -- ERROR creating field mapping for connection ID {connection_id}, destination ID: {destination_id}: {e}")

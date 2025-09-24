import copy

from django.core.management.base import BaseCommand
from django.db import transaction

from integrations.models import Integration


DEFAULT_FIELD_MAPPING = {"default": "", "destination_field": "provider_key"}


class Command(BaseCommand):
    def handle(self, *args, **options):
        def extract_provider_key(d):
            for k, v in d.items():
                if k == "default":
                    return v
                result = extract_provider_key(v)
                if result is not None:
                    return result
            return None

        self.stdout.write(f" -- InReach route configs fixer script -- \n\n")

        integrations = Integration.objects.filter(
            type__value="inreach",
            name__contains="[V1 to V2]"
        )

        self.stdout.write(f" -- Got {len(integrations)} InReach integrations to fix -- \n\n")

        for integration in integrations:
            try:
                with transaction.atomic():
                    route_config_data = integration.default_route.configuration.data

                    self.stdout.write(f" -- Current route config for integration '{integration.name}': '{route_config_data}' -- ")

                    current_provider_key = extract_provider_key(integration.default_route.configuration.data)
                    field_mappings = {
                        str(integration.id): {
                            "obv": {},
                            "txt": {}
                        }
                    }
                    for destination in integration.default_route.destinations.all():
                        inbound_field_mapping = copy.deepcopy(DEFAULT_FIELD_MAPPING)
                        inbound_field_mapping["default"] = current_provider_key

                        field_mappings[str(integration.id)]["obv"][str(destination.id)] = inbound_field_mapping
                        field_mappings[str(integration.id)]["txt"][str(destination.id)] = inbound_field_mapping

                    field_mappings_result = {
                        "field_mappings": field_mappings
                    }

                    self.stdout.write(f" -- New route config for integration '{integration.name}': '{field_mappings_result}' -- ")

                    integration.default_route.configuration.data = field_mappings_result
                    integration.default_route.configuration.save()
                    integration.default_route.save()
                    integration.save()

                    self.stdout.write(f" -- Route config for integration {integration.name} updated correctly -- \n\n")
            except Exception as e:
                self.stderr.write(f"\n\n -- ERROR updating integration '{integration.name}' route config: {e} -- \n\n")

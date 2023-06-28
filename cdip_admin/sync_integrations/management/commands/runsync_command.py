import logging

from django.core.management.base import BaseCommand

from integrations.models import (
    OutboundIntegrationConfiguration,
    InboundIntegrationConfiguration,
)
from sync_integrations.er_smart_sync import ER_SMART_Synchronizer
from sync_integrations.tasks import run_er_smart_sync_integrations

logger = logging.getLogger(__name__)


class SyncException(Exception):
    pass


class Command(BaseCommand):
    help = "A command to run a given synchronization process"

    def add_arguments(self, parser):
        parser.add_argument(
            "--smart_integration_id",
            type=str,
            help="SMART integration configuration id",
        )

        parser.add_argument(
            "--er_integration_id",
            type=str,
            help="Earth Ranger integration configuration id",
        )

    def handle(self, *args, **options):

        # TODO: In future can probably just pass in two integration ids and another param for type of sync
        if options["smart_integration_id"] and options["er_integration_id"]:
            smart_integration_id = options["smart_integration_id"]
            er_integration_id = options["er_integration_id"]

            try:
                smart_config = OutboundIntegrationConfiguration.objects.get(
                    id=smart_integration_id
                )
            except OutboundIntegrationConfiguration.DoesNotExist:
                print(
                    f"SMART integration configuration does not exist for id: {smart_integration_id}"
                )
                return

            try:
                er_config = InboundIntegrationConfiguration.objects.get(
                    id=er_integration_id
                )
            except InboundIntegrationConfiguration.DoesNotExist:
                print(
                    f"Earth Ranger integration configuration does not exist for id {er_integration_id}"
                )
                return

            er_smart_sync = ER_SMART_Synchronizer(
                smart_config=smart_config, er_config=er_config
            )
            er_smart_sync.synchronize_datamodel()
        else:
            print('Running all sync integrations.')
            run_er_smart_sync_integrations()

        print("Finished.")
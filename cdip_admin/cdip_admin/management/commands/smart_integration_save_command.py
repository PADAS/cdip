from django.core.management.base import BaseCommand
import logging

from sync_integrations.utils import on_smart_integration_save

logger = logging.getLogger(__name__)

# smart_integration_save_command --settings=cdip_admin.local_settings --smart_integration_id=114499bc-8689-4e12-adc4-ac9be94eeae0
class Command(BaseCommand):
    help = "A command to run appropriate actions after a SMART integration configuration is saved"

    def add_arguments(self, parser):
        parser.add_argument(
            "--smart_integration_id",
            type=str,
            help="SMART integration configuration id",
        )

    def handle(self, *args, **options):
        try:
            smart_integration_id = options.get("smart_integration_id")
            if smart_integration_id:
                on_smart_integration_save(integration_id=smart_integration_id)
            else:
                logger.warning("smart_integration_id not present in options")
        except:
            # TODO: raise a PortalBackgroundProcessError
            pass

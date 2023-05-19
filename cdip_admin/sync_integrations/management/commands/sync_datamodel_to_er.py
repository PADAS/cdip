from django.core.management.base import BaseCommand
from sync_integrations.er_smart_sync import ER_SMART_Synchronizer
import logging

#  runsync_command --settings=cdip_admin.local_settings --smart_integration_id=114499bc-8689-4e12-adc4-ac9be94eeae0 --er_integration_id=9e0d298a-01e0-4bfa-acc3-f0b446037095
from sync_integrations.tasks import run_er_smart_sync_integrations
from smartconnect import SmartClient
from dasclient.dasclient import DasClient, DasClientException

logger = logging.getLogger(__name__)


class SyncException(Exception):
    pass


class Command(BaseCommand):
    help = "A command to synchronize a downloaded Smart data model to EarthRanger."

    def add_arguments(self, parser):
        parser.add_argument(
            "-f",
            type=str,
            help="SMART Data Model File",
        )

        parser.add_argument(
            "--er_integration_id",
            type=str,
            help="Earth Ranger integration configuration id",
        )

    def handle(self, *args, **options):

        sclient = SmartClient(api='https://tempuri.org/', username='', password='', use_language_code='fr')
        dm = sclient.load_datamodel(filename='/Users/chrisdo/Downloads/Modele de données SMART.xml')

        print(dm)

        das_client = DasClient(
            service_root='https://ntokoupikounda.pamdas.org/api/v1.0',
            token="1ddb93be307d9bbda29e44885fd6e8df6030a79d",
            token_url="https://ntokoupikounda.pamdas.org/oauth2/token",
            client_id="das_web_client",
            provider_key="sample-dev",
        )

        er_smart_sync = ER_SMART_Synchronizer(das_client=das_client)
        er_smart_sync.push_smart_ca_datamodel_to_earthranger(smart_ca_uuid='smart-ca',
                                                             ca_label="[SMART]",
                                                             dm=dm)

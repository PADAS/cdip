from django.core.management.base import BaseCommand
from sync_integrations.er_smart_sync import ER_SMART_Synchronizer


#  runsync_command --settings=cdip_admin.local_settings --smart_integration_id=114499bc-8689-4e12-adc4-ac9be94eeae0 --er_integration_id=9e0d298a-01e0-4bfa-acc3-f0b446037095
from sync_integrations.utils import run_er_smart_sync_integrations


class Command(BaseCommand):
    help = 'A command to run a given synchronization process'

    def add_arguments(self, parser):
        parser.add_argument('--smart_integration_id', type=str,
                            help='SMART integration configuration id')

        parser.add_argument('--er_integration_id', type=str,
                            help='Earth Ranger integration configuration id')

    def handle(self, *args, **options):
        #TODO: In future can probably just pass in two integration ids and another param for type of sync
        if options['smart_integration_id'] and options['er_integration_id']:
            smart_integration_id = options['smart_integration_id']
            er_integration_id = options['er_integration_id']
            er_smart_sync = ER_SMART_Synchronizer(smart_integration_id=smart_integration_id,
                                                  er_integration_id=er_integration_id)
            er_smart_sync.push_smart_ca_data_model_to_er_event_types()
        else:
            run_er_smart_sync_integrations()
            # print("Arguments supplied are insufficient to run sync process")

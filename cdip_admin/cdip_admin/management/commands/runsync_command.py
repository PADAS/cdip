from django.core.management.base import BaseCommand
from sync_integrations.er_smart_sync import push_smart_ca_data_model_to_er_event_types


#  python manage.py runsync_command --settings=cdip_admin.local_settings
class Command(BaseCommand):
    help = 'A command to run a given synchronization process'

    def add_arguments(self, parser):
        # TODO: Determine how we want to configure this command
        pass

    def handle(self, *args, **options):
        # TODO: Determine how we want to handle the synchronization
        push_smart_ca_data_model_to_er_event_types()

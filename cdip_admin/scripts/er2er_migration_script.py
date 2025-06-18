import os
import django
from typing import Dict, Any

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cdip_admin.settings')

django.setup()

from integrations.models import (
    DeviceGroup,
    InboundIntegrationConfiguration,
    InboundIntegrationType,
    Organization,
    OutboundIntegrationConfiguration,
    OutboundIntegrationType
)


SETTINGS_DIR = 'das2das_zappa-settings'
REQUIRED_VARS = ['DAS_DEST', 'DAS_SRC', 'DAS_SRC_AUTH_TOKEN']


def print_error(msg: str, filename: str):
    print(f"ERROR: '{msg}' in '{filename}'. Skipping...")

def extract_env_vars(file_path: str, filename: str) -> Dict[str, Any]:
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        exec_globals = {}
        exec(content, exec_globals)
        return exec_globals.get('ENVIRONMENT_VARIABLES', {})
    except Exception as e:
        print_error(f"Failed to extract ENVIRONMENT_VARIABLES: {e}", filename)
        return {}

def get_provider_key(env_vars: dict) -> str:
    if 'PROVIDER_KEY' in env_vars:
        return env_vars['PROVIDER_KEY']
    das_src = env_vars.get('DAS_SRC', '')
    return das_src.split('://', 1)[-1].split('.', 1)[0] if das_src else ''

def create_inbounds_from_files():
    """
    Reads settings files from the specified directory and creates inbound objects based on the content.
    Each file should contain environment variables and other necessary configurations.
    """
    total_files = files_skipped = inbounds_created = outbounds_created = device_groups_created = files_with_error = 0

    print("\n -- ER2ER Subject Sharing Migration Script -- ")

    inbound_type = InboundIntegrationType.objects.filter(slug="er2er_subject_sharing").first()
    if not inbound_type:
        print("ERROR: Inbound Integration Type 'er2er_subject_sharing' not found. Exiting...")
        return

    # This is the ORG to use in PROD for this migrations
    organization, _ = Organization.objects.get_or_create(
        name="ER2ER Subject Sharing Migrated Lambda",
        description="ER2ER Subject Sharing Migrated Lambda organization",
    )

    for filename in os.listdir(SETTINGS_DIR):
        print(f"\n - Processing file: '{filename}'\n")
        total_files += 1
        file_path = os.path.join(SETTINGS_DIR, filename)
        env_vars = extract_env_vars(file_path, filename)
        if not env_vars:
            print_error(f"ENVIRONMENT_VARIABLES not found or empty in '{filename}'", filename)
            files_with_error += 1
            continue

        missing_vars = [var for var in REQUIRED_VARS if var not in env_vars]
        if missing_vars:
            print_error(f"ENVIRONMENT_VARIABLES missing required variables: {', '.join(missing_vars)}", filename)
            files_with_error += 1
            continue

        # First, we get or create a device_group for the new inbound
        inbound_name = '-'.join(filename.split('-')[1:-1])
        device_group_name = f"ER2ER Subjects: {inbound_name} - Default Group"

        device_group, created = DeviceGroup.objects.get_or_create(
            name=device_group_name,
            owner=organization
        )
        if created:
            das_dest = env_vars['DAS_DEST']
            outbound, created = OutboundIntegrationConfiguration.objects.get_or_create(
                type=OutboundIntegrationType.objects.get(slug="earth_ranger"),
                owner=organization,
                name=f"{das_dest} ER Outbound [LAMBDA: {inbound_name}]",
                endpoint=f"{das_dest}/"
            )
            if created:
                outbound.token = env_vars.get('DAS_DEST_AUTH_TOKEN')
                outbound.save()
                print(f"Created Outbound Integration Configuration: '{outbound.name}' for zappa_setting '{filename}'")
                outbounds_created += 1

            device_group.destinations.set([outbound])
            device_group.save()
            print(f"Created Device Group: {device_group_name} for zappa_setting '{filename}'")
            device_groups_created += 1
        else:
            print(f"Device Group already exists with the name: {device_group.name}.")

        das_dest_key = env_vars['DAS_DEST'].split('://', 1)[-1].split('.', 1)[0]
        provider = f"er2er_subjects_to_{das_dest_key}"
        endpoint = f"{env_vars['DAS_SRC']}/api/v1.0"

        # Create the inbound configuration
        inbound, created = InboundIntegrationConfiguration.objects.get_or_create(
            name=f"ER2ER Subjects - {inbound_name}",
            owner=organization,
            type=inbound_type,
            provider=provider,
            default_devicegroup=device_group,
            endpoint=endpoint
        )

        if created:
            inbound.enabled = False # Set to False by default, can be enabled later
            inbound.token = env_vars.get('DAS_SRC_AUTH_TOKEN')
            state = {
                "batch_size": env_vars.get('BATCH_SIZE', 1024),
                "feature_groups": env_vars.get('FEATURE_GROUPS', []),
                "look_back_window_hours": env_vars.get('LOOK_BACK_WINDOW_HOURS', 12),
                "provider_key": get_provider_key(env_vars),
                "schedule_interval_minutes": env_vars.get('SCHEDULE_INTERVAL_MINUTES', 5),
                "subject_additional": True,
            }
            if env_vars.get('SUBJECT_GROUP'):
                state['subject_group'] = env_vars.get('SUBJECT_GROUP')

            inbound.state = state
            inbound.save()
            print(f"Created Inbound Integration Configuration: {inbound.name} for zappa_setting '{filename}'")
            inbounds_created += 1
        else:
            files_skipped += 1
            print(f"Inbound Integration Configuration: {inbound.name} already exists for zappa_setting '{filename}', skipping creation.")

    print(f"\n -- Summary: -- \n")
    print(f"Total files processed: {total_files}")
    print(f"Files skipped: {files_skipped}")
    print(f"Inbounds created: {inbounds_created}")
    print(f"Outbounds created: {outbounds_created}")
    print(f"Device groups created: {device_groups_created}")
    print(f"Files with error: {files_with_error}")


if __name__ == '__main__':
    create_inbounds_from_files()

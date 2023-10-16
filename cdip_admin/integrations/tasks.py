import csv
import logging
import json
import aiofiles
import pydantic
import tempfile
import os

from asgiref.sync import async_to_sync
from celery import shared_task
from django.apps import apps
from integrations.utils import send_message_to_gcp_pubsub
from movebank_client import MovebankClient, MBClientError, PermissionOperations

from gundi_core.schemas.v1 import DestinationTypes
from gundi_core.schemas.v2 import MovebankActions, MBPermissionsActionConfig, MBUserPermission


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=10, retry_kwargs={'max_retries': 3})
def run_integration(self, **kwargs):
    integration_id = kwargs.get("integration_id", None)
    action_id = kwargs.get("action_id", None)
    pubsub_topic = kwargs.get("pubsub_topic", None)

    # Check if we have all the needed kwargs
    if not integration_id or not action_id or not pubsub_topic:
        logger.error(
            'Action cannot be executed. Missing arguments',
            extra={
                "integration_id": integration_id,
                "action_id": action_id,
                "pubsub_topic": pubsub_topic,
                'attention_needed': True
            }
        )
        return

    data = {
        "integration_id": integration_id,
        "action_id": action_id
    }

    # Send pubsub message to GCP
    send_message_to_gcp_pubsub(json.dumps(data), pubsub_topic)


@shared_task(bind=True, autoretry_for=(MBClientError,), retry_backoff=15, retry_kwargs={'max_retries': 3})
def recreate_and_send_movebank_permissions_csv_file(**kwargs):
    logger.info(' -- Recreating Movebank permissions CSV file... --')

    configs = []
    v1_configs = 0
    v2_configs = 0

    # V1 configs
    OutboundIntegrationConfiguration = apps.get_model("integrations", "OutboundIntegrationConfiguration")
    movebank_configs_v1 = OutboundIntegrationConfiguration.objects.filter(
        type__slug=DestinationTypes.Movebank.value,
        additional__has_key="permissions"
    ).values('id', 'additional')

    for mb_config in movebank_configs_v1:
        try:
            permissions = MBPermissionsActionConfig.parse_obj(mb_config["additional"]["permissions"])
        except pydantic.ValidationError:
            logger.exception(
                'Error parsing MBPermissionsActionConfig model (v1)',
                extra={
                    'outbound_integration_id': str(mb_config["id"]),
                    'attention_needed': True
                }
            )
            continue
        else:
            if not permissions.permissions:  # if parsing went ok but no permissions
                permissions.permissions = []
            v1_configs += len(permissions.permissions)
            for config in permissions.permissions:
                configs.append(config)

    # V2 configs
    IntegrationConfiguration = apps.get_model("integrations", "IntegrationConfiguration")
    movebank_configs_v2 = IntegrationConfiguration.objects.filter(
        integration__type__value=DestinationTypes.Movebank.value,
        action__value=MovebankActions.PERMISSIONS.value
    ).values('id', 'data')

    for mb_config in movebank_configs_v2:
        try:
            permissions = MBPermissionsActionConfig.parse_obj(mb_config["data"])
        except pydantic.ValidationError:
            logger.exception(
                'Error parsing MBPermissionsActionConfig model (v2)',
                extra={
                    'integration_configuration_id': str(mb_config["id"]),
                    'attention_needed': True
                }
            )
            continue
        else:
            if not permissions.permissions:  # if parsing went ok but no permissions
                permissions.permissions = []
            v2_configs += len(permissions.permissions)
            for config in permissions.permissions:
                configs.append(config)

    logger.info(f' -- Got {len(configs)} user/tag rows (v1: {v1_configs}, v2: {v2_configs}) --')

    if len(configs) >= 1:
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=MBUserPermission.schema().get("required"))
            writer.writeheader()
            for config in configs:
                writer.writerow(config.dict(by_alias=True))

        logger.info(f' -- CSV temp file created successfully. --')
        logger.info(f' -- Sending CSV file to Movebank... --')

        send_permissions_to_movebank(csvfile.name, **kwargs)

        logger.info(f' -- CSV file uploaded to Movebank successfully --')

        # Permissions file upload was successful, removing CSV file...
        csvfile.close()
        os.unlink(csvfile.name)
    else:
        logger.info(' -- No configs available to send --')


@async_to_sync
async def send_permissions_to_movebank(filename: str, **kwargs):
    client = MovebankClient(**kwargs)
    # Send permissions CSV file to Movebank
    async with aiofiles.open(filename, mode='rb') as perm_file:
        await client.post_permissions(
            study_name="gundi",
            csv_file=perm_file,
            operation=PermissionOperations.UPDATE_USER_PRIVILEGES
        )
    await client.close()  # Close the session used to send requests

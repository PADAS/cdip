import csv
import logging
import aiofiles
import pydantic
import os

from asgiref.sync import async_to_sync
from datetime import datetime, timezone
from celery import shared_task
from django.apps import apps
from movebank_client import MovebankClient, PermissionOperations

from gundi_core.schemas.v1 import DestinationTypes
from gundi_core.schemas.v2 import MovebankActions, MBPermissionsActionConfig, MBUserPermission


logger = logging.getLogger(__name__)


@shared_task
def recreate_and_send_movebank_permissions_csv_file():
    logger.info(' -- Recreating Movebank permissions CSV file... --')

    configs = []
    v1_configs = 0
    v2_configs = 0

    # V1 configs
    OutboundIntegrationConfiguration = apps.get_model("integrations", "OutboundIntegrationConfiguration")
    movebank_configs_v1 = OutboundIntegrationConfiguration.objects.filter(
        type__slug=DestinationTypes.Movebank.value,
        additional__has_key="permissions"
    ).values('additional')

    for mb_config in movebank_configs_v1:
        try:
            permissions = MBPermissionsActionConfig.parse_obj(mb_config["additional"]["permissions"])
        except pydantic.ValidationError:
            logger.exception('Error parsing MBPermissionsActionConfig model', extra={'needs_attention': True})
            return
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
    ).values('data')

    for mb_config in movebank_configs_v2:
        try:
            permissions = MBPermissionsActionConfig.parse_obj(mb_config["data"])
        except pydantic.ValidationError:
            logger.exception('Error parsing MBPermissionsActionConfig model', extra={'needs_attention': True})
            return
        else:
            if not permissions.permissions:  # if parsing went ok but no permissions
                permissions.permissions = []
            v2_configs += len(permissions.permissions)
            for config in permissions.permissions:
                configs.append(config)

    logger.info(f' -- Got {len(configs)} user/tag rows (v1: {v1_configs}, v2: {v2_configs}) --')

    filename = 'movebank_permissions_{}'.format(datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S'))
    with open(filename, 'w', newline="") as f:
        writer = csv.DictWriter(f, fieldnames=MBUserPermission.schema().get("required"))
        writer.writeheader()
        for config in configs:
            writer.writerow(config.dict(by_alias=True))

    logger.info(f' -- CSV file created successfully. filename: {filename} --')
    logger.info(f' -- Sending CSV file to Movebank... --')

    send_permissions_to_movebank(filename)

    logger.info(f' -- CSV file uploaded to Movebank successfully --')


@async_to_sync
async def send_permissions_to_movebank(filename: str):
    client = MovebankClient()
    # Send permissions CSV file to Movebank
    async with aiofiles.open(filename, mode='rb') as perm_file:
        await client.post_permissions(
            study_name="gundi",
            csv_file=perm_file,
            operation=PermissionOperations.UPDATE_USER_PRIVILEGES
        )

    await client.close()  # Close the session used to send requests

    # Permissions file upload was successful, removing CSV file...
    os.remove(filename)

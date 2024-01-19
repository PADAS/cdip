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
from activity_log.models import ActivityLog

from movebank_client import MovebankClient, MBClientError, PermissionOperations
from gundi_core.schemas.v1 import DestinationTypes
from gundi_core.schemas.v2 import MovebankActions, MBPermissionsActionConfig, MBUserPermission


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@shared_task(autoretry_for=(Exception,), retry_backoff=10, retry_kwargs={'max_retries': 3})
def run_integration(integration_id=None, action_id=None, pubsub_topic=None):

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

    try:  # Log the event
        integration = apps.get_model("integrations", "Integration").objects.get(id=integration_id)
        title = f"Action {action_id} triggered for Integration '{integration.name}'"
        ActivityLog.objects.create(
            log_level=ActivityLog.LogLevels.DEBUG,
            log_type=ActivityLog.LogTypes.EVENT,
            origin=ActivityLog.Origin.PORTAL,
            integration=integration,
            value="integration_action_triggered",
            title=title,
            details=data,
            is_reversible=False
        )
    except Exception as e:
        logger.error(
            f"Error logging integration action triggered event: {e}",
            extra={
                "integration_id": integration_id,
                "action": action_id,
                "pubsub_topic": pubsub_topic,
                'attention_needed': True
            }
        )


@shared_task(autoretry_for=(MBClientError,), retry_backoff=15, retry_kwargs={'max_retries': 3})
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
    )

    for mb_config in movebank_configs_v1:
        try:
            permissions = MBPermissionsActionConfig.parse_obj(mb_config.additional["permissions"])
        except pydantic.ValidationError:
            logger.exception(
                'Error parsing MBPermissionsActionConfig model (v1)',
                extra={
                    'outbound_integration_id': str(mb_config.id),
                    'attention_needed': True
                }
            )
            continue
        else:
            if not permissions.permissions:  # if parsing went ok but no permissions
                if not permissions.default_movebank_usernames:  # config does not have usernames set
                    permissions.permissions = []
                else:
                    # create and save preliminary permissions JSON into additional
                    logger.info(' -- No "permissions" set in outbound "additional", creating... --')
                    logger.info(f' -- Usernames to assign: {permissions.default_movebank_usernames} --')
                    permissions.permissions = create_and_save_permissions_json(
                        mb_config,
                        permissions.default_movebank_usernames,
                        "v1"
                    )
                    continue
            v1_configs += len(permissions.permissions)
            for config in permissions.permissions:
                configs.append(config)

    # V2 configs
    IntegrationConfiguration = apps.get_model("integrations", "IntegrationConfiguration")
    movebank_configs_v2 = IntegrationConfiguration.objects.filter(
        integration__type__value=DestinationTypes.Movebank.value,
        action__value=MovebankActions.PERMISSIONS.value
    )

    for mb_config in movebank_configs_v2:
        try:
            permissions = MBPermissionsActionConfig.parse_obj(mb_config.data)
        except pydantic.ValidationError:
            logger.exception(
                'Error parsing MBPermissionsActionConfig model (v2)',
                extra={
                    'integration_configuration_id': str(mb_config.id),
                    'attention_needed': True
                }
            )
            continue
        else:
            if not permissions.permissions:  # if parsing went ok but no permissions
                if not permissions.default_movebank_usernames:  # config does not have usernames set
                    permissions.permissions = []
                else:
                    # create and save preliminary permissions JSON into additional
                    logger.info(' -- No "permissions" set in config "data", creating... --')
                    logger.info(f' -- Usernames to assign: {permissions.default_movebank_usernames} --')
                    permissions.permissions = create_and_save_permissions_json(
                        mb_config,
                        permissions.default_movebank_usernames,
                        "v2"
                    )
                    continue
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


def create_and_save_permissions_json(config, usernames, gundi_version):
    permissions_dict = []
    if gundi_version == "v1":
        logger.info(f' -- Creating v1 permissions set for outbound ID {str(config.id)}... --')
        Device = apps.get_model("integrations", "Device")
        devices = Device.objects.filter(
            devicegroup__destinations__id=config.id
        ).order_by("external_id").distinct("external_id")
        for username in usernames:
            for device in devices:
                permissions_dict.append(
                    MBUserPermission.parse_obj(
                        {
                            "tag_id": f"{device.inbound_configuration.type.slug}."
                                      f"{device.external_id}."
                                      f"{str(device.inbound_configuration.id)}",
                            "username": username
                        }
                    )
                )

        if not permissions_dict:
            logger.info(f' -- No permissions created for outbound ID {str(config.id)}... --')
        else:
            config.additional.get("permissions")["permissions"] = [d.dict() for d in permissions_dict]
            config.save(execute_post_save=False)
            logger.info(f' -- Created {len(permissions_dict)} permissions for outbound ID {str(config.id)}... --')
    else:
        logger.info(f' -- Creating v2 permissions set for config ID {str(config.id)}... --')
        Source = apps.get_model("integrations", "Source")
        sources = Source.objects.filter(
            integration__routing_rules_by_provider__destinations__id=config.integration.id
        ).order_by("external_id").distinct("external_id")

        for username in usernames:
            for source in sources:
                permissions_dict.append(
                    MBUserPermission.parse_obj(
                        {
                            "tag_id": f"{source.integration.type.value}."
                                      f"{source.external_id}."
                                      f"{str(source.integration_id)}",
                            "username": username
                        }
                    )
                )

        if not permissions_dict:
            logger.info(f' -- No permissions created for config ID {str(config.id)}... --')
        else:
            config.data["permissions"] = [d.dict() for d in permissions_dict]
            config.save(execute_post_save=False)
            logger.info(f' -- Created {len(permissions_dict)} permissions for config ID {str(config.id)}... --')

    return permissions_dict


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

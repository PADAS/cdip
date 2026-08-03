import json
import logging
import django
from event_consumers.settings import logging_settings

logging_settings.init()
django.setup()  # To use the django ORM
from google.cloud import pubsub_v1
from django.conf import settings
from django.db import InterfaceError, OperationalError
from event_consumers.db_utils import refresh_db_connections
from gundi_core import events as system_events
from integrations.models import GundiTrace, Integration
from activity_log.models import ActivityLog


logger = logging.getLogger(__name__)


def _clean_event_title(title: str) -> str:
    title = title.strip()
    return title if len(title) < 200 else f"{title[:197]}..."


def handle_integration_action_started_event(event_dict: dict):
    event = system_events.IntegrationActionStarted.parse_obj(event_dict)
    event_data = event.payload
    action_id = event_data.action_id
    integration_id = event_data.integration_id
    integration = Integration.objects.get(id=integration_id)
    message = f"Action '{action_id}' started for integration {integration.name}."
    logger.info(message, extra={"event": event_dict})
    ActivityLog.objects.create(
        log_level=ActivityLog.LogLevels.INFO,
        log_type=ActivityLog.LogTypes.EVENT,
        origin=ActivityLog.Origin.INTEGRATION,
        integration=integration,
        value="integration_action_started",
        title=_clean_event_title(message),
        details=event_dict.get("payload", {}),
        is_reversible=False,
    )


def handle_integration_action_complete_event(event_dict: dict):
    event = system_events.IntegrationActionComplete.parse_obj(event_dict)
    event_data = event.payload
    action_id = event_data.action_id
    integration_id = event_data.integration_id
    integration = Integration.objects.get(id=integration_id)
    message = f"Action '{action_id}' completed."
    logger.info(message, extra={"event": event_dict})
    ActivityLog.objects.create(
        log_level=ActivityLog.LogLevels.INFO,
        log_type=ActivityLog.LogTypes.EVENT,
        origin=ActivityLog.Origin.INTEGRATION,
        integration=integration,
        value="integration_action_complete",
        title=_clean_event_title(message),
        details=event_dict.get("payload", {}),
        is_reversible=False,
    )


def handle_integration_action_failed_event(event_dict: dict):
    event = system_events.IntegrationActionFailed.parse_obj(event_dict)
    event_data = event.payload
    action_id = event_data.action_id
    integration_id = event_data.integration_id
    integration = Integration.objects.get(id=integration_id)
    error = event_data.error
    message = f"Error running action '{action_id}': {error}"
    logger.info(message, extra={"event": event_dict})
    # Workaround to serialize complex types until upgrading to pydantic v2
    log_data_clean = json.loads(json.dumps(event_data.dict(), default=str))
    ActivityLog.objects.create(
        log_level=ActivityLog.LogLevels.ERROR,
        log_type=ActivityLog.LogTypes.EVENT,
        origin=ActivityLog.Origin.INTEGRATION,
        integration=integration,
        value="integration_action_failed",
        title=_clean_event_title(message),
        details=log_data_clean,
        is_reversible=False,
    )


def handle_integration_action_custom_log_event(event_dict: dict):
    event = system_events.IntegrationActionCustomLog.parse_obj(event_dict)
    custom_log = event.payload
    integration_id = custom_log.integration_id
    integration = Integration.objects.get(id=integration_id)
    message = f"Custom Log: {custom_log.title}."
    logger.info(message, extra={"event": event_dict})
    ActivityLog.objects.create(
        log_level=custom_log.level,
        log_type=ActivityLog.LogTypes.EVENT,
        origin=ActivityLog.Origin.INTEGRATION,
        integration=integration,
        value="integration_custom_log",
        title=_clean_event_title(custom_log.title),
        details=event_dict.get("payload", {}),
        is_reversible=False,
    )


def handle_integration_webhook_started_event(event_dict: dict):
    event = system_events.IntegrationWebhookStarted.parse_obj(event_dict)
    event_data = event.payload
    integration_id = event_data.integration_id
    integration = Integration.objects.get(id=integration_id)
    message = f"Webhook request received."
    logger.info(message, extra={"event": event_dict})
    ActivityLog.objects.create(
        log_level=ActivityLog.LogLevels.INFO,
        log_type=ActivityLog.LogTypes.EVENT,
        origin=ActivityLog.Origin.INTEGRATION,
        integration=integration,
        value="integration_webhook_started",
        title=_clean_event_title(message),
        details=event_dict.get("payload", {}),
        is_reversible=False,
    )


def handle_integration_webhook_complete_event(event_dict: dict):
    event = system_events.IntegrationWebhookComplete.parse_obj(event_dict)
    event_data = event.payload
    integration_id = event_data.integration_id
    integration = Integration.objects.get(id=integration_id)
    message = f"Webhook request processing complete."
    logger.info(message, extra={"event": event_dict})
    ActivityLog.objects.create(
        log_level=ActivityLog.LogLevels.INFO,
        log_type=ActivityLog.LogTypes.EVENT,
        origin=ActivityLog.Origin.INTEGRATION,
        integration=integration,
        value="integration_webhook_complete",
        title=_clean_event_title(message),
        details=event_dict.get("payload", {}),
        is_reversible=False,
    )


def handle_integration_webhook_failed_event(event_dict: dict):
    event = system_events.IntegrationWebhookFailed.parse_obj(event_dict)
    event_data = event.payload
    integration_id = event_data.integration_id
    integration = Integration.objects.get(id=integration_id) if integration_id else None
    error = event_dict["payload"].get("error", "No details.")
    logger.info(error, extra={"event": event_dict})
    ActivityLog.objects.create(
        log_level=ActivityLog.LogLevels.ERROR,
        log_type=ActivityLog.LogTypes.EVENT,
        origin=ActivityLog.Origin.INTEGRATION,
        integration=integration,
        value="integration_webhook_failed",
        title=_clean_event_title(error),
        details=event_dict.get("payload", {}),
        is_reversible=False,
    )


def handle_integration_webhook_custom_log_event(event_dict: dict):
    event = system_events.IntegrationWebhookCustomLog.parse_obj(event_dict)
    custom_log = event.payload
    integration_id = custom_log.integration_id
    integration = Integration.objects.get(id=integration_id) if integration_id else None
    message = f"Webhook Custom Log: {custom_log.title}."
    logger.info(message, extra={"event": event_dict})
    ActivityLog.objects.create(
        log_level=custom_log.level,
        log_type=ActivityLog.LogTypes.EVENT,
        origin=ActivityLog.Origin.INTEGRATION,
        integration=integration,
        value="integration_webhook_custom_log",
        title=_clean_event_title(custom_log.title),
        details=event_dict.get("payload", {}),
        is_reversible=False,
    )


event_handlers = {
    "IntegrationActionStarted": handle_integration_action_started_event,
    "IntegrationActionComplete": handle_integration_action_complete_event,
    "IntegrationActionFailed": handle_integration_action_failed_event,
    "IntegrationActionCustomLog": handle_integration_action_custom_log_event,
    "IntegrationWebhookStarted": handle_integration_webhook_started_event,
    "IntegrationWebhookComplete": handle_integration_webhook_complete_event,
    "IntegrationWebhookFailed": handle_integration_webhook_failed_event,
    "IntegrationWebhookCustomLog": handle_integration_webhook_custom_log_event,
}


def process_event(message: pubsub_v1.subscriber.message.Message) -> None:
    logger.info(f"Received Integration Event {message}.")
    # Long-running non-request process: Django's per-request connection
    # cleanup never runs here, so drop dead/expired connections ourselves
    # before touching the ORM (GUNDI-5550).
    refresh_db_connections()
    try:
        event_dict = json.loads(message.data)
    except (ValueError, UnicodeDecodeError):
        logger.exception("Invalid JSON in Integration Event message. Message discarded.")
        message.ack()
        return
    try:
        logger.debug(f"Event Details", extra={"event": event_dict})
        event_type = event_dict.get("event_type")
        schema_version = event_dict.get("schema_version")
        if schema_version != "v1":
            logger.warning(
                f"Schema version '{schema_version}' is not supported. Message discarded."
            )
            message.ack()
            return
        event_handler = event_handlers.get(event_type)
        if not event_handler:
            logger.warning(f"Unknown Event Type {event_type}. Message discarded.")
            message.ack()
            return
        event_handler(event_dict=event_dict)
    except (InterfaceError, OperationalError) as e:
        # Transient DB failure (e.g. "connection already closed"): drop the
        # stale connection and nack so PubSub redelivers instead of losing
        # the event and its activity log record.
        logger.exception(
            f"Error Processing Integration Event: {e}",
            extra={"event": event_dict},
        )
        refresh_db_connections()
        message.nack()
    except Exception as e:
        # Treated as permanent for this message. Ack to avoid a poison-message
        # redelivery loop — the subscription has no dead-letter topic yet.
        logger.exception(
            f"Error Processing Integration Event: {e}",
            extra={"event": event_dict},
        )
        message.ack()
    else:
        logger.info(f"Integration Event Processed successfully.")
        message.ack()


def main():
    while True:  # Keep the consumer running. Reset the connection if it fails.
        try:
            subscriber = pubsub_v1.SubscriberClient()
            subscription_path = subscriber.subscription_path(
                settings.GCP_PROJECT_ID, settings.INTEGRATION_EVENTS_SUB_ID
            )
            streaming_pull_future = subscriber.subscribe(
                subscription_path, callback=process_event
            )
            logger.info(
                f"Integration Events Consumer > Listening for messages on {subscription_path}..\n"
            )

            # Wrap subscriber in a 'with' block to automatically call close() when done.
            with subscriber:
                try:
                    streaming_pull_future.result()
                except Exception as e:
                    logger.exception(f"Internal Error {e}. Shutting down..\n")
                    streaming_pull_future.cancel()  # Trigger the shutdown.
                    streaming_pull_future.result()  # Block until the shutdown is complete.
                    raise e
        except Exception as e:
            logger.exception(f"Internal Error {e}. Restarting..")
            continue


if __name__ == "__main__":
    main()

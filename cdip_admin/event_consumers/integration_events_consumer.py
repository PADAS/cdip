import json
import logging
import django
from event_consumers.settings import logging_settings
logging_settings.init()
django.setup()  # To use the django ORM
from google.cloud import pubsub_v1
from django.conf import settings
from gundi_core import events as system_events
from integrations.models import GundiTrace, Integration
from activity_log.models import ActivityLog


logger = logging.getLogger(__name__)


def handle_integration_action_started_event(event_dict: dict):
    event = system_events.IntegrationActionStarted.parse_obj(event_dict)
    event_data = event.payload
    action_id = event_data.action_id
    integration_id = event_data.integration_id
    integration = Integration.objects.get(id=integration_id)
    message = f"Action '{action_id}' started for integration {integration.name}."
    logger.info(
        message,
        extra={"event": event_dict}
    )
    ActivityLog.objects.create(
        log_level=ActivityLog.LogLevels.INFO,
        log_type=ActivityLog.LogTypes.EVENT,
        origin=ActivityLog.Origin.INTEGRATION,
        integration=integration,
        value="integration_action_started",
        title=message,
        details=event_dict["payload"],
        is_reversible=False
    )


def handle_integration_action_complete_event(event_dict: dict):
    event = system_events.IntegrationActionComplete.parse_obj(event_dict)
    event_data = event.payload
    action_id = event_data.action_id
    integration_id = event_data.integration_id
    integration = Integration.objects.get(id=integration_id)
    message = f"Action '{action_id}' completed."
    logger.info(
        message,
        extra={"event": event_dict}
    )
    ActivityLog.objects.create(
        log_level=ActivityLog.LogLevels.INFO,
        log_type=ActivityLog.LogTypes.EVENT,
        origin=ActivityLog.Origin.INTEGRATION,
        integration=integration,
        value="integration_action_complete",
        title=message,
        details=event_dict["payload"],
        is_reversible=False
    )


def handle_integration_action_failed_event(event_dict: dict):
    event = system_events.IntegrationActionFailed.parse_obj(event_dict)
    event_data = event.payload
    action_id = event_data.action_id
    integration_id = event_data.integration_id
    integration = Integration.objects.get(id=integration_id)
    error = event_dict["payload"].get("error", "No details.")
    message = f"Error running action '{action_id}': {error}"
    logger.info(
        message,
        extra={"event": event_dict}
    )
    ActivityLog.objects.create(
        log_level=ActivityLog.LogLevels.ERROR,
        log_type=ActivityLog.LogTypes.EVENT,
        origin=ActivityLog.Origin.INTEGRATION,
        integration=integration,
        value="integration_action_failed",
        title=message,
        details=event_dict["payload"],
        is_reversible=False
    )


def handle_integration_action_custom_log_event(event_dict: dict):
    event = system_events.IntegrationActionCustomLog.parse_obj(event_dict)
    custom_log = event.payload
    integration_id = custom_log.integration_id
    integration = Integration.objects.get(id=integration_id)
    message = f"Custom Log: {custom_log.title}."
    logger.info(
        message,
        extra={"event": event_dict}
    )
    ActivityLog.objects.create(
        log_level=custom_log.level,
        log_type=ActivityLog.LogTypes.EVENT,
        origin=ActivityLog.Origin.INTEGRATION,
        integration=integration,
        value="integration_custom_log",
        title=custom_log.title,
        details=event_dict["payload"],
        is_reversible=False
    )


event_handlers = {
    "IntegrationActionStarted": handle_integration_action_started_event,
    "IntegrationActionComplete": handle_integration_action_complete_event,
    "IntegrationActionFailed": handle_integration_action_failed_event,
    "IntegrationActionCustomLog": handle_integration_action_custom_log_event
}


def process_event(message: pubsub_v1.subscriber.message.Message) -> None:
    try:
        logger.info(f"Received Integration Event {message}.")
        event_dict = json.loads(message.data)
        logger.debug(f"Event Details", extra={"event": event_dict})
        event_type = event_dict.get("event_type")
        schema_version = event_dict.get("schema_version")
        if schema_version != "v1":
            logger.warning(f"Schema version '{schema_version}' is not supported. Message discarded.")
            message.ack()
            return
        event_handler = event_handlers.get(event_type)
        if not event_handler:
            logger.warning(f"Unknown Event Type {event_type}. Message discarded.")
            message.ack()
            return
        event_handler(event_dict=event_dict)
    except Exception as e:
        logger.exception(f"Error Processing Integration Event: {e}", extra={"event": json.loads(message.data)})
    else:
        logger.info(f"Integration Event Processed successfully.")
    finally:
        message.ack()


def main():
    while True:  # Keep the consumer running. Reset the connection if it fails.
        try:
            subscriber = pubsub_v1.SubscriberClient()
            subscription_path = subscriber.subscription_path(
                settings.GCP_PROJECT_ID,
                settings.INTEGRATION_EVENTS_SUB_ID
            )
            streaming_pull_future = subscriber.subscribe(
                subscription_path,
                callback=process_event
            )
            logger.info(f"Integration Events Consumer > Listening for messages on {subscription_path}..\n")

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


if __name__ == '__main__':
    main()

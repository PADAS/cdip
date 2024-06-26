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


def handle_observation_delivered_event(event_dict: dict):
    event = system_events.ObservationDelivered.parse_obj(event_dict)
    # Update the status and save the external id
    event_data = event.payload
    logger.info(
        f"Observation Delivery Succeeded for gundi_id: {event_data.gundi_id}, destination_id: {event_data.destination_id}",
        extra={"event": event_dict}
    )
    # Look for traces in the database
    traces = GundiTrace.objects.filter(object_id=event_data.gundi_id)
    logger.debug(
        f"Observation Delivery Succeeded for gundi_id: {event_data.gundi_id}, destination_id: {event_data.destination_id}",
        extra={"event": event_dict}
    )
    if not traces.exists():  # This shouldn't happen
        logger.warning(f"Unknown Observation with id {event_data.gundi_id}. Event Ignored.")
        return

    trace_count = traces.count()
    logger.debug(
        f"Trace count for gundi_id: {event_data.gundi_id}: {trace_count}",
        extra={"event": event_dict}
    )
    if trace_count > 1:  # Multiple destinations
        trace = traces.filter(destination_id=event_data.destination_id).first()
    else:
        trace = traces.first()

    if not trace.destination or str(event_data.destination_id) == str(trace.destination.id):  # Update
        logger.debug(
            f"Updating trace as delivered for gundi_id {event_data.gundi_id}, destination_id: {event_data.destination_id}",
            extra={"event": event_dict}
        )
        trace.destination_id = event_data.destination_id
        trace.delivered_at = event_data.delivered_at
        trace.external_id = event_data.external_id
        trace.has_error = False
        trace.error = ""
        trace.save()
    else:
        logger.debug(
            f"Creating trace as delivered for gundi_id {event_data.gundi_id}, new destination_id: {event_data.destination_id}",
            extra={"event": event_dict}
        )
        trace = GundiTrace.objects.create(
            object_id=trace.object_id,
            object_type=trace.object_type,
            related_to=event_data.related_to,
            created_by=trace.created_by,
            data_provider=trace.data_provider,
            destination_id=event_data.destination_id,
            delivered_at=event_data.delivered_at,
            external_id=event_data.external_id,
        )

    logger.debug(
        f"Recording delivery event in the activity log for gundi_id {event_data.gundi_id}, new destination_id: {event_data.destination_id}",
        extra={"event": event_dict}
    )
    title = f"Observation Delivered to '{trace.destination.base_url}'"
    ActivityLog.objects.create(
        log_level=ActivityLog.LogLevels.DEBUG,
        log_type=ActivityLog.LogTypes.EVENT,
        origin=ActivityLog.Origin.DISPATCHER,
        integration=trace.data_provider,
        value="observation_delivery_succeeded",
        title=title,
        details=event_dict["payload"],
        is_reversible=False
    )


def handle_observation_delivery_failed_event(event_dict: dict):
    event = system_events.ObservationDeliveryFailed.parse_obj(event_dict)
    # Update the status and save the external id
    event_data = event.payload
    logger.warning(
        f"Observation Delivery Failed. gundi_id: {event_data.gundi_id}",
        extra={"event": event_dict}
    )
    # Look for traces in the database
    traces = GundiTrace.objects.filter(object_id=event_data.gundi_id)
    if not traces.exists():  # This shouldn't happen
        logger.warning(f"Unknown Observation with id {event_data.gundi_id}. Event Ignored.")
        return
    # Update the db with the event data
    trace = traces.first()
    if not trace.destination:  # First destination
        logger.debug(
            f"Updating trace with error for gundi_id {event_data.gundi_id}, destination_id: {event_data.destination_id}",
            extra={"event": event_dict}
        )
        trace.destination_id = event_data.destination_id
        trace.has_error = True
        trace.error = "Delivery Failed at the Dispatcher."
        trace.save()
    elif str(event_data.destination_id) != str(trace.destination.id):  # Multiple destinations
        logger.debug(
            f"Creating trace with error for gundi_id {event_data.gundi_id}, new destination_id: {event_data.destination_id}",
            extra={"event": event_dict}
        )
        GundiTrace.objects.create(
            object_id=trace.object_id,
            object_type=trace.object_type,
            related_to=event_data.related_to,
            created_by=trace.created_by,
            data_provider=trace.data_provider,
            destination_id=event_data.destination_id,
            delivered_at=event_data.delivered_at,
            external_id=event_data.external_id,
            has_error=True,
            error="Delivery Failed at the Dispatcher."
        )
    else:
        logger.warning(
            f"Trace was not updated due to possible duplicated event. gundi_id: {event_data.gundi_id}",
            extra={"event": event_dict}
        )

    logger.debug(
        f"Recording delivery error event in the activity log for gundi_id {event_data.gundi_id}, new destination_id: {event_data.destination_id}",
        extra={"event": event_dict}
    )
    title = f"Error Delivering observation to '{trace.destination.base_url}'"
    ActivityLog.objects.create(
        log_level=ActivityLog.LogLevels.ERROR,
        log_type=ActivityLog.LogTypes.EVENT,
        origin=ActivityLog.Origin.DISPATCHER,
        integration=trace.data_provider,
        value="observation_delivery_failed",
        title=title,
        details=event_dict["payload"],
        is_reversible=False
    )


event_handlers = {
    "ObservationDelivered": handle_observation_delivered_event,
    "ObservationDeliveryFailed": handle_observation_delivery_failed_event
}


def process_event(message: pubsub_v1.subscriber.message.Message) -> None:
    try:
        logger.info(f"Received Dispatcher Event {message}.")
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
        logger.exception(f"Error Processing Dispatcher Event: {e}", extra={"event": json.loads(message.data)})
    else:
        logger.info(f"Dispatcher Event Processed successfully.")
    finally:
        message.ack()


def main():
    while True:  # Keep the consumer running. Reset the connection if it fails.
        try:
            subscriber = pubsub_v1.SubscriberClient()
            subscription_path = subscriber.subscription_path(
                settings.GCP_PROJECT_ID,
                settings.DISPATCHER_EVENTS_SUB_ID
            )
            streaming_pull_future = subscriber.subscribe(
                subscription_path,
                callback=process_event
            )
            logger.info(f"Dispatcher Events Consumer > Listening for messages on {subscription_path}..\n")

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

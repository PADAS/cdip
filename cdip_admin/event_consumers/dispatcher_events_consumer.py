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


data_type_str_map = {
    "obv": "Observation",
    "ev": "Event",
    "att": "Attachment"
}


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
            source=trace.source,
            related_to=event_data.related_to or None,  # Empy string to None
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
    data_type = data_type_str_map.get(trace.object_type, "Data")
    title = f"{data_type} {trace.object_id} Delivered to '{trace.destination.base_url}'"
    log_data = {
        **event_dict["payload"],
        "source_external_id": str(trace.source.external_id) if trace.source else None,
    }
    ActivityLog.objects.create(
        log_level=ActivityLog.LogLevels.DEBUG,
        log_type=ActivityLog.LogTypes.EVENT,
        origin=ActivityLog.Origin.DISPATCHER,
        integration=trace.data_provider,
        value="observation_delivery_succeeded",
        title=title,
        details=log_data,
        is_reversible=False
    )


def build_delivery_failed_event_v2_from_v1_data(event_dict: dict) -> system_events.ObservationDeliveryFailed:
    v1_payload = event_dict.get("payload")
    return system_events.ObservationDeliveryFailed(
        payload=system_events.DeliveryErrorDetails(
            error="Delivery Failed at the Dispatcher. Please update this dispatcher to see more details here.",
            observation=system_events.DispatchedObservation.parse_obj(v1_payload)
        )
    )


def handle_observation_delivery_failed_event(event_dict: dict):
    schema_version = event_dict.get("schema_version")
    if schema_version == "v1":
        event = build_delivery_failed_event_v2_from_v1_data(event_dict)
        destination_id = event.payload.observation.destination_id
        logger.warning(
            f"Event schema version v1 is deprecated. Please update the dispatcher of destination {destination_id}."
        )
    else:
        event = system_events.ObservationDeliveryFailed.parse_obj(event_dict)
    # Update the status and save the external id
    event_data = event.payload
    observation = event_data.observation
    logger.warning(
        f"Observation Delivery Failed. gundi_id: {observation.gundi_id}",
        extra={"event": event_dict}
    )
    # Look for traces in the database
    traces = GundiTrace.objects.filter(object_id=observation.gundi_id)
    if not traces.exists():  # This shouldn't happen
        logger.warning(f"Unknown Observation with id {observation.gundi_id}. Event Ignored.")
        return
    # Update the db with the event data
    trace = traces.first()
    if not trace.destination:  # First destination
        logger.debug(
            f"Updating trace with error for gundi_id {observation.gundi_id}, destination_id: {observation.destination_id}",
            extra={"event": event_dict}
        )
        trace.destination_id = observation.destination_id
        trace.has_error = True
        trace.error = "Delivery Failed at the Dispatcher."
        trace.save()
    elif str(observation.destination_id) != str(trace.destination.id):  # Multiple destinations
        logger.debug(
            f"Creating trace with error for gundi_id {observation.gundi_id}, new destination_id: {observation.destination_id}",
            extra={"event": event_dict}
        )
        trace = GundiTrace.objects.create(
            object_id=trace.object_id,
            object_type=trace.object_type,
            source=trace.source,
            related_to=observation.related_to or None,  # Empy string to None
            created_by=trace.created_by,
            data_provider=trace.data_provider,
            destination_id=observation.destination_id,
            delivered_at=observation.delivered_at,
            external_id=observation.external_id,
            has_error=True,
            error="Delivery Failed at the Dispatcher."
        )
    else:
        logger.warning(
            f"Trace was not updated due to possible duplicated event. gundi_id: {observation.gundi_id}",
            extra={"event": event_dict}
        )

    logger.debug(
        f"Recording delivery error event in the activity log for gundi_id {observation.gundi_id}, new destination_id: {observation.destination_id}",
        extra={"event": event_dict}
    )
    data_type = data_type_str_map.get(trace.object_type, "Data")
    title = f"Error Delivering {data_type} {trace.object_id} to '{trace.destination.base_url}'"
    log_data = {
        **event.payload.dict(),
        "source_external_id": str(trace.source.external_id) if trace.source else None,
    }
    ActivityLog.objects.create(
        log_level=ActivityLog.LogLevels.ERROR,
        log_type=ActivityLog.LogTypes.EVENT,
        origin=ActivityLog.Origin.DISPATCHER,
        integration=trace.data_provider,
        value="observation_delivery_failed",
        title=title,
        details=log_data,
        is_reversible=False
    )


def handle_observation_updated_event(event_dict: dict):
    event = system_events.ObservationUpdated.parse_obj(event_dict)
    # Update the status and save the external id
    event_data = event.payload
    gundi_id = str(event_data.gundi_id)
    destination_id = str(event_data.destination_id)
    logger.info(
        f"Observation Update Succeeded for gundi_id: {gundi_id}, destination_id: {destination_id}",
        extra={"event": event_dict}
    )
    # Look the related trace in the database
    try:
        trace = GundiTrace.objects.get(object_id=gundi_id, destination__id=destination_id)
    except GundiTrace.DoesNotExist:
        logger.warning(f"Unknown Observation with id {gundi_id} for destination {destination_id}. Event Ignored.")
        return
    # Save the time when it was updated in the destination system
    trace.last_update_delivered_at = event_data.updated_at
    trace.save()
    # Generate Activity log to be seen in the portal
    logger.debug(
        f"Recording update event in the activity log for gundi_id {event_data.gundi_id}, new destination_id: {event_data.destination_id}",
        extra={"event": event_dict}
    )
    data_type = data_type_str_map.get(trace.object_type, "Data")
    title = f"{data_type} {gundi_id} updated in '{trace.destination.base_url}'"
    log_data = {
        **event_dict["payload"],
        "source_external_id": str(trace.source.external_id) if trace.source else None,
    }
    ActivityLog.objects.create(
        log_level=ActivityLog.LogLevels.DEBUG,
        log_type=ActivityLog.LogTypes.EVENT,
        origin=ActivityLog.Origin.DISPATCHER,
        integration=trace.data_provider,
        value="observation_update_succeeded",
        title=title,
        details=log_data,
        is_reversible=False
    )


def build_update_failed_event_v2_from_v1_data(event_dict: dict) -> system_events.ObservationUpdateFailed:
    v1_payload = event_dict.get("payload")
    return system_events.ObservationUpdateFailed(
        payload=system_events.UpdateErrorDetails(
            error="Update Failed at the Dispatcher. Please update this dispatcher to see more details here.",
            observation=system_events.UpdatedObservation.parse_obj(v1_payload)
        )
    )


def handle_observation_update_failed_event(event_dict: dict):
    schema_version = event_dict.get("schema_version")
    if schema_version == "v1":
        event = build_update_failed_event_v2_from_v1_data(event_dict)
        destination_id = event.payload.observation.destination_id
        logger.warning(
            f"Event schema version v1 is deprecated. Please update the dispatcher of destination {destination_id}."
        )
    else:
        event = system_events.ObservationUpdateFailed.parse_obj(event_dict)
    event_data = event.payload
    observation = event_data.observation
    gundi_id = str(observation.gundi_id)
    destination_id = str(observation.destination_id)
    logger.warning(
        f"Observation Update Failed. gundi_id: {gundi_id}, destination_id: {destination_id}",
        extra={"event": event_dict}
    )
    # Look the related trace in the database
    try:
        trace = GundiTrace.objects.get(object_id=gundi_id, destination__id=destination_id)
    except GundiTrace.DoesNotExist:
        logger.warning(f"Unknown Observation with id {gundi_id} for destination {destination_id}. Event Ignored.")
        return
    # Update the trace with the error
    trace.has_error = True
    trace.error = "Update Failed at the Dispatcher."
    trace.save()
    # Generate Activity log to be seen in the portal
    logger.debug(
        f"Recording update error event in the activity log for gundi_id {gundi_id}, destination_id: {destination_id}",
        extra={"event": event_dict}
    )
    data_type = data_type_str_map.get(trace.object_type, "Data")
    title = f"Error Updating {data_type} {gundi_id} in '{trace.destination.base_url}'"
    log_data = {
        **event.payload.dict(),
        "source_external_id": str(trace.source.external_id) if trace.source else None,
    }
    ActivityLog.objects.create(
        log_level=ActivityLog.LogLevels.ERROR,
        log_type=ActivityLog.LogTypes.EVENT,
        origin=ActivityLog.Origin.DISPATCHER,
        integration=trace.data_provider,
        value="observation_update_failed",
        title=title,
        details=log_data,
        is_reversible=False
    )


def handle_dispatcher_log_event(event_dict):
    event = system_events.DispatcherCustomLog.parse_obj(event_dict)
    event_data = event.payload
    gundi_id = str(event_data.gundi_id)
    destination_id = str(event_data.destination_id)
    logger.info(
        f"Dispatcher Custom Log Event. gundi_id: {gundi_id}, destination_id: {destination_id}: \n{event_data.title}",
        extra={"event": event_dict}  # FixMe: extra doesn't show up in GCP logs
    )
    # Look the related trace in the database
    trace = GundiTrace.objects.filter(object_id=gundi_id).first()
    if not trace:
        logger.warning(f"Unknown Observation with id {gundi_id}. Event Ignored.")
        return
    # Look for the related destination integration
    integration = Integration.objects.filter(id=destination_id).first()
    if not integration:
        logger.warning(f"Unknown Destination Integration with id {destination_id}. Event Ignored.")
        return
    # Generate Activity log to be seen in the portal
    title = event_data.title
    log_data = {
        **event_dict["payload"],
        "source_external_id": str(trace.source.external_id) if trace.source else None,
    }
    ActivityLog.objects.create(
        log_level=event_data.level,
        log_type=ActivityLog.LogTypes.EVENT,
        origin=ActivityLog.Origin.DISPATCHER,
        integration=integration,
        value="custom_dispatcher_log",
        title=title,
        details=log_data,
        is_reversible=False
    )


event_handlers = {
    "ObservationDelivered": handle_observation_delivered_event,
    "ObservationDeliveryFailed": handle_observation_delivery_failed_event,
    "ObservationUpdated": handle_observation_updated_event,
    "ObservationUpdateFailed": handle_observation_update_failed_event,
    "DispatcherCustomLog": handle_dispatcher_log_event
}


def process_event(message: pubsub_v1.subscriber.message.Message) -> None:
    try:
        logger.info(f"Received Dispatcher Event {message}.")
        event_dict = json.loads(message.data)
        logger.debug(f"Event Details", extra={"event": event_dict})
        event_type = event_dict.get("event_type")
        schema_version = event_dict.get("schema_version")
        if schema_version not in ["v1", "v2"]:
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

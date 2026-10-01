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
from integrations.models import GundiTrace
from activity_log.models import ActivityLog


logger = logging.getLogger(__name__)


data_type_str_map = {
    "obv": "Observation",
    "ev": "Event",
    "att": "Attachment"
}


def handle_observation_filtered_event(event_dict: dict):
    event = system_events.ObservationFiltered.parse_obj(event_dict)
    event_data = event.payload
    gundi_id = str(event_data.gundi_id)
    destination_id = str(event_data.destination_id)
    logger.info(
        f"Observation Filtered. gundi_id: {gundi_id}, destination_id: {destination_id}, "
        f"filtered_by: {event_data.filtered_by}",
        extra={"event": event_dict}
    )
    traces = GundiTrace.objects.filter(object_id=gundi_id)
    if not traces.exists():  # This shouldn't happen
        logger.warning(f"Unknown Observation with id {gundi_id}. Event Ignored.")
        return

    # A filtered observation was dropped before transform/dispatch, so the trace
    # for this destination is usually still the unbound ingestion row. Bind it,
    # or add a row when other destinations already claimed the existing ones.
    bound = next(
        (t for t in traces if t.destination_id and str(t.destination_id) == destination_id),
        None,
    )
    unbound = next((t for t in traces if not t.destination_id), None)
    trace = bound or unbound
    if trace:
        trace.destination_id = destination_id
        trace.save()
    else:
        base = traces.first()
        trace = GundiTrace.objects.create(
            object_id=base.object_id,
            object_type=base.object_type,
            source=base.source,
            related_to=event_data.related_to or None,
            created_by=base.created_by,
            data_provider=base.data_provider,
            destination_id=destination_id,
        )

    # Filtering is configured behavior, not a failure: INFO, and never
    # has_error, so connection health is unaffected.
    data_type = data_type_str_map.get(trace.object_type, "Data")
    destination_str = trace.destination.base_url if trace.destination else destination_id
    title = f"{data_type} {gundi_id} filtered out for '{destination_str}'"
    log_data = {
        **event_dict["payload"],
        "source_external_id": str(trace.source.external_id) if trace.source else None,
    }
    ActivityLog.objects.create(
        log_level=ActivityLog.LogLevels.INFO,
        log_type=ActivityLog.LogTypes.EVENT,
        origin=ActivityLog.Origin.TRANSFORMER,
        integration=trace.data_provider,
        value="observation_filtered",
        title=title,
        details=log_data,
        is_reversible=False
    )


# Schema versions are validated per event type, not globally: each event in
# this topic pins its own version in gundi-core, so a bump in one event must
# not make the consumer discard the others.
event_handlers = {
    "ObservationFiltered": (handle_observation_filtered_event, {"v1"}),
}


def process_event(message: pubsub_v1.subscriber.message.Message) -> None:
    logger.info(f"Received Routing Event {message}.")
    # Long-running non-request process: Django's per-request connection
    # cleanup never runs here, so drop dead/expired connections ourselves
    # before touching the ORM (GUNDI-5550).
    refresh_db_connections()
    try:
        event_dict = json.loads(message.data)
    except (ValueError, UnicodeDecodeError):
        logger.exception("Invalid JSON in Routing Event message. Message discarded.")
        message.ack()
        return
    try:
        logger.debug(f"Event Details", extra={"event": event_dict})
        event_type = event_dict.get("event_type")
        schema_version = event_dict.get("schema_version")
        handler_entry = event_handlers.get(event_type)
        if not handler_entry:
            logger.warning(f"Unknown Event Type {event_type}. Message discarded.")
            message.ack()
            return
        event_handler, supported_versions = handler_entry
        if schema_version not in supported_versions:
            logger.warning(
                f"Schema version '{schema_version}' is not supported for {event_type}. Message discarded."
            )
            message.ack()
            return
        event_handler(event_dict=event_dict)
    except (InterfaceError, OperationalError) as e:
        # Transient DB failure (e.g. "connection already closed"): drop the
        # stale connection and nack so PubSub redelivers instead of losing
        # the event and its activity log record.
        logger.exception(
            f"Error Processing Routing Event: {e}",
            extra={"event": event_dict},
        )
        refresh_db_connections()
        message.nack()
    except Exception as e:
        # Treated as permanent for this message. Ack to avoid a poison-message
        # redelivery loop — the subscription has no dead-letter topic yet.
        logger.exception(
            f"Error Processing Routing Event: {e}",
            extra={"event": event_dict},
        )
        message.ack()
    else:
        logger.info(f"Routing Event Processed successfully.")
        message.ack()


def main():
    while True:  # Keep the consumer running. Reset the connection if it fails.
        try:
            subscriber = pubsub_v1.SubscriberClient()
            subscription_path = subscriber.subscription_path(
                settings.GCP_PROJECT_ID, settings.ROUTING_EVENTS_SUB_ID
            )
            streaming_pull_future = subscriber.subscribe(
                subscription_path, callback=process_event
            )
            logger.info(
                f"Routing Events Consumer > Listening for messages on {subscription_path}..\n"
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

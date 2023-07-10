import json
import logging
import django
django.setup()  # To use the django ORM
from google.cloud import pubsub_v1
from django.conf import settings
from gundi_core import events as system_events
from integrations.models import GundiTrace, Integration


def handle_observation_delivered_event(event_dict: dict):
    event = system_events.ObservationDelivered.parse_obj(event_dict)
    # Update the status and save the external id
    event_data = event.payload
    # Look for traces in the database
    traces = GundiTrace.objects.filter(object_id=event_data.gundi_id)
    trace_count = traces.count()
    if trace_count == 0:  # This shouldn't happen
        # Create the trace in the database?
        pass
    elif trace_count > 0:
        # Update with the event data
        trace = traces.first()
        if not trace.destination:  # Single destination
            trace.destination = Integration.objects.get(id=event_data.destination_id)
            trace.delivered_at = event_data.delivered_at
            trace.external_id = event_data.external_id
            trace.save()
        else:  # Multiple destinations
            GundiTrace.objects.create(
                object_id=trace.object_id,
                object_type=trace.object_type,
                related_to=event_data.related_to,
                created_by=trace.created_by,
                data_provider=trace.data_provider,
                destination=event_data.destination_id,
                delivered_at=event_data.delivered_at,
                external_id=event_data.external_id
            )


event_handlers = {
    "ObservationDelivered": handle_observation_delivered_event
}


def process_event(message: pubsub_v1.subscriber.message.Message) -> None:
    print(f"Received Dispatcher Event {message}.")
    event_dict = json.loads(message.data)
    event_type = event_dict.get("event_type")
    event_handler = event_handlers.get(event_type)
    if not event_handler:
        print(f"Unknown Event Type {event_type}. Message discarded.")
        return
    event_handler(event_dict=event_dict)
    message.ack()
    print(f"Dispatcher Event Processed successfully.")


if __name__ == '__main__':
    subscriber = pubsub_v1.SubscriberClient()
    subscription_path = subscriber.subscription_path(
        settings.GCP_PROJECT_ID,
        settings.DISPATCHER_EVENTS_SUB_ID
    )
    streaming_pull_future = subscriber.subscribe(
        subscription_path,
        callback=process_event
    )
    print(f"Dispatcher Events Consumer > Listening for messages on {subscription_path}..\n")

    # Wrap subscriber in a 'with' block to automatically call close() when done.
    with subscriber:
        try:
            streaming_pull_future.result()
        except Exception:
            streaming_pull_future.cancel()  # Trigger the shutdown.
            streaming_pull_future.result()  # Block until the shutdown is complete.

import pytest
import json
from event_consumers.dispatcher_events_consumer import process_event
from integrations.models import GundiTrace


pytestmark = pytest.mark.django_db


def test_process_observation_delivered_event_with_single_destination(
        trap_tagger_event_trace, trap_tagger_observation_delivered_event
):
    # Test the case when an observation is delivered to a single destination successfully
    process_event(trap_tagger_observation_delivered_event)
    event_data = json.loads(trap_tagger_observation_delivered_event.data)["payload"]
    trap_tagger_event_trace.refresh_from_db()
    assert str(trap_tagger_event_trace.destination.id) == str(event_data["destination_id"])
    assert str(trap_tagger_event_trace.external_id) == str(event_data["external_id"])
    assert str(trap_tagger_event_trace.delivered_at) == str(event_data["delivered_at"])


def test_process_observation_delivered_event_with_two_destinations(
        trap_tagger_event_trace, trap_tagger_observation_delivered_event, trap_tagger_observation_delivered_event_two
):
    # Test the case when an observation is delivered to two destinations successfully
    process_event(trap_tagger_observation_delivered_event)  # One event for one destination
    process_event(trap_tagger_observation_delivered_event_two)  # A second event for the other destination
    # Check that we have two traces in the database now (for the second destination)
    event_data = json.loads(trap_tagger_observation_delivered_event.data)["payload"]
    assert GundiTrace.objects.filter(object_id=event_data["gundi_id"]).count() == 2

    # Check that the data related to the first destination was saved in the database
    trace_one = GundiTrace.objects.get(
        object_id=event_data["gundi_id"],
        destination__id=event_data["destination_id"]
    )
    assert str(trace_one.external_id) == str(event_data["external_id"])

    # Check that the data related to the second destination was saved in the database
    event_data = json.loads(trap_tagger_observation_delivered_event_two.data)["payload"]
    trace_two = GundiTrace.objects.get(
        object_id=event_data["gundi_id"],
        destination__id=event_data["destination_id"]
    )
    assert str(trace_two.external_id) == str(event_data["external_id"])


def test_process_observation_delivery_failed_event(
        trap_tagger_event_trace, trap_tagger_observation_delivery_failed_event
):
    # Test the case when an observation fails to get delivered and we receive the event notification
    process_event(trap_tagger_observation_delivery_failed_event)
    trap_tagger_event_trace.refresh_from_db()
    # Check that the error is recorded
    assert trap_tagger_event_trace.has_error
    assert trap_tagger_event_trace.error == "Delivery Failed at the Dispatcher."
    # Other fields must not be updated as the delivery has failed
    assert trap_tagger_event_trace.destination
    assert not trap_tagger_event_trace.external_id
    assert not trap_tagger_event_trace.delivered_at


def test_process_observation_delivered_event_without_external_id(
        trap_tagger_to_movebank_observation_trace, trap_tagger_to_movebank_observation_delivered_event
):
    # Test the case when an observation is delivered to a single destination successfully
    # But no external id is returned. (for example, Movebank)
    process_event(trap_tagger_to_movebank_observation_delivered_event)
    event_data = json.loads(trap_tagger_to_movebank_observation_delivered_event.data)["payload"]
    trap_tagger_to_movebank_observation_trace.refresh_from_db()
    assert str(trap_tagger_to_movebank_observation_trace.destination.id) == str(event_data["destination_id"])
    assert not trap_tagger_to_movebank_observation_trace.external_id  # Movebank API doesn't return an ID
    assert str(trap_tagger_to_movebank_observation_trace.delivered_at) == str(event_data["delivered_at"])


def test_process_observation_delivered_event_after_retry_with_single_destination(
        trap_tagger_event_trace, trap_tagger_observation_delivery_failed_event, trap_tagger_observation_delivered_event
):
    # Test the case when an observation fails to get delivered the first time
    # and succeeds on a second try.
    process_event(trap_tagger_observation_delivery_failed_event)
    trap_tagger_event_trace.refresh_from_db()
    assert trap_tagger_event_trace.has_error
    assert trap_tagger_event_trace.error == "Delivery Failed at the Dispatcher."
    process_event(trap_tagger_observation_delivered_event)
    event_data = json.loads(trap_tagger_observation_delivered_event.data)["payload"]
    trap_tagger_event_trace.refresh_from_db()
    assert not trap_tagger_event_trace.has_error
    assert not trap_tagger_event_trace.error
    assert str(trap_tagger_event_trace.destination.id) == str(event_data["destination_id"])
    assert str(trap_tagger_event_trace.external_id) == str(event_data["external_id"])
    assert str(trap_tagger_event_trace.delivered_at) == str(event_data["delivered_at"])


def test_process_observation_delivered_event_after_retry_with_two_destinations(
        trap_tagger_event_trace,
        trap_tagger_observation_delivery_failed_event,
        trap_tagger_observation_delivery_failed_event_two,
        trap_tagger_observation_delivered_event,
        trap_tagger_observation_delivered_event_two
):
    # Test the case when an observation fails to get delivered the first time to two destinations
    # and succeeds on a second try for both destinations
    process_event(trap_tagger_observation_delivery_failed_event)
    trap_tagger_event_trace.refresh_from_db()
    assert trap_tagger_event_trace.has_error
    assert trap_tagger_event_trace.error == "Delivery Failed at the Dispatcher."
    process_event(trap_tagger_observation_delivery_failed_event_two)
    event_2_data = json.loads(trap_tagger_observation_delivered_event_two.data)["payload"]
    trap_tagger_event_trace_2 = GundiTrace.objects.get(
        object_id=trap_tagger_event_trace.object_id,
        destination__id=str(event_2_data["destination_id"])
    )
    assert trap_tagger_event_trace_2.has_error
    assert trap_tagger_event_trace_2.error == "Delivery Failed at the Dispatcher."

    process_event(trap_tagger_observation_delivered_event)
    event_data = json.loads(trap_tagger_observation_delivered_event.data)["payload"]
    trap_tagger_event_trace.refresh_from_db()
    assert not trap_tagger_event_trace.has_error
    assert not trap_tagger_event_trace.error
    assert str(trap_tagger_event_trace.destination.id) == str(event_data["destination_id"])
    assert str(trap_tagger_event_trace.external_id) == str(event_data["external_id"])
    assert str(trap_tagger_event_trace.delivered_at) == str(event_data["delivered_at"])

    process_event(trap_tagger_observation_delivered_event_two)
    event_data = json.loads(trap_tagger_observation_delivered_event_two.data)["payload"]
    trap_tagger_event_trace_2.refresh_from_db()
    assert not trap_tagger_event_trace_2.has_error
    assert not trap_tagger_event_trace_2.error
    assert str(trap_tagger_event_trace_2.destination.id) == str(event_data["destination_id"])
    assert str(trap_tagger_event_trace_2.external_id) == str(event_data["external_id"])
    assert str(trap_tagger_event_trace_2.delivered_at) == str(event_data["delivered_at"])



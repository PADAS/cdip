import pytest
from django.urls import reverse
from rest_framework import status
from integrations.models import (
    GundiTrace
)


pytestmark = pytest.mark.django_db


def _test_list_traces(api_client, user, expected_traces, params=None):
    api_client.force_authenticate(user)
    params = params or {}
    response = api_client.get(
        reverse("traces-list"),
        params
    )
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    traces = response_data["results"]
    expected_trace_ids = [str(uid) for uid in expected_traces]
    assert len(traces) == len(expected_traces)
    for trace in traces:
        assert trace.get("object_id") in expected_trace_ids
        assert "object_id" in trace
        assert "object_type" in trace
        assert "related_to" in trace
        assert "data_provider" in trace
        assert "destination" in trace
        assert "delivered_at" in trace
        assert "external_id" in trace
        assert "created_at" in trace
        assert "updated_at" in trace


def test_list_traces_as_superuser(
        api_client, superuser,
        event_delivered_trace, attachment_delivered_trace, event_delivered_trace2
):
    _test_list_traces(
        api_client=api_client,
        user=superuser,
        expected_traces=[event_delivered_trace, event_delivered_trace2, attachment_delivered_trace]
    )


def test_filter_traces_as_superuser(
        api_client, superuser,
        event_delivered_trace, event_delivered_trace2, attachment_delivered_trace
):
    _test_list_traces(
        api_client=api_client,
        user=superuser,
        params={
            "object_id": str(event_delivered_trace2.object_id),
            "destination": str(event_delivered_trace2.destination.id)
        },
        expected_traces=[event_delivered_trace2]
    )


def test_trace_retrieve_exposes_the_discard_fields(
        api_client, superuser, lotek_observation_trace
):
    # A filtered trace must not look identical to one still in flight: the
    # timestamp is the flag, the reason says which rule kind dropped it.
    lotek_observation_trace.discarded_at = "2026-10-07T00:00:00Z"
    lotek_observation_trace.discard_reason = "device_whitelist"
    lotek_observation_trace.save(update_fields=["discarded_at", "discard_reason"])

    api_client.force_authenticate(superuser)
    response = api_client.get(
        reverse("traces-list"), data={"object_id": str(lotek_observation_trace.object_id)}
    )
    assert response.status_code == status.HTTP_200_OK, response.content
    body = response.json()["results"][0]
    assert body["discarded_at"] is not None
    assert body["discard_reason"] == "device_whitelist"


def test_traces_can_be_filtered_by_discarded(
        api_client, superuser, lotek_observation_trace, trap_tagger_event_trace
):
    lotek_observation_trace.discarded_at = "2026-10-07T00:00:00Z"
    lotek_observation_trace.save(update_fields=["discarded_at"])

    api_client.force_authenticate(superuser)
    response = api_client.get(reverse("traces-list"), data={"discarded_at__isnull": False})
    assert response.status_code == status.HTTP_200_OK, response.content
    object_ids = {row["object_id"] for row in response.json()["results"]}
    assert str(lotek_observation_trace.object_id) in object_ids
    assert str(trap_tagger_event_trace.object_id) not in object_ids

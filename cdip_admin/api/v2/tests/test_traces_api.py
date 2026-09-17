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


# ---- Filtered drops (GUNDI-5178) ------------------------------------------


def test_trace_payload_exposes_the_filtered_fields(
        api_client, superuser, event_delivered_trace
):
    api_client.force_authenticate(superuser)
    response = api_client.get(reverse("traces-list"))

    assert response.status_code == status.HTTP_200_OK, response.content
    trace = response.json()["results"][0]
    for field in ("is_filtered", "filtered_at", "filtered_by"):
        assert field in trace


def test_a_trace_is_not_filtered_by_default(
        api_client, superuser, event_delivered_trace
):
    # Every row already in the table predates this feature, so the default has to read as
    # "not filtered" rather than as unknown.
    api_client.force_authenticate(superuser)
    response = api_client.get(reverse("traces-list"))

    trace = response.json()["results"][0]
    assert trace["is_filtered"] is False
    assert trace["filtered_at"] is None
    assert trace["filtered_by"] is None


def test_traces_can_be_filtered_by_is_filtered(
        api_client, superuser, event_delivered_trace, event_delivered_trace2
):
    event_delivered_trace2.is_filtered = True
    event_delivered_trace2.filtered_by = "device_whitelist"
    event_delivered_trace2.save()

    api_client.force_authenticate(superuser)
    response = api_client.get(reverse("traces-list"), {"is_filtered": "true"})

    assert response.status_code == status.HTTP_200_OK, response.content
    results = response.json()["results"]
    assert [t["object_id"] for t in results] == [str(event_delivered_trace2.object_id)]
    assert results[0]["filtered_by"] == "device_whitelist"


def test_a_filtered_drop_is_not_an_error(
        api_client, superuser, event_delivered_trace
):
    # has_error feeds the connection health calculation, so a working blacklist must not
    # make a healthy connection look unhealthy.
    event_delivered_trace.is_filtered = True
    event_delivered_trace.filtered_by = "device_blacklist"
    event_delivered_trace.save()

    api_client.force_authenticate(superuser)
    trace = api_client.get(reverse("traces-list")).json()["results"][0]

    assert trace["is_filtered"] is True
    assert trace["has_error"] is False

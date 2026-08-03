import pytest
from unittest.mock import ANY
from django.urls import reverse
from django.conf import settings
from gundi_core.schemas.v2 import StreamPrefixEnum
from rest_framework import status
from activity_log.models import ActivityLog
from integrations.models import Source
from .utils import _test_activity_logs_on_instance_created, _test_activity_logs_on_instance_updated

pytestmark = pytest.mark.django_db


def _test_create_observation(api_client, mock_publisher, integration, keyauth_headers, data, assert_source_created=True):
    response = api_client.post(
        reverse("observations-list"),
        data=data,
        format='json',
        **keyauth_headers
    )
    # Check the request response
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    if isinstance(response_data, dict):
        response_data = [response_data]
    for obj in response_data:
        assert "object_id" in obj
        assert "created_at" in obj
    # Check that sources are created
    if not isinstance(data, list):
        data = [data]
        for obs in data:
            source_id = obs.get("source", "default-source")
            if assert_source_created:
                source = Source.objects.get(integration=integration, external_id=source_id)
                # Check activity logs
                activity_log = ActivityLog.objects.filter(integration_id=integration.id, value="source_created").first()
                _test_activity_logs_on_instance_created(
                    activity_log=activity_log,
                    instance=source,
                    user=None  # Created through API, no user
                )
            # Check that an event was published so routing services continue processing the data
            assert mock_publisher.publish.called
            data_kwarg = mock_publisher.publish.call_args.kwargs["data"]
            assert data_kwarg.get("payload")
            extra_arg = mock_publisher.publish.call_args.kwargs["extra"]
            assert "gundi_id" in extra_arg
            assert extra_arg.get("gundi_version") == "v2"
            assert extra_arg.get("observation_type") == StreamPrefixEnum.observation.value


def test_create_single_observation(
        api_client, mocker, mock_publisher, mock_deduplication, provider_trap_tagger, keyauth_headers_trap_tagger
):
    # Mock external dependencies
    mocker.patch("api.v2.utils.publisher", mock_publisher)
    mocker.patch("api.v2.utils.is_duplicate_data", mock_deduplication)
    _test_create_observation(
        api_client=api_client,
        mock_publisher=mock_publisher,
        integration=provider_trap_tagger,
        keyauth_headers=keyauth_headers_trap_tagger,
        data={
            "source": "ABC123",
            "type": "tracking-device",
            "subject_type": "giraffe",
            "recorded_at": "2023-08-24 12:02:02-0700",
            "location": {
                "lat": -51.688650,
                "lon": -72.704435
            },
            "additional": {
                "speed_kmph": 5
            },
            "annotations": {
                "priority": "high"
            }
        }
    )


def test_create_observations_in_bulk(
        api_client, mocker, mock_publisher, mock_deduplication, provider_trap_tagger, keyauth_headers_trap_tagger
):
    # Mock external dependencies
    mocker.patch("api.v2.utils.publisher", mock_publisher)
    mocker.patch("api.v2.utils.is_duplicate_data", mock_deduplication)
    _test_create_observation(
        api_client=api_client,
        mock_publisher=mock_publisher,
        integration=provider_trap_tagger,
        keyauth_headers=keyauth_headers_trap_tagger,
        data=[
            {
                "source": "test-device-mariano",
                "type": "tracking-device",
                "subject_type": "giraffe",
                "recorded_at": "2023-08-24 13:07:00-0700",
                "location": {
                    "lat": -51.690,
                    "lon": -72.714
                },
                "additional": {
                    "speed_kmph": 5
                },
                "annotations": {
                    "in_danger": False
                }
            },
            {
                "source": "test-device-mariano-2",
                "type": "tracking-device",
                "subject_type": "giraffe",
                "recorded_at": "2023-08-24 13:08:00-0700",
                "location": {
                    "lat": -51.695,
                    "lon": -72.724
                },
                "additional": {
                    "speed_kmph": 5
                },
                "annotations": {
                    "in_danger": True
                }
            }
        ]
    )
    assert mock_publisher.publish.call_count == 2


def test_override_observation_source_name_with_new_source(
        api_client, mocker, mock_publisher, mock_deduplication, provider_trap_tagger, keyauth_headers_trap_tagger
):
    # Mock external dependencies
    mocker.patch("api.v2.utils.publisher", mock_publisher)
    mocker.patch("api.v2.utils.is_duplicate_data", mock_deduplication)
    observation_data = {
        "source": "STVIC",
        "subject_type": "truck",
        "source_name": "Buttercup32",
        "recorded_at": "2023-12-14 02:44:32Z",
        "location": {
            "lat": -51.669228,
            "lon": -72.664443
        },
        "additional": {
            "speed_kmph": 3
        }
    }
    _test_create_observation(
        api_client=api_client,
        mock_publisher=mock_publisher,
        integration=provider_trap_tagger,
        keyauth_headers=keyauth_headers_trap_tagger,
        data=observation_data
    )
    # Check that a message was published with the right data for routing services
    final_message = mock_publisher.publish.call_args.kwargs["data"].get("payload", {})
    assert final_message.get("source_name") == observation_data["source_name"]
    assert final_message.get("external_source_id") == observation_data["source"]
    assert final_message.get("subject_type") == observation_data["subject_type"]
    assert str(final_message.get("recorded_at")) == observation_data["recorded_at"].replace("Z", "+00:00")
    assert final_message.get("location", {}).get("lat") == observation_data["location"]["lat"]
    assert final_message.get("location", {}).get("lon") == observation_data["location"]["lon"]
    assert final_message.get("additional") == observation_data["additional"]


def test_override_observation_source_name_with_existent_source(
        api_client, mocker, mock_publisher, mock_deduplication,
        provider_lotek_panthera, keyauth_headers_lotek, lotek_sources
):
    # Mock external dependencies
    mocker.patch("api.v2.utils.publisher", mock_publisher)
    mocker.patch("api.v2.utils.is_duplicate_data", mock_deduplication)
    source = lotek_sources[0]
    observation_data = {
        "source": str(source.external_id),
        "subject_type": "truck",
        "source_name": "Buttercup32",
        "recorded_at": "2023-12-14 02:44:32Z",
        "location": {
            "lat": -51.669228,
            "lon": -72.664443
        },
        "additional": {
            "speed_kmph": 3
        }
    }
    _test_create_observation(
        api_client=api_client,
        mock_publisher=mock_publisher,
        integration=provider_lotek_panthera,
        keyauth_headers=keyauth_headers_lotek,
        data=observation_data,
        assert_source_created=False
    )
    # Check that a message was published with the right data for routing services
    final_message = mock_publisher.publish.call_args.kwargs["data"].get("payload", {})
    assert final_message.get("source_name") == observation_data["source_name"]
    assert final_message.get("external_source_id") == observation_data["source"]
    assert final_message.get("subject_type") == observation_data["subject_type"]
    assert str(final_message.get("recorded_at")) == observation_data["recorded_at"].replace("Z", "+00:00")
    assert final_message.get("location", {}).get("lat") == observation_data["location"]["lat"]
    assert final_message.get("location", {}).get("lon") == observation_data["location"]["lon"]
    assert final_message.get("additional") == observation_data["additional"]


def test_observation_with_invalid_lat_returns_400(
        api_client, mocker, mock_publisher, mock_deduplication,
        provider_lotek_panthera, keyauth_headers_lotek, lotek_sources
):
    # Mock external dependencies
    mocker.patch("api.v2.utils.publisher", mock_publisher)
    mocker.patch("api.v2.utils.is_duplicate_data", mock_deduplication)
    data = {
        "source": "ABC123",
        "type": "tracking-device",
        "subject_type": "giraffe",
        "recorded_at": "2023-08-24 12:02:02-0700",
        "location": {
            "lat": -91.0,  # Invalid latitude
            "lon": -72.704435
        },
        "additional": {
            "speed_kmph": 5
        },
        "annotations": {
            "priority": "high"
        }
    }
    response = api_client.post(
        reverse("observations-list"),
        data=data,
        format='json',
        **keyauth_headers_lotek
    )
    # Check the request response
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert not mock_publisher.publish.called

def test_observation_with_invalid_lon_returns_400(
        api_client, mocker, mock_publisher, mock_deduplication,
        provider_lotek_panthera, keyauth_headers_lotek, lotek_sources
):
    # Mock external dependencies
    mocker.patch("api.v2.utils.publisher", mock_publisher)
    mocker.patch("api.v2.utils.is_duplicate_data", mock_deduplication)
    data = {
        "source": "ABC123",
        "type": "tracking-device",
        "subject_type": "giraffe",
        "recorded_at": "2023-08-24 12:02:02-0700",
        "location": {
            "lat": -51.688650,
            "lon": 181.0  # Invalid longitude
        },
        "additional": {
            "speed_kmph": 5
        },
        "annotations": {
            "priority": "high"
        }
    }
    response = api_client.post(
        reverse("observations-list"),
        data=data,
        format='json',
        **keyauth_headers_lotek
    )
    # Check the request response
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert not mock_publisher.publish.called


def test_create_observations_in_bulk_above_threshold_publishes_batch_envelope(
        api_client, mocker, mock_publisher, mock_deduplication, settings,
        provider_trap_tagger, keyauth_headers_trap_tagger
):
    settings.OBSERVATIONS_BATCH_THRESHOLD = 3
    settings.OBSERVATIONS_BATCH_MAX_ITEMS = 2
    mocker.patch("api.v2.utils.publisher", mock_publisher)
    mocker.patch("api.v2.utils.is_duplicate_data", mock_deduplication)
    data = [
        {
            "source": f"batch-device-{i}",
            "type": "tracking-device",
            "recorded_at": f"2026-07-24 13:0{i}:00-0700",
            "location": {"lat": -51.690, "lon": -72.714},
        }
        for i in range(3)
    ]
    response = api_client.post(
        reverse("observations-list"), data=data, format='json', **keyauth_headers_trap_tagger
    )
    assert response.status_code == status.HTTP_200_OK
    # 3 items, max 2 per envelope -> 2 publishes (2 + 1), both batch envelopes
    assert mock_publisher.publish.call_count == 2
    first_call = mock_publisher.publish.call_args_list[0].kwargs
    assert first_call["data"]["event_type"] == "ObservationsBatchReceived"
    assert len(first_call["data"]["payload"]["observations"]) == 2
    extra = first_call["extra"]
    assert extra["batch"] == "true"
    assert extra["batch_count"] == "2"
    assert extra["gundi_version"] == "v2"
    assert extra["observation_type"] == StreamPrefixEnum.observation.value
    second_call = mock_publisher.publish.call_args_list[1].kwargs
    assert len(second_call["data"]["payload"]["observations"]) == 1


def test_create_observations_below_threshold_publishes_per_item(
        api_client, mocker, mock_publisher, mock_deduplication, settings,
        provider_trap_tagger, keyauth_headers_trap_tagger
):
    settings.OBSERVATIONS_BATCH_THRESHOLD = 10
    mocker.patch("api.v2.utils.publisher", mock_publisher)
    mocker.patch("api.v2.utils.is_duplicate_data", mock_deduplication)
    data = [
        {
            "source": f"single-device-{i}",
            "type": "tracking-device",
            "recorded_at": f"2026-07-24 13:0{i}:00-0700",
            "location": {"lat": -51.690, "lon": -72.714},
        }
        for i in range(2)
    ]
    response = api_client.post(
        reverse("observations-list"), data=data, format='json', **keyauth_headers_trap_tagger
    )
    assert response.status_code == status.HTTP_200_OK
    assert mock_publisher.publish.call_count == 2
    for call in mock_publisher.publish.call_args_list:
        assert call.kwargs["data"]["event_type"] == "ObservationReceived"
        assert "gundi_id" in call.kwargs["extra"]


def _record_span_nesting(mocker):
    # Wraps tracing.tracer.start_as_current_span to record, for every span
    # entered, which OTHER spans (by name) were already open (their
    # __enter__ ran but __exit__ hasn't yet) at that moment - i.e. its
    # ancestors. Returns the list of (span_name, ancestors_tuple) entries in
    # the order spans were entered.
    import contextlib
    from api.v2 import utils as api_utils

    real_start = api_utils.tracing.tracer.start_as_current_span
    active_stack = []
    entries = []

    @contextlib.contextmanager
    def spy(name, *args, **kwargs):
        entries.append((name, tuple(active_stack)))
        active_stack.append(name)
        try:
            with real_start(name, *args, **kwargs) as span:
                yield span
        finally:
            active_stack.pop()

    mocker.patch.object(api_utils.tracing.tracer, "start_as_current_span", side_effect=spy)
    return entries


def test_per_item_publish_span_nests_under_process_observation_span(
        api_client, mocker, mock_publisher, mock_deduplication, settings,
        provider_trap_tagger, keyauth_headers_trap_tagger
):
    # I-span regression test: for trickle traffic (below the batch
    # threshold), the publish span (gundi_api.send_observations_to_routing)
    # must stay nested under the per-item gundi_api.process_observation
    # span - exactly as before the batch refactor. Otherwise every
    # single-observation POST produces two disconnected traces and the
    # routing/dispatcher spans downstream lose the ingestion attributes
    # (gundi_id, integration_id, external_source_id) they used to hang under.
    settings.OBSERVATIONS_BATCH_THRESHOLD = 10  # well above 1 item -> per-item mode
    mocker.patch("api.v2.utils.publisher", mock_publisher)
    mocker.patch("api.v2.utils.is_duplicate_data", mock_deduplication)
    entries = _record_span_nesting(mocker)

    data = [{
        "source": "span-device-1",
        "type": "tracking-device",
        "recorded_at": "2026-07-24 13:00:00-0700",
        "location": {"lat": -51.690, "lon": -72.714},
    }]
    response = api_client.post(
        reverse("observations-list"), data=data, format='json', **keyauth_headers_trap_tagger
    )

    assert response.status_code == status.HTTP_200_OK
    publish_entries = [e for e in entries if e[0] == "gundi_api.send_observations_to_routing"]
    assert len(publish_entries) == 1
    _, ancestors = publish_entries[0]
    assert "gundi_api.process_observation" in ancestors


def test_batch_publish_span_is_not_nested_under_process_observation_span(
        api_client, mocker, mock_publisher, mock_deduplication, settings,
        provider_trap_tagger, keyauth_headers_trap_tagger
):
    # Counterpart to the test above: in batch mode the envelope is published
    # once, after the per-item loop finishes, so it must NOT be nested under
    # any single item's gundi_api.process_observation span.
    settings.OBSERVATIONS_BATCH_THRESHOLD = 1  # force batch mode for 2 items
    settings.OBSERVATIONS_BATCH_MAX_ITEMS = 10
    mocker.patch("api.v2.utils.publisher", mock_publisher)
    mocker.patch("api.v2.utils.is_duplicate_data", mock_deduplication)
    entries = _record_span_nesting(mocker)

    data = [
        {
            "source": f"batch-span-device-{i}",
            "type": "tracking-device",
            "recorded_at": f"2026-07-24 13:0{i}:00-0700",
            "location": {"lat": -51.690, "lon": -72.714},
        }
        for i in range(2)
    ]
    response = api_client.post(
        reverse("observations-list"), data=data, format='json', **keyauth_headers_trap_tagger
    )

    assert response.status_code == status.HTTP_200_OK
    batch_entries = [e for e in entries if e[0] == "gundi_api.send_observations_batch_to_routing"]
    assert len(batch_entries) == 1
    _, ancestors = batch_entries[0]
    assert "gundi_api.process_observation" not in ancestors

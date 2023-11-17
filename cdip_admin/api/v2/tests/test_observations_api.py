import pytest
from unittest.mock import ANY
from django.urls import reverse
from rest_framework import status
from cdip_connector.core.routing import TopicEnum
from activity_log.models import ActivityLog
from integrations.models import Source
from .utils import _test_activity_logs_on_instance_created, _test_activity_logs_on_instance_updated


pytestmark = pytest.mark.django_db


def _test_create_observation(api_client, integration, keyauth_headers, data):
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
            source = Source.objects.get(integration=integration, external_id=source_id)
            assert source
            # Check activity logs
            activity_log = ActivityLog.objects.filter(integration_id=integration.id, value="source_created").first()
            _test_activity_logs_on_instance_created(
                activity_log=activity_log,
                instance=source,
                user=None  # Created through API, no user
            )


def test_create_single_observation(
        api_client, mocker, mock_get_publisher, mock_deduplication, provider_trap_tagger, keyauth_headers_trap_tagger
):
    # Mock external dependencies
    mocker.patch("api.v2.utils.get_publisher", mock_get_publisher)
    mocker.patch("api.v2.utils.is_duplicate_data", mock_deduplication)
    _test_create_observation(
        api_client=api_client,
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
    # Check that a message was published in the right topic for routing
    assert mock_get_publisher.return_value.publish.called
    mock_get_publisher.return_value.publish.assert_called_with(
        topic=TopicEnum.observations_unprocessed.value,
        data=ANY,
        extra=ANY
    )


def test_create_events_in_bulk(
        api_client, mocker, mock_get_publisher, mock_deduplication, provider_trap_tagger, keyauth_headers_trap_tagger
):
    # Mock external dependencies
    mocker.patch("api.v2.utils.get_publisher", mock_get_publisher)
    mocker.patch("api.v2.utils.is_duplicate_data", mock_deduplication)
    _test_create_observation(
        api_client=api_client,
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
    # Check that a message was published in the right topic for routing
    assert mock_get_publisher.return_value.publish.called
    assert mock_get_publisher.return_value.publish.call_count == 2
    mock_get_publisher.return_value.publish.assert_called_with(
        topic=TopicEnum.observations_unprocessed.value,
        data=ANY,
        extra=ANY
    )

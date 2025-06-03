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


def _test_post_message(api_client, mock_publisher, integration, data, headers=None, assert_source_created=True):
    headers = headers or {}
    response = api_client.post(
        reverse("messages-list"),
        data=data,
        format='json',
        **headers
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
            assert extra_arg.get("observation_type") == StreamPrefixEnum.text_message.value


def test_send_single_message_from_inreach_to_er(
        api_client, mocker, mock_publisher, mock_deduplication, inreach_connection
):
    # Mock external dependencies
    mocker.patch("api.v2.utils.publisher", mock_publisher)
    mocker.patch("api.v2.utils.is_duplicate_data", mock_deduplication)
    _test_post_message(
        api_client=api_client,
        mock_publisher=mock_publisher,
        integration=inreach_connection,
        headers={"HTTP_X_CONSUMER_USERNAME": f"integration:{inreach_connection.id}"},
        data={
            "sender": "2075752244",
            "recipients": ["admin@sitex.pamdas.org"],
            "text": "Help! I need assistance.",
            "recorded_at": "2025-06-03 09:54:10-0300",
            "location": {
                "latitude": -51.689,
                "longitude": -72.705
            },
            "additional": {
                "speed_kmph": 30
            }
        }
    )


def test_send_multiple_messages_from_inreach_to_er(
        api_client, mocker, mock_publisher, mock_deduplication, inreach_connection
):
    # Mock external dependencies
    mocker.patch("api.v2.utils.publisher", mock_publisher)
    mocker.patch("api.v2.utils.is_duplicate_data", mock_deduplication)
    _test_post_message(
        api_client=api_client,
        mock_publisher=mock_publisher,
        integration=inreach_connection,
        headers={"HTTP_X_CONSUMER_USERNAME": f"integration:{inreach_connection.id}"},
        data=[
            {
                "sender": "2075752244",
                "recipients": ["admin@sitex.pamdas.org"],
                "text": "Help! I need assistance.",
                "recorded_at": "2025-06-03 09:54:10-0300",
                "location": {
                    "latitude": -51.689,
                    "longitude": -72.705
                },
                "additional": {
                    "status": {
                        "autonomous": 0,
                        "lowBattery": 0,
                        "intervalChange": 1,
                        "resetDetected": 0
                    }
                }
            },
            {
                "sender": "2075752244",
                "recipients": ["user@sitex.pamdas.org"],
                "text": "FYI my battery is low.",
                "recorded_at": "2025-06-03 10:00:00-0300",
                "location": {
                    "latitude": -51.690,
                    "longitude": -72.706
                },
                "additional": {
                    "status": {
                        "autonomous": 0,
                        "lowBattery": 1,
                        "intervalChange": 0,
                        "resetDetected": 0
                    }
                }
            }
        ]
    )


def test_send_single_message_from_er_to_inreach(
        api_client, mocker, mock_publisher, mock_deduplication, earthranger_conection, inreach_connection
):
    # Mock external dependencies
    mocker.patch("api.v2.utils.publisher", mock_publisher)
    mocker.patch("api.v2.utils.is_duplicate_data", mock_deduplication)
    _test_post_message(
        api_client=api_client,
        mock_publisher=mock_publisher,
        integration=earthranger_conection,
        headers={"HTTP_X_CONSUMER_USERNAME": f"integration:{earthranger_conection.id}"},
        data={
            "sender": "admin@sitex.pamdas.org",
            "device_ids": ["2075752244"],  # test recipients alias
            "text": "Help is on the way!",
            "created_at": "2025-06-03 11:54:10-0300"
        }
    )


def test_send_multiple_messages_from_er_to_inreach(
        api_client, mocker, mock_publisher, mock_deduplication, earthranger_conection, inreach_connection
):
    # Mock external dependencies
    mocker.patch("api.v2.utils.publisher", mock_publisher)
    mocker.patch("api.v2.utils.is_duplicate_data", mock_deduplication)
    _test_post_message(
        api_client=api_client,
        mock_publisher=mock_publisher,
        integration=earthranger_conection,
        headers={"HTTP_X_CONSUMER_USERNAME": f"integration:{earthranger_conection.id}"},
        data=[
            {
                "sender": "admin@sitex.pamdas.org",
                "device_ids": ["2075752244", "1275752245"],
                "text": "Help is on the way!",
                "recorded_at": "2025-06-03 12:54:10-0300"
            },
            {
                "sender": "admin@sitex.pamdas.org",
                "recipients": ["2075752244"],
                "text": "We are close to your location.",
                "location": {
                    "latitude": -51.675,
                    "longitude": -72.701
                },
                "created_at": "2025-06-03 12:25:10-0300"  # test recorded_at alias
            }
        ]
    )

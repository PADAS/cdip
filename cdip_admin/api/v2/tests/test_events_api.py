import pytest
from unittest.mock import ANY
from django.urls import reverse
from rest_framework import status
from cdip_connector.core.routing import TopicEnum


pytestmark = pytest.mark.django_db


def _test_create_event(api_client, keyauth_headers, data):
    response = api_client.post(
        reverse("events-list"),
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


def test_create_single_event(api_client, mocker, mock_get_publisher, mock_deduplication, keyauth_headers_trap_tagger):
    # Mock external dependencies
    mocker.patch("api.v2.utils.get_publisher", mock_get_publisher)
    mocker.patch("api.v2.utils.is_duplicate_data", mock_deduplication)
    _test_create_event(
        api_client=api_client,
        keyauth_headers=keyauth_headers_trap_tagger,
        data={
            "source": "Xyz123",
            "title": "Leopard Detected",
            "recorded_at": "2023-07-05T11:52-08:00",
            "location": {
              "lat": -51.667875,
              "lon": -72.711950,
              "alt": 1800
            },
            "event_details": {
              "site_name": "Camera2G",
              "species": "Leopard",
              "tags": [
                "female adult",
                "male child"
              ],
              "animal_count": 2
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


def test_create_events_in_bulk(api_client, mocker, mock_get_publisher, mock_deduplication, keyauth_headers_trap_tagger):
    # Mock external dependencies
    mocker.patch("api.v2.utils.get_publisher", mock_get_publisher)
    mocker.patch("api.v2.utils.is_duplicate_data", mock_deduplication)
    _test_create_event(
        api_client=api_client,
        keyauth_headers=keyauth_headers_trap_tagger,
        data=[
            {
                "source": "Xyz123",
                "title": "Leopard Detected",
                "recorded_at": "2023-07-05T11:52-08:00",
                "location": {
                  "lat": -51.667875,
                  "lon": -72.711950,
                  "alt": 1800
                },
                "event_details": {
                  "site_name": "Camera2G",
                  "species": "Leopard",
                  "tags": [
                    "female adult",
                    "male child"
                  ],
                  "animal_count": 2
                }
            },
            {
                "source": "Xyz123",
                "title": "Wilddog Detected",
                "recorded_at": "2023-07-05T11:52-08:00",
                "location": {
                    "lat": -51.688648,
                    "lon": -72.704423,
                    "alt": 1800
                },
                "event_details": {
                    "site_name": "Camera2B",
                    "species": "Wilddog",
                    "tags": [
                        "adult",
                        "male"
                    ],
                    "animal_count": 1
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


def test_create_single_event_without_source(
        api_client, mocker, mock_get_publisher, mock_deduplication, keyauth_headers_trap_tagger
):
    # Mock external dependencies
    mocker.patch("api.v2.utils.get_publisher", mock_get_publisher)
    mocker.patch("api.v2.utils.is_duplicate_data", mock_deduplication)
    _test_create_event(
        api_client=api_client,
        keyauth_headers=keyauth_headers_trap_tagger,
        data={
            #"source": "Xyz123",  # Source is optional
            "title": "Leopard Detected",
            "recorded_at": "2023-07-05T11:52-08:00",
            "location": {
              "lat": -51.667875,
              "lon": -72.711950,
              "alt": 1800
            },
            "event_details": {
              "site_name": "Camera2G",
              "species": "Leopard",
              "tags": [
                "female adult",
                "male child"
              ],
              "animal_count": 2
            }
        }
    )
    # Check that a message was published in the right topic for routing
    publish_mock = mock_get_publisher.return_value.publish
    assert publish_mock.called
    mock_get_publisher.return_value.publish.assert_called_with(
        topic=TopicEnum.observations_unprocessed.value,
        data=ANY,
        extra=ANY
    )
    # Check that the source is set with a default value
    assert publish_mock.call_args.kwargs["data"].get("external_source_id") == "default-source"


def test_create_events_in_bulk_without_source(api_client, mocker, mock_get_publisher, mock_deduplication, keyauth_headers_trap_tagger):
    # Mock external dependencies
    mocker.patch("api.v2.utils.get_publisher", mock_get_publisher)
    mocker.patch("api.v2.utils.is_duplicate_data", mock_deduplication)
    _test_create_event(
        api_client=api_client,
        keyauth_headers=keyauth_headers_trap_tagger,
        data=[
            {
                #"source": "Xyz123",  # Source is optional
                "title": "Leopard Detected",
                "recorded_at": "2023-07-05T11:52-08:00",
                "location": {
                  "lat": -51.667875,
                  "lon": -72.711950,
                  "alt": 1800
                },
                "event_details": {
                  "site_name": "Camera2G",
                  "species": "Leopard",
                  "tags": [
                    "female adult",
                    "male child"
                  ],
                  "animal_count": 2
                }
            },
            {
                #"source": "Xyz456",  # Source is optional
                "title": "Wilddog Detected",
                "recorded_at": "2023-07-05T11:52-08:00",
                "location": {
                    "lat": -51.688648,
                    "lon": -72.704423,
                    "alt": 1800
                },
                "event_details": {
                    "site_name": "Camera2B",
                    "species": "Wilddog",
                    "tags": [
                        "adult",
                        "male"
                    ],
                    "animal_count": 1
                }
            }
        ]
    )
    # Check that a message was published in the right topic for routing
    publish_mock = mock_get_publisher.return_value.publish
    assert publish_mock.called
    assert publish_mock.call_count == 2
    mock_get_publisher.return_value.publish.assert_called_with(
        topic=TopicEnum.observations_unprocessed.value,
        data=ANY,
        extra=ANY
    )
    # Check that the source is set with a default value
    for call in publish_mock.call_args_list:
        assert call.kwargs["data"].get("external_source_id") == "default-source"

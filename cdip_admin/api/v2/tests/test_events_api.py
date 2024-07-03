import pytest
from unittest.mock import ANY
from django.urls import reverse
from django.conf import settings
from rest_framework import status


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


def test_create_single_event(api_client, mocker, mock_publisher, mock_deduplication, keyauth_headers_trap_tagger):
    # Mock external dependencies
    mocker.patch("api.v2.utils.publisher", mock_publisher)
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
    assert mock_publisher.publish.called
    mock_publisher.publish.assert_called_with(
        topic=settings.RAW_OBSERVATIONS_TOPIC,
        data=ANY,
        extra=ANY
    )


def test_create_events_in_bulk(api_client, mocker, mock_publisher, mock_deduplication, keyauth_headers_trap_tagger):
    # Mock external dependencies
    mocker.patch("api.v2.utils.publisher", mock_publisher)
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
    assert mock_publisher.publish.called
    assert mock_publisher.publish.call_count == 2
    mock_publisher.publish.assert_called_with(
        topic=settings.RAW_OBSERVATIONS_TOPIC,
        data=ANY,
        extra=ANY
    )


def test_create_single_event_without_source(
        api_client, mocker, mock_publisher, mock_deduplication, keyauth_headers_trap_tagger
):
    # Mock external dependencies
    mocker.patch("api.v2.utils.publisher", mock_publisher)
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
    publish_mock = mock_publisher.publish
    assert publish_mock.called
    mock_publisher.publish.assert_called_with(
        topic=settings.RAW_OBSERVATIONS_TOPIC,
        data=ANY,
        extra=ANY
    )
    # Check that the source is set with a default value
    assert publish_mock.call_args.kwargs["data"].get("payload", {}).get("external_source_id") == "default-source"


def test_create_events_in_bulk_without_source(api_client, mocker, mock_publisher, mock_deduplication, keyauth_headers_trap_tagger):
    # Mock external dependencies
    mocker.patch("api.v2.utils.publisher", mock_publisher)
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
    publish_mock = mock_publisher.publish
    assert publish_mock.called
    assert publish_mock.call_count == 2
    mock_publisher.publish.assert_called_with(
        topic=settings.RAW_OBSERVATIONS_TOPIC,
        data=ANY,
        extra=ANY
    )
    # Check that the source is set with a default value
    for call in publish_mock.call_args_list:
        assert call.kwargs["data"].get("payload", {}).get("external_source_id") == "default-source"


def test_create_single_event_without_location(api_client, mocker, mock_publisher, mock_deduplication, keyauth_headers_trap_tagger):
    # Mock external dependencies
    mocker.patch("api.v2.utils.publisher", mock_publisher)
    mocker.patch("api.v2.utils.is_duplicate_data", mock_deduplication)
    _test_create_event(
        api_client=api_client,
        keyauth_headers=keyauth_headers_trap_tagger,
        data={  # Analizer events do not require location
            'event_type': 'silence_source_provider_rep',
            'title': '265de4c0-07b8-4e30-b136-5d5a75ff5912 integration disrupted',
            'recorded_at': '2023-11-16T12:14:35.215393-06:00',
            'event_details': {'report_time': '2023-11-16 18:14:34', 'silence_threshold': '00:00',
                              'last_device_reported_at': '2023-10-26 21:24:02', 'updates': []},
            'additional': {'id': '968f6307-3ff6-4810-aca5-bf4669d6ddd6', 'location': None,
                           'time': '2023-11-16T12:14:35.213057-06:00', 'end_time': None, 'serial_number': 371,
                           'message': '', 'provenance': '', 'priority': 0, 'priority_label': 'Gray', 'attributes': {},
                           'comment': None, 'reported_by': None, 'state': 'new', 'is_contained_in': [],
                           'sort_at': '2023-11-16T12:14:35.215163-06:00', 'patrol_segments': [], 'geometry': None,
                           'updated_at': '2023-11-16T12:14:35.215163-06:00',
                           'created_at': '2023-11-16T12:14:35.215393-06:00', 'icon_id': 'silence_source_provider_rep',
                           'files': [], 'related_subjects': [], 'event_category': 'analyzer_event',
                           'url': 'https://gundi-er.pamdas.org/api/v1.0/activity/event/968f6307-3ff6-4810-aca5-bf4669d6ddd6',
                           'image_url': 'https://gundi-er.pamdas.org/static/generic-gray.svg', 'geojson': None,
                           'is_collection': False, 'updates': [
                    {'message': 'Created', 'time': '2023-11-16T18:14:35.220923+00:00',
                     'user': {'first_name': '', 'last_name': '', 'username': ''}, 'type': 'add_event'}],
                           'patrols': []}
        }
    )
    # Check that a message was published in the right topic for routing
    assert mock_publisher.publish.called
    mock_publisher.publish.assert_called_with(
        topic=settings.RAW_OBSERVATIONS_TOPIC,
        data=ANY,
        extra=ANY
    )

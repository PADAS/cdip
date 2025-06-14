import pytest
from unittest.mock import ANY
from django.urls import reverse
from django.conf import settings
from gundi_core.schemas.v2 import StreamPrefixEnum
from rest_framework import status


pytestmark = pytest.mark.django_db


def _test_create_event(api_client, mock_publisher, keyauth_headers, data):
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
    # Check that a message was published in the right topic for routing
    assert mock_publisher.publish.called
    topic_kwarg = mock_publisher.publish.call_args.kwargs["topic"]
    assert topic_kwarg == settings.RAW_OBSERVATIONS_TOPIC
    data_kwarg = mock_publisher.publish.call_args.kwargs["data"]
    assert data_kwarg.get("payload")
    extra_arg = mock_publisher.publish.call_args.kwargs["extra"]
    assert "gundi_id" in extra_arg
    assert extra_arg.get("gundi_version") == "v2"
    assert extra_arg.get("observation_type") == StreamPrefixEnum.event.value


def test_create_single_event(api_client, mocker, mock_publisher, mock_deduplication, keyauth_headers_trap_tagger):
    # Mock external dependencies
    mocker.patch("api.v2.utils.publisher", mock_publisher)
    mocker.patch("api.v2.utils.is_duplicate_data", mock_deduplication)
    _test_create_event(
        api_client=api_client,
        mock_publisher=mock_publisher,
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


def test_create_events_in_bulk(api_client, mocker, mock_publisher, mock_deduplication, keyauth_headers_trap_tagger):
    # Mock external dependencies
    mocker.patch("api.v2.utils.publisher", mock_publisher)
    mocker.patch("api.v2.utils.is_duplicate_data", mock_deduplication)
    _test_create_event(
        api_client=api_client,
        mock_publisher=mock_publisher,
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
    assert mock_publisher.publish.call_count == 2



def test_create_single_event_without_source(
        api_client, mocker, mock_publisher, mock_deduplication, keyauth_headers_trap_tagger
):
    # Mock external dependencies
    mocker.patch("api.v2.utils.publisher", mock_publisher)
    mocker.patch("api.v2.utils.is_duplicate_data", mock_deduplication)
    _test_create_event(
        api_client=api_client,
        mock_publisher=mock_publisher,
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
    publish_mock = mock_publisher.publish
    # Check that the source is set with a default value
    assert publish_mock.call_args.kwargs["data"].get("payload", {}).get("external_source_id") == "default-source"


def test_create_events_in_bulk_without_source(api_client, mocker, mock_publisher, mock_deduplication, keyauth_headers_trap_tagger):
    # Mock external dependencies
    mocker.patch("api.v2.utils.publisher", mock_publisher)
    mocker.patch("api.v2.utils.is_duplicate_data", mock_deduplication)
    _test_create_event(
        api_client=api_client,
        mock_publisher=mock_publisher,
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
    assert publish_mock.call_count == 2
    # Check that the source is set with a default value
    for call in publish_mock.call_args_list:
        assert call.kwargs["data"].get("payload", {}).get("external_source_id") == "default-source"


def test_create_single_event_without_location(api_client, mocker, mock_publisher, mock_deduplication, keyauth_headers_trap_tagger):
    # Mock external dependencies
    mocker.patch("api.v2.utils.publisher", mock_publisher)
    mocker.patch("api.v2.utils.is_duplicate_data", mock_deduplication)
    _test_create_event(
        api_client=api_client,
        mock_publisher=mock_publisher,
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


def test_create_single_event_with_status(api_client, mocker, mock_publisher, mock_deduplication, keyauth_headers_trap_tagger):
    # Mock external dependencies
    mocker.patch("api.v2.utils.publisher", mock_publisher)
    mocker.patch("api.v2.utils.is_duplicate_data", mock_deduplication)
    _test_create_event(
        api_client=api_client,
        mock_publisher=mock_publisher,
        keyauth_headers=keyauth_headers_trap_tagger,
        data={
            "source": "camera123",
            "title": "Animal Detected",
            "event_type": "animals",
            "recorded_at": "2024-08-22 13:01:26-0300",
            "location": {
                "lon": -109.239682,
                "lat": -27.104423
            },
            "event_details": {
                "species": "lion"
            },
            "status": "active"
        }
    )
    data_kwarg = mock_publisher.publish.call_args.kwargs["data"]
    assert data_kwarg.get("payload")
    assert data_kwarg.get("payload", {}).get("status") == "active"


@pytest.mark.parametrize("request_data", [
    ("species_update_request_data"),
    ("status_update_request_data"),
])
def test_update_event(api_client, mocker, request, request_data, trap_tagger_event_trace, mock_publisher, mock_deduplication, keyauth_headers_trap_tagger):
    # Mock external dependencies
    mocker.patch("api.v2.utils.publisher", mock_publisher)
    mocker.patch("api.v2.utils.is_duplicate_data", mock_deduplication)
    data = request.getfixturevalue(request_data)
    response = api_client.patch(
        reverse("events-detail", kwargs={"pk": trap_tagger_event_trace.object_id}),
        data=data,
        format='json',
        **keyauth_headers_trap_tagger
    )
    assert response.status_code == status.HTTP_200_OK
    # Check that a message was published in the right topic for routing
    assert mock_publisher.publish.called
    topic_kwarg = mock_publisher.publish.call_args.kwargs["topic"]
    assert topic_kwarg == settings.RAW_OBSERVATIONS_TOPIC
    data_kwarg = mock_publisher.publish.call_args.kwargs["data"]
    payload = data_kwarg.get("payload", {})
    assert payload.get("changes") == data
    extra_arg = mock_publisher.publish.call_args.kwargs["extra"]
    gundi_id = str(trap_tagger_event_trace.object_id)
    assert extra_arg.get("gundi_id") == gundi_id
    assert mock_publisher.publish.call_args.kwargs["ordering_key"] == gundi_id
    assert extra_arg.get("gundi_version") == "v2"
    assert extra_arg.get("observation_type") == StreamPrefixEnum.event_update.value


def test_event_with_invalid_lat_returns_400(api_client, mocker, mock_publisher, mock_deduplication, keyauth_headers_trap_tagger):
    # Mock external dependencies
    mocker.patch("api.v2.utils.publisher", mock_publisher)
    mocker.patch("api.v2.utils.is_duplicate_data", mock_deduplication)
    data = {
        "source": "camera123",
        "title": "Animal Detected",
        "event_type": "animals",
        "recorded_at": "2024-08-22 13:01:26-0300",
        "location": {
            "lat": -91.104423,  # Invalid latitude
            "lon": -109.239682,
        },
        "event_details": {
            "species": "lion"
        }
    }
    response = api_client.post(
        reverse("events-list"),
        data=data,
        format='json',
        **keyauth_headers_trap_tagger
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert not mock_publisher.called


def test_event_with_invalid_lon_returns_400(api_client, mocker, mock_publisher, mock_deduplication, keyauth_headers_trap_tagger):
    # Mock external dependencies
    mocker.patch("api.v2.utils.publisher", mock_publisher)
    mocker.patch("api.v2.utils.is_duplicate_data", mock_deduplication)
    data = {
        "source": "camera123",
        "title": "Animal Detected",
        "event_type": "animals",
        "recorded_at": "2024-08-22 13:01:26-0300",
        "location": {
            "lat": -27.104423,
            "lon": 181.239682,  # Invalid longitude
        },
        "event_details": {
            "species": "lion"
        }
    }
    response = api_client.post(
        reverse("events-list"),
        data=data,
        format='json',
        **keyauth_headers_trap_tagger
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert not mock_publisher.called

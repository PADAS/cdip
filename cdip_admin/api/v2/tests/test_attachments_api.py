import pytest
from unittest.mock import ANY
from django.urls import reverse
from django.conf import settings
from rest_framework import status


pytestmark = pytest.mark.django_db


def _test_create_attachment(api_client, keyauth_headers, event_id, files):
    response = api_client.post(
        reverse("attachments-list", kwargs={"event_pk": event_id}),
        data=files,
        format='multipart',
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


def test_create_single_attachment(
        api_client, mocker, mock_publisher, mock_deduplication, keyauth_headers_trap_tagger,
        trap_tagger_event_trace, leopard_image_file, mock_cloud_storage
):
    # Mock external dependencies
    mocker.patch("api.v2.utils.default_storage", mock_cloud_storage)
    mocker.patch("api.v2.utils.publisher", mock_publisher)
    mocker.patch("api.v2.utils.is_duplicate_attachment", mock_deduplication)
    _test_create_attachment(
        api_client=api_client,
        keyauth_headers=keyauth_headers_trap_tagger,
        event_id=str(trap_tagger_event_trace.object_id),
        files={
            "file1": leopard_image_file
        }
    )
    # Check that the file was saved
    assert mock_cloud_storage.save.called
    # Check that a message was published in the right topic for routing
    assert mock_publisher.publish.called
    mock_publisher.publish.assert_called_with(
        topic=settings.RAW_OBSERVATIONS_TOPIC,
        data=ANY,
        extra=ANY
    )


def test_create_single_attachment_for_multiple_destinations(
        api_client, mocker, mock_publisher, mock_deduplication, keyauth_headers_trap_tagger,
        event_delivered_trace, event_delivered_trace2, leopard_image_file, mock_cloud_storage
):
    # Mock external dependencies
    mocker.patch("api.v2.utils.default_storage", mock_cloud_storage)
    mocker.patch("api.v2.utils.publisher", mock_publisher)
    mocker.patch("api.v2.utils.is_duplicate_attachment", mock_deduplication)
    _test_create_attachment(
        api_client=api_client,
        keyauth_headers=keyauth_headers_trap_tagger,
        event_id=str(event_delivered_trace.object_id),
        files={
            "file1": leopard_image_file
        }
    )
    # Check that the file was saved
    assert mock_cloud_storage.save.called
    # Check that a message was published in the right topic for routing
    assert mock_publisher.publish.called
    mock_publisher.publish.assert_called_with(
        topic=settings.RAW_OBSERVATIONS_TOPIC,
        data=ANY,
        extra=ANY
    )


def test_create_attachments_multiple_files(
        api_client, mocker, mock_publisher, mock_deduplication, keyauth_headers_trap_tagger,
        trap_tagger_event_trace, leopard_image_file, wilddog_image_file, mock_cloud_storage
):
    # Mock external dependencies
    mocker.patch("api.v2.utils.default_storage", mock_cloud_storage)
    mocker.patch("api.v2.utils.publisher", mock_publisher)
    mocker.patch("api.v2.utils.is_duplicate_attachment", mock_deduplication)
    _test_create_attachment(
        api_client=api_client,
        keyauth_headers=keyauth_headers_trap_tagger,
        event_id=str(trap_tagger_event_trace.object_id),
        files={
            "file1": leopard_image_file,
            "file2": wilddog_image_file
        }
    )
    # Check that the file was saved
    assert mock_cloud_storage.save.called
    assert mock_cloud_storage.save.call_count == 2
    # Check that a message was published in the right topic for routing
    assert mock_publisher.publish.called
    assert mock_publisher.publish.call_count == 2
    mock_publisher.publish.assert_called_with(
        topic=settings.RAW_OBSERVATIONS_TOPIC,
        data=ANY,
        extra=ANY
    )


def test_create_attachments_no_files(
        api_client, mocker, mock_publisher, mock_deduplication, keyauth_headers_trap_tagger,
        trap_tagger_event_trace
):
    # Try sending no files
    response = api_client.post(
        reverse("attachments-list", kwargs={"event_pk": trap_tagger_event_trace.object_id}),
        format='multipart',
        **keyauth_headers_trap_tagger
    )
    # Expect a 400 response
    assert response.status_code == status.HTTP_400_BAD_REQUEST

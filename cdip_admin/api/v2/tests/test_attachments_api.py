import pytest
from unittest.mock import ANY
from django.urls import reverse
from rest_framework import status
from cdip_connector.core.routing import TopicEnum


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
        api_client, mocker, mock_get_publisher, mock_deduplication, keyauth_headers_trap_tagger,
        trap_tagger_event_trace, leopard_image_file, mock_cloud_storage
):
    # Mock external dependencies
    mocker.patch("api.v2.utils.default_storage", mock_cloud_storage)
    mocker.patch("api.v2.utils.get_publisher", mock_get_publisher)
    mocker.patch("api.v2.utils.is_duplicate_attachment", mock_deduplication)
    _test_create_attachment(
        api_client=api_client,
        keyauth_headers=keyauth_headers_trap_tagger,
        event_id=str(trap_tagger_event_trace.id),
        files={
            "file1": leopard_image_file
        }
    )
    # Check that the file was saved
    assert mock_cloud_storage.save.called
    # Check that a message was published in the right topic for routing
    assert mock_get_publisher.return_value.publish.called
    mock_get_publisher.return_value.publish.assert_called_with(
        topic=TopicEnum.observations_unprocessed.value,
        data=ANY,
        extra=ANY
    )


def test_create_attachments_multiple_files(
        api_client, mocker, mock_get_publisher, mock_deduplication, keyauth_headers_trap_tagger,
        trap_tagger_event_trace, leopard_image_file, wilddog_image_file, mock_cloud_storage
):
    # Mock external dependencies
    mocker.patch("api.v2.utils.default_storage", mock_cloud_storage)
    mocker.patch("api.v2.utils.get_publisher", mock_get_publisher)
    mocker.patch("api.v2.utils.is_duplicate_attachment", mock_deduplication)
    _test_create_attachment(
        api_client=api_client,
        keyauth_headers=keyauth_headers_trap_tagger,
        event_id=str(trap_tagger_event_trace.id),
        files={
            "file1": leopard_image_file,
            "file2": wilddog_image_file
        }
    )
    # Check that the file was saved
    assert mock_cloud_storage.save.called
    assert mock_cloud_storage.save.call_count == 2
    # Check that a message was published in the right topic for routing
    assert mock_get_publisher.return_value.publish.called
    assert mock_get_publisher.return_value.publish.call_count == 2
    mock_get_publisher.return_value.publish.assert_called_with(
        topic=TopicEnum.observations_unprocessed.value,
        data=ANY,
        extra=ANY
    )

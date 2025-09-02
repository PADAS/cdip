import base64
import json

import pytest

from ..utils import create_api_consumer, KONG_PROXY_URL, CONSUMERS_PATH, get_api_consumer_info, patch_api_consumer_info, \
    get_prefix_from_integration_type, convert_legacy_topic_name

pytestmark = pytest.mark.django_db


def test_create_api_consumer_for_v1_integration(mocker, inbound_integration_awt, mock_kong_consumers_api_requests):

    mocker.patch("integrations.utils.requests", mock_kong_consumers_api_requests)

    result = create_api_consumer(inbound_integration_awt)

    assert result is True
    expected_url = f"{KONG_PROXY_URL}{CONSUMERS_PATH}"
    expected_json_blob = json.dumps({
        "integration_ids": [str(inbound_integration_awt.id)],
        "integration_type": inbound_integration_awt.type.slug,
    }).encode("utf-8")
    expected_custom_id = base64.b64encode(expected_json_blob)
    expected_data = {
        "username": f"integration:{inbound_integration_awt.id}",
        "custom_id": expected_custom_id,
    }
    mock_kong_consumers_api_requests.post.assert_called_once_with(expected_url, data=expected_data)


def test_create_api_consumer_for_v2_integration(mocker, provider_ats, mock_kong_consumers_api_requests):

    mocker.patch("integrations.utils.requests", mock_kong_consumers_api_requests)

    result = create_api_consumer(provider_ats)

    assert result is True
    expected_url = f"{KONG_PROXY_URL}{CONSUMERS_PATH}"
    expected_json_blob = json.dumps({
        "integration_ids": [str(provider_ats.id)],
        "integration_type": provider_ats.type.value,
    }).encode("utf-8")
    expected_custom_id = base64.b64encode(expected_json_blob)
    expected_data = {
        "username": f"integration:{provider_ats.id}",
        "custom_id": expected_custom_id,
    }
    mock_kong_consumers_api_requests.post.assert_called_once_with(expected_url, data=expected_data)


def test_get_api_consumer_info(mocker, provider_ats, mock_kong_consumers_api_requests, mock_api_consumer_info):
    mocker.patch("integrations.utils.requests", mock_kong_consumers_api_requests)

    result = get_api_consumer_info(provider_ats)

    assert result == mock_api_consumer_info
    expected_url = f"{KONG_PROXY_URL}{CONSUMERS_PATH}/integration:{str(provider_ats.id)}"
    mock_kong_consumers_api_requests.get.assert_called_once_with(expected_url)


def test_patch_api_consumer_info(mocker, provider_ats, mock_kong_consumers_api_requests):
    mocker.patch("integrations.utils.requests", mock_kong_consumers_api_requests)
    data = {"custom_id": "new_custom_id"}

    result = patch_api_consumer_info(provider_ats, data)

    assert result == mock_kong_consumers_api_requests.patch.return_value
    expected_url = f"{KONG_PROXY_URL}{CONSUMERS_PATH}/integration:{str(provider_ats.id)}"
    mock_kong_consumers_api_requests.patch.assert_called_once_with(expected_url, data=data)


@pytest.mark.parametrize("integration_type, expected_prefix", [
    ("earth_ranger", "earthranger"),
    ("MoveBank", "movebank"),
    ("mella-tracking", "mellatracking"),
    ("ats ", "ats"),
    ("un_conventional-VAlue ", "unconventionalvalue"),
])
def test_get_topic_prefix_from_integration_type(integration_type, expected_prefix):
    assert get_prefix_from_integration_type(integration_type) == expected_prefix


@pytest.mark.parametrize("legacy_name, expected_cleaned_name", [
    ("earth_ranger-actions-topic", "earthranger-actions-topic"),
    ("stevens-connect-actions-topic", "stevensconnect-actions-topic"),
    ("some-tech_name-actions-topic", "sometechname-actions-topic"),
    ("ats-actions-topic", "ats-actions-topic")
])
def test_clean_legacy_topic_names(legacy_name, expected_cleaned_name):
    assert convert_legacy_topic_name(legacy_name) == expected_cleaned_name

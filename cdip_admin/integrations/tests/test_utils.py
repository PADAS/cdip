import base64
import json

import pytest

from ..utils import create_api_consumer, KONG_PROXY_URL, CONSUMERS_PATH, get_api_consumer_info, patch_api_consumer_info, \
    get_prefix_from_integration_type, convert_legacy_topic_name, KONG_REQUEST_TIMEOUT, KEYS_PATH, get_api_key

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
    mock_kong_consumers_api_requests.post.assert_called_once_with(
        expected_url, data=expected_data, timeout=KONG_REQUEST_TIMEOUT
    )


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
    mock_kong_consumers_api_requests.post.assert_called_once_with(
        expected_url, data=expected_data, timeout=KONG_REQUEST_TIMEOUT
    )


def test_get_api_consumer_info(mocker, provider_ats, mock_kong_consumers_api_requests, mock_api_consumer_info):
    mocker.patch("integrations.utils.requests", mock_kong_consumers_api_requests)

    result = get_api_consumer_info(provider_ats)

    assert result == mock_api_consumer_info
    expected_url = f"{KONG_PROXY_URL}{CONSUMERS_PATH}/integration:{str(provider_ats.id)}"
    mock_kong_consumers_api_requests.get.assert_called_once_with(
        expected_url, timeout=KONG_REQUEST_TIMEOUT
    )


def _mock_kong_get(mocker, status_code, json_data=None):
    response = mocker.MagicMock()
    response.status_code = status_code
    response.ok = 200 <= status_code < 300
    response.json.return_value = json_data
    return response


def test_get_api_key_returns_existing_key_without_posting(mocker, provider_ats, mock_kong_consumers_api_requests):
    mock_kong_consumers_api_requests.get.return_value = _mock_kong_get(
        mocker, 200, {"data": [{"key": "existing-key"}]}
    )
    mocker.patch("integrations.utils.requests", mock_kong_consumers_api_requests)

    key = get_api_key(provider_ats)

    assert key == "existing-key"
    mock_kong_consumers_api_requests.get.assert_called_once_with(
        f"{KONG_PROXY_URL}{CONSUMERS_PATH}/integration:{provider_ats.id}{KEYS_PATH}",
        timeout=KONG_REQUEST_TIMEOUT,
    )
    mock_kong_consumers_api_requests.post.assert_not_called()


def test_get_api_key_creates_key_when_consumer_has_none(mocker, provider_ats, mock_kong_consumers_api_requests):
    mock_kong_consumers_api_requests.get.return_value = _mock_kong_get(mocker, 200, {"data": []})
    mock_kong_consumers_api_requests.post.return_value.content = json.dumps({"key": "new-key"})
    mocker.patch("integrations.utils.requests", mock_kong_consumers_api_requests)

    key = get_api_key(provider_ats)

    assert key == "new-key"
    mock_kong_consumers_api_requests.post.assert_called_once_with(
        f"{KONG_PROXY_URL}{CONSUMERS_PATH}/integration:{provider_ats.id}{KEYS_PATH}",
        timeout=KONG_REQUEST_TIMEOUT,
    )


def test_get_api_key_creates_consumer_and_key_when_consumer_missing(
    mocker, provider_ats, mock_kong_consumers_api_requests
):
    mock_kong_consumers_api_requests.get.return_value = _mock_kong_get(mocker, 404, {"message": "Not found"})
    mock_kong_consumers_api_requests.post.return_value.content = json.dumps({"key": "new-key"})
    mocker.patch("integrations.utils.requests", mock_kong_consumers_api_requests)

    key = get_api_key(provider_ats)

    assert key == "new-key"
    post_urls = [c.args[0] for c in mock_kong_consumers_api_requests.post.call_args_list]
    assert post_urls == [
        f"{KONG_PROXY_URL}{CONSUMERS_PATH}",
        f"{KONG_PROXY_URL}{CONSUMERS_PATH}/integration:{provider_ats.id}{KEYS_PATH}",
    ]


def test_patch_api_consumer_info(mocker, provider_ats, mock_kong_consumers_api_requests):
    mocker.patch("integrations.utils.requests", mock_kong_consumers_api_requests)
    data = {"custom_id": "new_custom_id"}

    result = patch_api_consumer_info(provider_ats, data)

    assert result == mock_kong_consumers_api_requests.patch.return_value
    expected_url = f"{KONG_PROXY_URL}{CONSUMERS_PATH}/integration:{str(provider_ats.id)}"
    mock_kong_consumers_api_requests.patch.assert_called_once_with(
        expected_url, data=data, timeout=KONG_REQUEST_TIMEOUT
    )


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

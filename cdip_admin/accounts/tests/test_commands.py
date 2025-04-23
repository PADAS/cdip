from unittest.mock import ANY

import pytest
from django.core.management import call_command


pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("gundi_version", ["v1", "v2"])
def test_call_api_consumers_command_list(
    mocker,
    gundi_version,
    mock_api_consumer_info,
    capsys,
    organization,
    inbound_integration_awt,
    provider_ats,
):
    mock_get_api_consumer_info = mocker.MagicMock()
    mock_get_api_consumer_info.return_value = mock_api_consumer_info
    mocker.patch("accounts.management.commands.api_consumers.get_api_consumer_info", mock_get_api_consumer_info)

    call_command("api_consumers", f"--{gundi_version}")
    captured = capsys.readouterr()

    if gundi_version == "v1":
        mock_get_api_consumer_info.assert_called_once_with(inbound_integration_awt)
    elif gundi_version == "v2":
        mock_get_api_consumer_info.assert_called_once_with(provider_ats)
    assert "Consumer info:" in captured.out
    assert "Decoded data:" in captured.out


@pytest.mark.parametrize("gundi_version", ["v1", "v2"])
def test_call_api_consumers_set_integration_type(
    mocker,
    gundi_version,
    mock_api_consumer_info,
    capsys,
    organization,
    inbound_integration_awt,
    provider_ats,
):
    mock_get_api_consumer_info = mocker.MagicMock()
    mock_get_api_consumer_info.return_value = mock_api_consumer_info
    mocker.patch("accounts.management.commands.api_consumers.get_api_consumer_info", mock_get_api_consumer_info)
    mock_patch_api_consumer_info = mocker.MagicMock()
    mocker.patch("accounts.management.commands.api_consumers.patch_api_consumer_info", mock_patch_api_consumer_info)

    call_command("api_consumers", f"--{gundi_version}", "--set-integration-type")
    captured = capsys.readouterr()

    if gundi_version == "v1":
        mock_patch_api_consumer_info.assert_called_once_with(inbound_integration_awt, ANY)
    elif gundi_version == "v2":
        mock_patch_api_consumer_info.assert_called_once_with(provider_ats, ANY)
    assert "Setting integration type" in captured.out
    assert "Patching consumer info" in captured.out

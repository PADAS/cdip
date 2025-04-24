import base64
import json

import pytest
from django.core.management import call_command


pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("gundi_version", ["v1", "v2"])
def test_call_api_consumers_get_list(
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
def test_call_api_consumers_get_integration_consumer_info(
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
    if gundi_version == "v1":
        integration = inbound_integration_awt
    elif gundi_version == "v2":
        integration = provider_ats
    else:
        raise ValueError("Invalid gundi version")

    call_command("api_consumers", f"--{gundi_version}", "--integration", f"{integration.id}")

    captured = capsys.readouterr()
    if gundi_version == "v1":
        mock_get_api_consumer_info.assert_called_once_with(inbound_integration_awt)
    elif gundi_version == "v2":
        mock_get_api_consumer_info.assert_called_once_with(provider_ats)
    assert "Consumer info:" in captured.out
    assert "Decoded data:" in captured.out


@pytest.mark.parametrize("gundi_version", ["v1", "v2"])
def test_call_api_consumers_get_integration_api_key(
    mocker,
    gundi_version,
    mock_api_consumer_info,
    mock_get_api_key,
    capsys,
    organization,
    inbound_integration_awt,
    provider_ats,
):
    mock_get_api_consumer_info = mocker.MagicMock()
    mock_get_api_consumer_info.return_value = mock_api_consumer_info
    mocker.patch("accounts.management.commands.api_consumers.get_api_consumer_info", mock_get_api_consumer_info)
    mocker.patch("accounts.management.commands.api_consumers.get_api_key", mock_get_api_key)

    if gundi_version == "v1":
        integration = inbound_integration_awt
    elif gundi_version == "v2":
        integration = provider_ats
    else:
        raise ValueError("Invalid gundi version")

    call_command("api_consumers", f"--{gundi_version}", "--get-key", "--integration", f"{integration.id}")

    captured = capsys.readouterr()
    if gundi_version == "v1":
        mock_get_api_consumer_info.assert_called_once_with(inbound_integration_awt)
    elif gundi_version == "v2":
        mock_get_api_consumer_info.assert_called_once_with(provider_ats)
    assert "Consumer info:" in captured.out
    assert "Decoded data:" in captured.out
    assert f"API key: {mock_get_api_key()}" in captured.out


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
    custom_data = json.loads(base64.b64decode(mock_api_consumer_info["custom_id"]).decode("utf-8").strip())
    if gundi_version == "v1":
        expected_integration_type = inbound_integration_awt.type.slug
        expected_update_data = {
            "custom_id": base64.b64encode(
                json.dumps({**custom_data, "integration_type": expected_integration_type}).encode("utf-8"))
        }
        mock_patch_api_consumer_info.assert_called_once_with(
            integration=inbound_integration_awt,
            data=expected_update_data
        )
    elif gundi_version == "v2":
        expected_integration_type = provider_ats.type.value
        expected_update_data = {
            "custom_id": base64.b64encode(
                json.dumps({**custom_data, "integration_type": expected_integration_type}).encode("utf-8"))
        }
        mock_patch_api_consumer_info.assert_called_once_with(
            integration=provider_ats,
            data=expected_update_data
        )
    assert "Setting integration type" in captured.out
    assert "Patching consumer info" in captured.out


@pytest.mark.parametrize("gundi_version", ["v1", "v2"])
def test_call_api_consumers_set_integration_type_dry_run(
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

    call_command("api_consumers", f"--{gundi_version}", "--set-integration-type", "--dry-run")
    captured = capsys.readouterr()

    if gundi_version == "v1":
        mock_patch_api_consumer_info.assert_not_called()
    elif gundi_version == "v2":
        mock_patch_api_consumer_info.assert_not_called()
    assert "Dry run, not applying changes." in captured.out

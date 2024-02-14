from unittest.mock import patch
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError


pytestmark = pytest.mark.django_db


def test_call_dispatchers_command_list_missing(
    capsys,
    organization,
    outbound_integration_er_no_broker,
    outbound_integration_er_with_kafka_dispatcher,
    outbound_integration_smart_with_kafka_dispatcher,
):
    call_command("dispatchers", "--list-missing")
    captured = capsys.readouterr()

    assert f"3 integrations using legacy dispatchers (kafka consumers):" in captured.out
    integration = outbound_integration_er_no_broker
    assert (
        f"({integration.type.slug}) - {integration.name} - {str(integration.id)}"
        in captured.out
    )
    integration = outbound_integration_er_with_kafka_dispatcher
    assert (
        f"({integration.type.slug}) - {integration.name} - {str(integration.id)}"
        in captured.out
    )
    integration = outbound_integration_smart_with_kafka_dispatcher
    assert (
        f"({integration.type.slug}) - {integration.name} - {str(integration.id)}"
        in captured.out
    )


def test_call_dispatchers_command_deploy_missing_for_earthranger(
    mocker,
    capsys,
    organization,
    outbound_integration_er_no_broker,
    outbound_integration_er_with_kafka_dispatcher,
    outbound_integration_smart_with_kafka_dispatcher,
):
    # Mock the celery task doing the actual deployment
    mocker.patch("deployments.models.transaction.on_commit", lambda fn: fn())
    mock_deploy_serverless_dispatcher = mocker.MagicMock()
    mocker.patch(
        "deployments.models.deploy_serverless_dispatcher",
        mock_deploy_serverless_dispatcher,
    )

    call_command("dispatchers", "--v1", "--deploy-missing", "--type", "earth_ranger")
    captured = capsys.readouterr()

    for integration in [
        outbound_integration_er_no_broker,
        outbound_integration_er_with_kafka_dispatcher,
    ]:
        # Check that configuration was updated to use pubsub
        integration.refresh_from_db()
        assert integration.additional.get("broker") == "gcp_pubsub"
        assert integration.additional.get("topic")  # Topic name must be set
        # Check the command output
        assert f"Deploying dispatcher for {integration.name}..." in captured.out
        assert f"Deployment triggered for {integration.name} (v1)" in captured.out

    # Check that the deploy task was called for the two ER integrations using legacy dispatchers
    assert mock_deploy_serverless_dispatcher.delay.call_count == 2


def test_call_dispatchers_command_deploy_missing_for_smart(
    mocker,
    capsys,
    organization,
    outbound_integration_er_no_broker,
    outbound_integration_er_with_kafka_dispatcher,
    outbound_integration_smart_with_kafka_dispatcher,
):
    # Mock the celery task doing the actual deployment
    mocker.patch("deployments.models.transaction.on_commit", lambda fn: fn())
    mock_deploy_serverless_dispatcher = mocker.MagicMock()
    mocker.patch(
        "deployments.models.deploy_serverless_dispatcher",
        mock_deploy_serverless_dispatcher,
    )

    call_command("dispatchers", "--v1", "--deploy-missing", "--type", "smart_connect")
    captured = capsys.readouterr()

    # Check that configuration was updated to use pubsub
    integration = outbound_integration_smart_with_kafka_dispatcher
    integration.refresh_from_db()
    assert integration.additional.get("broker") == "gcp_pubsub"
    assert integration.additional.get("topic")  # Topic name must be set
    # Check the command output
    assert f"Deploying dispatcher for {integration.name}..." in captured.out
    assert f"Deployment triggered for {integration.name} (v1)" in captured.out

    # Check that the deploy task was called for the smart integration using legacy dispatchers
    assert mock_deploy_serverless_dispatcher.delay.call_count == 1


def test_call_dispatchers_command_deploy_with_integration_id(
    mocker,
    capsys,
    organization,
    outbound_integration_er_no_broker,
    outbound_integration_er_with_kafka_dispatcher,
    outbound_integration_smart_with_kafka_dispatcher,
):
    # Mock the celery task doing the actual deployment
    mocker.patch("deployments.models.transaction.on_commit", lambda fn: fn())
    mock_deploy_serverless_dispatcher = mocker.MagicMock()
    mocker.patch(
        "deployments.models.deploy_serverless_dispatcher",
        mock_deploy_serverless_dispatcher,
    )
    integration = outbound_integration_er_no_broker

    call_command("dispatchers", "--v1", "--deploy", str(integration.id))
    captured = capsys.readouterr()

    # Check that configuration was updated to use pubsub
    integration.refresh_from_db()
    assert integration.additional.get("broker") == "gcp_pubsub"
    assert integration.additional.get("topic")  # Topic name must be set
    # Check the command output
    assert f"Deploying dispatcher for {integration.name}..." in captured.out
    assert f"Deployment triggered for {integration.name} (v1)" in captured.out

    # Check that the deploy task was called for the selected ER integration
    assert mock_deploy_serverless_dispatcher.delay.called
import pytest
from django.core.management import call_command
from django.test import override_settings


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


@pytest.mark.parametrize("gundi_version", ["v1", "v2"])
@pytest.mark.parametrize("integration_type", [
    "earth_ranger",
    "smart_connect",
    "wps_watch"
])
@override_settings(GCP_ENVIRONMENT_ENABLED=True)
def test_call_dispatchers_command_update_source_by_type_with_max_v1(
    request,
    gundi_version,
    integration_type,
    mocker,
    capsys,
    organization,
    dispatcher_source_release_1,
    dispatcher_source_release_2
):
    if gundi_version == "v1":
        integrations_er = request.getfixturevalue("outbound_integrations_list_er")
        integrations_smart = request.getfixturevalue("outbound_integrations_list_smart")
        integrations_wps = request.getfixturevalue("outbound_integrations_list_wpswatch")
    else:
        integrations_er = request.getfixturevalue("integrations_list_er")
        integrations_smart = request.getfixturevalue("integrations_list_smart")
        integrations_wps = request.getfixturevalue("integrations_list_wpswatch")
    # Mock the celery task doing the actual deployment
    mocker.patch("deployments.models.transaction.on_commit", lambda fn: fn())
    mock_deploy_serverless_dispatcher = mocker.MagicMock()
    mocker.patch(
        "deployments.models.deploy_serverless_dispatcher",
        mock_deploy_serverless_dispatcher,
    )

    call_command(
        "dispatchers", f"--{gundi_version}", "--type", integration_type, "--max", "2", "--update-source", dispatcher_source_release_2
    )
    captured = capsys.readouterr()

    source_key = "source_code_path" if integration_type == "earth_ranger" else "docker_image_url"
    if integration_type == "earth_ranger":
        integrations_list = integrations_er
    elif integration_type == "smart_connect":
        integrations_list = integrations_smart
    else:
        integrations_list = integrations_wps
    sorted_integrations = sorted(integrations_list, key=lambda i: i.name)
    for integration in sorted_integrations[:2]:
        # Check that configuration was updated to the new release
        integration.refresh_from_db()
        dispatcher = integration.dispatcher_by_outbound if gundi_version == "v1" else integration.dispatcher_by_integration
        source_code_settings = dispatcher.configuration.get("deployment_settings", {}).get(source_key)
        assert source_code_settings == dispatcher_source_release_2
        # Check the command output
        assert f"Updating dispatcher for {integration.name} with env_vars: None, deployment_settings {{'{source_key}': '{dispatcher_source_release_2}'}}..." in captured.out
        assert f"Update triggered for {integration.name}" in captured.out

    for integration in sorted_integrations[2:]:
        # Check that configuration of other integrations was not updated
        integration.refresh_from_db()
        dispatcher = integration.dispatcher_by_outbound if gundi_version == "v1" else integration.dispatcher_by_integration
        source_code_settings = dispatcher.configuration.get("deployment_settings", {}).get(source_key)
        assert source_code_settings == dispatcher_source_release_1

    # Check that the deploy task was called for the two ER integrations being updated
    assert mock_deploy_serverless_dispatcher.delay.call_count == 2


@pytest.mark.parametrize("integration_type", [
    "earth_ranger",
    "smart_connect",
    "wps_watch"
])
@override_settings(GCP_ENVIRONMENT_ENABLED=True)
def test_call_dispatchers_command_update_source_by_id_v1(
    request,
    integration_type,
    mocker,
    capsys,
    organization,
    outbound_integrations_list_er,
    outbound_integrations_list_smart,
    outbound_integrations_list_wpswatch,
    dispatcher_source_release_1,
    dispatcher_source_release_2
):
    # Mock the celery task doing the actual deployment
    mocker.patch("deployments.models.transaction.on_commit", lambda fn: fn())
    mock_deploy_serverless_dispatcher = mocker.MagicMock()
    mocker.patch(
        "deployments.models.deploy_serverless_dispatcher",
        mock_deploy_serverless_dispatcher,
    )

    # Pick one integration to update
    if integration_type == "earth_ranger":
        integration = outbound_integrations_list_er[0]
    elif integration_type == "smart_connect":
        integration = outbound_integrations_list_smart[0]
    else:
        integration = outbound_integrations_list_wpswatch[0]

    call_command(
        "dispatchers", "--v1", "--integration", str(integration.id), "--update-source", dispatcher_source_release_2
    )
    captured = capsys.readouterr()

    source_key = "source_code_path" if integration_type == "earth_ranger" else "docker_image_url"

    # Check that configuration was updated to the new release
    integration.refresh_from_db()
    source_code_settings = integration.dispatcher_by_outbound.configuration.get("deployment_settings", {}).get(source_key)
    assert source_code_settings == dispatcher_source_release_2
    # Check the command output
    assert f"Updating dispatcher for {integration.name} with env_vars: None, deployment_settings {{'{source_key}': '{dispatcher_source_release_2}'}}..." in captured.out
    assert f"Update triggered for {integration.name}" in captured.out

    # Check that the deploy task was called for the two ER integrations being updated
    assert mock_deploy_serverless_dispatcher.delay.called


@pytest.mark.parametrize("gundi_version", ["v1", "v2"])
@pytest.mark.parametrize("integration_type", [
    "earth_ranger",
    "smart_connect",
    "wps_watch"
])
@override_settings(GCP_ENVIRONMENT_ENABLED=True)
def test_call_dispatchers_command_recreate_by_type_with_max_v1(
    request,
    gundi_version,
    integration_type,
    mocker,
    capsys,
    organization,
    dispatcher_source_release_1
):
    if gundi_version == "v1":
        integrations_er = request.getfixturevalue("outbound_integrations_list_er")
        integrations_smart = request.getfixturevalue("outbound_integrations_list_smart")
        integrations_wps = request.getfixturevalue("outbound_integrations_list_wpswatch")
    else:
        integrations_er = request.getfixturevalue("integrations_list_er")
        integrations_smart = request.getfixturevalue("integrations_list_smart")
        integrations_wps = request.getfixturevalue("integrations_list_wpswatch")
    # Mock the celery task doing the actual deployment
    mocker.patch("deployments.models.transaction.on_commit", lambda fn: fn())
    mock_deploy_serverless_dispatcher = mocker.MagicMock()
    mocker.patch(
        "deployments.models.deploy_serverless_dispatcher",
        mock_deploy_serverless_dispatcher,
    )
    mocker.patch(
        "deployments.management.commands.dispatchers.deploy_serverless_dispatcher",
        mock_deploy_serverless_dispatcher
    )

    call_command(
        "dispatchers", f"--{gundi_version}", "--type", integration_type, "--max", "2",
        "--recreate"
    )

    if integration_type == "earth_ranger":
        integrations_list = integrations_er
    elif integration_type == "smart_connect":
        integrations_list = integrations_smart
    else:
        integrations_list = integrations_wps
    sorted_integrations = sorted(integrations_list, key=lambda i: i.name)
    # Check that the deployment task is triggered for each integration
    assert mock_deploy_serverless_dispatcher.delay.call_count == 2
    for integration in sorted_integrations[:2]:
        if gundi_version == "v1":
            mock_deploy_serverless_dispatcher.delay.assert_any_call(
                deployment_id=integration.dispatcher_by_outbound.id,
                force_recreate=True,
                deployment_settings=None  # Reuse existent settings
            )
        else:
            mock_deploy_serverless_dispatcher.delay.assert_any_call(
                deployment_id=integration.dispatcher_by_integration.id,
                force_recreate=True,
                deployment_settings=None  # Reuse existent settings
            )


@pytest.mark.parametrize("gundi_version", ["v1", "v2"])
@pytest.mark.parametrize("integration_type", [
    "earth_ranger",
    "smart_connect",
    "wps_watch",
    "trap_tagger"
])
@override_settings(GCP_ENVIRONMENT_ENABLED=True)
def test_call_dispatchers_command_recreate_and_update_source_by_type_with_max_v1(
    request,
    gundi_version,
    integration_type,
    mocker,
    capsys,
    organization,
    dispatcher_source_release_1,
    dispatcher_source_release_2
):
    if integration_type == "trap_tagger" and gundi_version == "v1":
        pytest.skip("Trap Tagger is not supported in v1")

    if gundi_version == "v1":
        integrations_er = request.getfixturevalue("outbound_integrations_list_er")
        integrations_smart = request.getfixturevalue("outbound_integrations_list_smart")
        integrations_wps = request.getfixturevalue("outbound_integrations_list_wpswatch")
        integrations_list_traptagger_dest = []
    else:
        integrations_er = request.getfixturevalue("integrations_list_er")
        integrations_smart = request.getfixturevalue("integrations_list_smart")
        integrations_wps = request.getfixturevalue("integrations_list_wpswatch")
        integrations_list_traptagger_dest = request.getfixturevalue("integrations_list_traptagger_dest")

    # Mock the celery task doing the actual deployment
    mocker.patch("deployments.models.transaction.on_commit", lambda fn: fn())
    mock_deploy_serverless_dispatcher = mocker.MagicMock()
    mocker.patch(
        "deployments.models.deploy_serverless_dispatcher",
        mock_deploy_serverless_dispatcher,
    )
    mocker.patch(
        "deployments.management.commands.dispatchers.deploy_serverless_dispatcher",
        mock_deploy_serverless_dispatcher
    )

    call_command(
        "dispatchers", f"--{gundi_version}", "--type", integration_type, "--max", "2",
        "--recreate", "--update-source", dispatcher_source_release_2
    )

    source_key = "source_code_path" if integration_type == "earth_ranger" else "docker_image_url"
    if integration_type == "earth_ranger":
        integrations_list = integrations_er
    elif integration_type == "smart_connect":
        integrations_list = integrations_smart
    elif integration_type == "wps_watch":
        integrations_list = integrations_wps
    elif integration_type == "trap_tagger":
        integrations_list = integrations_list_traptagger_dest
    sorted_integrations = sorted(integrations_list, key=lambda i: i.name)
    # Check that the deployment task is triggered for each integration
    assert mock_deploy_serverless_dispatcher.delay.call_count == 2
    for integration in sorted_integrations[:2]:
        if gundi_version == "v1":
            mock_deploy_serverless_dispatcher.delay.assert_any_call(
                deployment_id=integration.dispatcher_by_outbound.id,
                force_recreate=True,
                deployment_settings={source_key: dispatcher_source_release_2}
            )
        else:
            mock_deploy_serverless_dispatcher.delay.assert_any_call(
                deployment_id=integration.dispatcher_by_integration.id,
                force_recreate=True,
                deployment_settings={source_key: dispatcher_source_release_2}
            )

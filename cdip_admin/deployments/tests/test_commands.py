import pytest
from django.core.management import call_command
from django.test import override_settings

from deployments.models import DispatcherDeployment
from integrations.models import Integration


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


def test_call_dispatchers_command_list_unused(
    mocker,
    capsys,
    organization,
    integrations_list_er,
):
    # Mock the celery task triggered when deployments are created
    mocker.patch("deployments.models.transaction.on_commit", lambda fn: fn())
    mocker.patch(
        "deployments.models.deploy_serverless_dispatcher", mocker.MagicMock()
    )
    # Orphaned deployment whose topic isn't referenced by any integration -> unused
    unused_deployment = DispatcherDeployment.objects.create(
        name="orphan-dispatcher", topic_name="orphan-topic"
    )
    # Orphaned deployment with no topic recorded -> unused
    unused_deployment_no_topic = DispatcherDeployment.objects.create(
        name="orphan-dispatcher-no-topic", topic_name=None
    )
    # Orphaned deployment whose topic is still used by an integration -> in use
    integration = integrations_list_er[0]
    shared_topic_deployment = DispatcherDeployment.objects.create(
        name="orphan-shared-topic-dispatcher",
        topic_name=integration.additional["topic"],
    )
    # Deployments created by the fixture are linked by FK -> in use
    linked_deployment = integration.dispatcher_by_integration

    call_command("dispatchers", "--list-unused")
    captured = capsys.readouterr()

    assert "2 unused deployments:" in captured.out
    assert unused_deployment.name in captured.out
    assert unused_deployment_no_topic.name in captured.out
    assert shared_topic_deployment.name not in captured.out
    assert linked_deployment.name not in captured.out


def test_call_dispatchers_command_delete_unused_with_yes(
    mocker,
    capsys,
    organization,
    integrations_list_er,
):
    mocker.patch("deployments.models.transaction.on_commit", lambda fn: fn())
    mocker.patch(
        "deployments.models.deploy_serverless_dispatcher", mocker.MagicMock()
    )
    mock_delete_task = mocker.MagicMock()
    mocker.patch(
        "deployments.models.delete_serverless_dispatcher", mock_delete_task
    )
    unused_deployment = DispatcherDeployment.objects.create(
        name="orphan-dispatcher", topic_name="orphan-topic"
    )
    integration = integrations_list_er[0]
    shared_topic_deployment = DispatcherDeployment.objects.create(
        name="orphan-shared-topic-dispatcher",
        topic_name=integration.additional["topic"],
    )
    linked_deployment = integration.dispatcher_by_integration

    call_command("dispatchers", "--delete-unused", "--yes")
    captured = capsys.readouterr()

    assert f"Deletion triggered for {unused_deployment.name}" in captured.out
    # The deletion task tears down GCP resources and then removes the row
    mock_delete_task.delay.assert_called_once_with(
        deployment_id=str(unused_deployment.id), topic="orphan-topic"
    )
    # In-use deployments are untouched
    assert DispatcherDeployment.objects.filter(id=shared_topic_deployment.id).exists()
    assert DispatcherDeployment.objects.filter(id=linked_deployment.id).exists()


def test_call_dispatchers_command_delete_unused_aborts_without_confirmation(
    mocker,
    capsys,
    organization,
):
    mocker.patch("deployments.models.transaction.on_commit", lambda fn: fn())
    mocker.patch(
        "deployments.models.deploy_serverless_dispatcher", mocker.MagicMock()
    )
    mock_delete_task = mocker.MagicMock()
    mocker.patch(
        "deployments.models.delete_serverless_dispatcher", mock_delete_task
    )
    mocker.patch("builtins.input", return_value="n")
    unused_deployment = DispatcherDeployment.objects.create(
        name="orphan-dispatcher", topic_name="orphan-topic"
    )

    call_command("dispatchers", "--delete-unused")
    captured = capsys.readouterr()

    assert "Aborted." in captured.out
    assert "Done." not in captured.out
    mock_delete_task.delay.assert_not_called()
    assert DispatcherDeployment.objects.filter(id=unused_deployment.id).exists()


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
# No @override_settings(GCP_ENVIRONMENT_ENABLED=True) here: the list fixtures
# (instantiated mid-test via request.getfixturevalue) already set it through the
# pytest-django settings fixture. Combining both makes the decorator's disable()
# and the fixture's finalizer run out of order, leaking GCP_ENVIRONMENT_ENABLED=True
# into every later test in the session.
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
# See note on test_call_dispatchers_command_update_source_by_type_with_max_v1
# about why there is no GCP_ENVIRONMENT_ENABLED override here.
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
# See note on test_call_dispatchers_command_update_source_by_type_with_max_v1
# about why there is no GCP_ENVIRONMENT_ENABLED override here.
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


SHARED = "root-er-test-topic"


def _make_er_destination_with_deployment(request, name, topic="destination-old-topic"):
    # Build an ER integration with a linked deployment, without triggering
    # real deploys (GCP_ENVIRONMENT_ENABLED is False by default in tests).
    integration_type_er = request.getfixturevalue("integration_type_er")
    organization = request.getfixturevalue("organization")
    from deployments.models import DispatcherDeployment
    integration = Integration.objects.create(
        type=integration_type_er,
        name=name,
        owner=organization,
        base_url=f"https://{name.lower().replace(' ', '')}.pamdas.org",
        additional={"broker": "gcp_pubsub", "topic": topic},
    )
    deployment = DispatcherDeployment.objects.create(
        name=f"dispatcher-{name.lower().replace(' ', '-')}",
        integration=integration,
        topic_name=topic,
        configuration={"env_vars": {"GCP_PROJECT_ID": "test-project"}},
    )
    return integration, deployment


@pytest.mark.django_db
@override_settings(ER_SHARED_DISPATCHER_TOPIC=SHARED)
def test_migrate_to_shared_flips_topic_and_stamps_bookkeeping(request, capsys):
    integration, deployment = _make_er_destination_with_deployment(request, "Reserve A")

    call_command("dispatchers", "--migrate-to-shared", "--max", "10")

    integration.refresh_from_db()
    assert integration.additional["topic"] == SHARED
    assert integration.additional["pre_migration_topic"] == "destination-old-topic"
    assert integration.additional["shared_pool_migrated_at"]  # ISO timestamp
    # Nothing deleted: the old deployment is the rollback lever
    deployment.refresh_from_db()
    assert deployment.integration_id == integration.id


@pytest.mark.django_db
@override_settings(ER_SHARED_DISPATCHER_TOPIC=SHARED)
def test_migrate_to_shared_skips_dedicated_and_already_migrated(request, capsys):
    dedicated, _ = _make_er_destination_with_deployment(request, "Dedicated B")
    dedicated.additional["dedicated_dispatcher"] = True
    dedicated.save()
    migrated, _ = _make_er_destination_with_deployment(request, "Done C", topic=SHARED)

    call_command("dispatchers", "--migrate-to-shared", "--max", "10")

    dedicated.refresh_from_db()
    assert dedicated.additional["topic"] == "destination-old-topic"
    migrated.refresh_from_db()
    assert "pre_migration_topic" not in migrated.additional  # untouched


@pytest.mark.django_db
def test_migrate_to_shared_refuses_when_setting_empty(request, capsys):
    _make_er_destination_with_deployment(request, "Reserve D")

    call_command("dispatchers", "--migrate-to-shared", "--max", "10")

    out = capsys.readouterr()
    assert "ER_SHARED_DISPATCHER_TOPIC" in (out.out + out.err)
    integration = Integration.objects.get(name="Reserve D")
    assert integration.additional["topic"] == "destination-old-topic"


@pytest.mark.django_db
@override_settings(ER_SHARED_DISPATCHER_TOPIC=SHARED)
def test_rollback_shared_restores_topic(request, capsys):
    integration, _ = _make_er_destination_with_deployment(request, "Reserve E")
    call_command("dispatchers", "--migrate-to-shared", "--integration", str(integration.id), "--max", "1")

    call_command("dispatchers", "--rollback-shared", "--integration", str(integration.id))

    integration.refresh_from_db()
    assert integration.additional["topic"] == "destination-old-topic"
    assert "pre_migration_topic" not in integration.additional
    assert "shared_pool_migrated_at" not in integration.additional


@pytest.mark.django_db
@override_settings(ER_SHARED_DISPATCHER_TOPIC=SHARED)
def test_rollback_shared_refuses_after_teardown(request, capsys):
    integration, deployment = _make_er_destination_with_deployment(request, "Reserve F")
    call_command("dispatchers", "--migrate-to-shared", "--integration", str(integration.id), "--max", "1")
    # Simulate teardown having removed the deployment
    from deployments.models import DispatcherDeployment
    DispatcherDeployment.objects.filter(pk=deployment.pk).delete()

    call_command("dispatchers", "--rollback-shared", "--integration", str(integration.id))

    out = capsys.readouterr()
    assert "no longer exists" in (out.out + out.err)
    integration.refresh_from_db()
    assert integration.additional["topic"] == SHARED  # unchanged


@pytest.mark.django_db
@override_settings(ER_SHARED_DISPATCHER_TOPIC=SHARED)
def test_teardown_respects_cooling_period(request, mocker, capsys):
    integration, deployment = _make_er_destination_with_deployment(request, "Reserve G")
    call_command("dispatchers", "--migrate-to-shared", "--integration", str(integration.id), "--max", "1")
    mock_drained = mocker.patch(
        "deployments.management.commands.dispatchers.subscription_is_drained", return_value=True
    )
    mock_delete_task = mocker.patch("deployments.models.delete_serverless_dispatcher")

    # Migrated seconds ago: inside the cooling period -> nothing torn down
    call_command("dispatchers", "--teardown-migrated", "--max", "10")

    assert DispatcherDeployment.objects.filter(pk=deployment.pk).exists()
    mock_delete_task.delay.assert_not_called()

    # Backdate the stamp beyond the cooling period -> teardown proceeds
    integration.refresh_from_db()
    from datetime import timedelta
    from django.utils import timezone
    old = (timezone.now() - timedelta(days=8)).isoformat()
    integration.additional["shared_pool_migrated_at"] = old
    Integration.objects.filter(pk=integration.pk).update(additional=integration.additional)

    call_command("dispatchers", "--teardown-migrated", "--max", "10")

    integration.refresh_from_db()
    assert "shared_pool_migrated_at" not in integration.additional
    assert mock_drained.called
    assert not DispatcherDeployment.objects.filter(pk=deployment.pk, integration__isnull=False).exists()
    mock_delete_task.delay.assert_called_once()  # teardown task actually fired


@pytest.mark.django_db
@override_settings(ER_SHARED_DISPATCHER_TOPIC=SHARED)
def test_teardown_hard_skips_deployment_recording_shared_topic(request, mocker, capsys):
    integration, deployment = _make_er_destination_with_deployment(request, "Reserve H", topic=SHARED)
    # Corrupt state: deployment records the shared topic as its own
    DispatcherDeployment.objects.filter(pk=deployment.pk).update(topic_name=SHARED)
    from datetime import timedelta
    from django.utils import timezone
    Integration.objects.filter(pk=integration.pk).update(additional={
        **integration.additional,
        "shared_pool_migrated_at": (timezone.now() - timedelta(days=8)).isoformat(),
    })
    mocker.patch("deployments.management.commands.dispatchers.subscription_is_drained", return_value=True)
    mock_delete_task = mocker.patch("deployments.models.delete_serverless_dispatcher")

    call_command("dispatchers", "--teardown-migrated", "--max", "10")

    out = capsys.readouterr()
    assert "shared topic" in (out.out + out.err).lower()
    assert DispatcherDeployment.objects.filter(pk=deployment.pk).exists()
    mock_delete_task.delay.assert_not_called()


@pytest.mark.django_db
@override_settings(ER_SHARED_DISPATCHER_TOPIC=SHARED)
def test_teardown_skips_undrained_subscription(request, mocker, capsys):
    integration, deployment = _make_er_destination_with_deployment(request, "Reserve I")
    call_command("dispatchers", "--migrate-to-shared", "--integration", str(integration.id), "--max", "1")
    from datetime import timedelta
    from django.utils import timezone
    integration.refresh_from_db()
    Integration.objects.filter(pk=integration.pk).update(additional={
        **integration.additional,
        "shared_pool_migrated_at": (timezone.now() - timedelta(days=8)).isoformat(),
    })
    mocker.patch(
        "deployments.management.commands.dispatchers.subscription_is_drained", return_value=False
    )
    mock_delete_task = mocker.patch("deployments.models.delete_serverless_dispatcher")

    call_command("dispatchers", "--teardown-migrated", "--max", "10")

    assert DispatcherDeployment.objects.filter(pk=deployment.pk, integration__isnull=False).exists()
    mock_delete_task.delay.assert_not_called()


@pytest.mark.django_db
@override_settings(ER_SHARED_DISPATCHER_TOPIC=SHARED)
def test_teardown_stamps_manually_migrated_on_first_sight(request, mocker, capsys):
    # Manually moved to the shared topic previously: no stamp yet
    integration, deployment = _make_er_destination_with_deployment(request, "Reserve J", topic=SHARED)
    mocker.patch("deployments.management.commands.dispatchers.subscription_is_drained", return_value=True)
    mock_delete_task = mocker.patch("deployments.models.delete_serverless_dispatcher")

    call_command("dispatchers", "--teardown-migrated", "--max", "10")

    integration.refresh_from_db()
    assert integration.additional.get("shared_pool_migrated_at")  # stamped, not torn down
    assert DispatcherDeployment.objects.filter(pk=deployment.pk).exists()
    mock_delete_task.delay.assert_not_called()


@pytest.mark.django_db
@override_settings(ER_SHARED_DISPATCHER_TOPIC=SHARED)
def test_teardown_survives_malformed_migration_stamp(request, mocker, capsys):
    """A corrupt shared_pool_migrated_at (not ISO-parseable) must be reported
    and skipped, not crash the whole command - it should still process later
    integrations in the queryset."""
    from datetime import timedelta
    from django.utils import timezone
    from deployments.models import DispatcherDeployment

    # Integration with malformed timestamp
    integration, deployment = _make_er_destination_with_deployment(request, "Reserve K", topic=SHARED)
    Integration.objects.filter(pk=integration.pk).update(additional={
        **integration.additional, "shared_pool_migrated_at": "not-a-real-timestamp",
    })

    # Healthy integration that should be processed normally
    # Create with old dedicated topic first, then migrate to shared pool
    healthy_integration, healthy_deployment = _make_er_destination_with_deployment(request, "Reserve K2", topic="old-dedicated-topic")
    # Update to simulate being migrated to shared pool
    Integration.objects.filter(pk=healthy_integration.pk).update(additional={
        "broker": "gcp_pubsub",
        "topic": SHARED,
        "pre_migration_topic": "old-dedicated-topic",
        "shared_pool_migrated_at": (timezone.now() - timedelta(days=8)).isoformat(),
    })

    mocker.patch("deployments.management.commands.dispatchers.subscription_is_drained", return_value=True)
    mock_delete_task = mocker.patch("deployments.models.delete_serverless_dispatcher")

    call_command("dispatchers", "--teardown-migrated", "--max", "10")
    out = capsys.readouterr()

    assert f"Error tearing down {integration.name}" in (out.out + out.err)
    # Nothing was torn down; the malformed row is left alone for manual fixing
    assert DispatcherDeployment.objects.filter(pk=deployment.pk).exists()

    # Healthy integration should still be processed
    assert not DispatcherDeployment.objects.filter(pk=healthy_deployment.pk, integration__isnull=False).exists()
    mock_delete_task.delay.assert_called_once()


@pytest.mark.django_db
@override_settings(ER_SHARED_DISPATCHER_TOPIC=SHARED)
def test_teardown_handles_naive_migration_stamp(request, mocker, capsys):
    """A hand-edited shared_pool_migrated_at without a timezone offset (naive)
    must be treated as UTC and compared normally against the (aware) cooling
    cutoff, rather than being skipped forever with an aware/naive TypeError."""
    from datetime import timedelta
    from django.utils import timezone

    # Deployment records a dedicated topic; the integration was migrated onto
    # the shared pool. The migration stamp is naive (no tz offset).
    integration, deployment = _make_er_destination_with_deployment(request, "Reserve L", topic="old-dedicated-topic")
    naive_stamp = (timezone.now() - timedelta(days=8)).replace(tzinfo=None).isoformat()
    Integration.objects.filter(pk=integration.pk).update(additional={
        "broker": "gcp_pubsub",
        "topic": SHARED,
        "pre_migration_topic": "old-dedicated-topic",
        "shared_pool_migrated_at": naive_stamp,
    })
    mocker.patch("deployments.management.commands.dispatchers.subscription_is_drained", return_value=True)
    mock_delete_task = mocker.patch("deployments.models.delete_serverless_dispatcher")

    call_command("dispatchers", "--teardown-migrated", "--max", "10")
    out = capsys.readouterr()

    assert "Error tearing down" not in (out.out + out.err)
    assert not DispatcherDeployment.objects.filter(pk=deployment.pk, integration__isnull=False).exists()
    mock_delete_task.delay.assert_called_once()


@pytest.mark.django_db
@override_settings(ER_SHARED_DISPATCHER_TOPIC=SHARED)
def test_migrate_to_shared_skips_when_pre_migration_topic_is_falsy(request, capsys):
    """If neither additional.topic nor the deployment's recorded topic_name
    are set, we can't compute a rollback lever - migrating anyway would
    brick --rollback-shared. The integration must be skipped, not migrated
    with a falsy pre_migration_topic."""
    integration_type_er = request.getfixturevalue("integration_type_er")
    organization = request.getfixturevalue("organization")
    from deployments.models import DispatcherDeployment
    integration = Integration.objects.create(
        type=integration_type_er,
        name="Reserve L",
        owner=organization,
        base_url="https://reservel.pamdas.org",
        additional={"broker": "gcp_pubsub"},  # no "topic" key at all
    )
    DispatcherDeployment.objects.create(
        name="dispatcher-reserve-l",
        integration=integration,
        topic_name=None,  # nothing to fall back on either
        configuration={"env_vars": {"GCP_PROJECT_ID": "test-project"}},
    )

    call_command("dispatchers", "--migrate-to-shared", "--integration", str(integration.id), "--max", "1")
    out = capsys.readouterr()

    assert "cannot determine pre-migration topic" in (out.out + out.err)
    integration.refresh_from_db()
    assert "pre_migration_topic" not in integration.additional
    assert "shared_pool_migrated_at" not in integration.additional
    assert integration.additional.get("topic") != SHARED  # not migrated


@pytest.mark.django_db
@override_settings(ER_SHARED_DISPATCHER_TOPIC=SHARED)
def test_update_source_excludes_migrated_integrations(
    request, mocker, capsys, dispatcher_source_release_1, dispatcher_source_release_2
):
    """--update-source/--recreate must not select integrations already on
    (or migrated to) the shared pool topic: redeploying their old function
    would re-derive its topic from additional.topic - now SHARED - attaching
    a zombie push subscription to the shared root."""
    from deployments.models import DispatcherDeployment
    integration_type_er = request.getfixturevalue("integration_type_er")
    organization = request.getfixturevalue("organization")

    normal = Integration.objects.create(
        type=integration_type_er,
        name="Normal ER Site",
        owner=organization,
        base_url="https://normal.pamdas.org",
        additional={"broker": "gcp_pubsub", "topic": "destination-old-topic"},
    )
    DispatcherDeployment.objects.create(
        name="dispatcher-normal",
        integration=normal,
        topic_name="destination-old-topic",
        configuration={
            "env_vars": {"GCP_PROJECT_ID": "test-project"},
            "deployment_settings": {"source_code_path": dispatcher_source_release_1},
        },
    )

    migrated = Integration.objects.create(
        type=integration_type_er,
        name="Migrated ER Site",
        owner=organization,
        base_url="https://migrated.pamdas.org",
        additional={
            "broker": "gcp_pubsub",
            "topic": SHARED,
            "pre_migration_topic": "destination-old-topic-2",
            "shared_pool_migrated_at": "2024-01-01T00:00:00+00:00",
        },
    )
    DispatcherDeployment.objects.create(
        name="dispatcher-migrated",
        integration=migrated,
        topic_name="destination-old-topic-2",
        configuration={
            "env_vars": {"GCP_PROJECT_ID": "test-project"},
            "deployment_settings": {"source_code_path": dispatcher_source_release_1},
        },
    )

    mocker.patch("deployments.models.transaction.on_commit", lambda fn: fn())
    mock_deploy_serverless_dispatcher = mocker.MagicMock()
    mocker.patch(
        "deployments.models.deploy_serverless_dispatcher", mock_deploy_serverless_dispatcher
    )

    call_command(
        "dispatchers", "--v2", "--type", "earth_ranger", "--max", "10",
        "--update-source", dispatcher_source_release_2,
    )
    captured = capsys.readouterr()

    normal.refresh_from_db()
    assert normal.dispatcher_by_integration.configuration["deployment_settings"]["source_code_path"] == dispatcher_source_release_2
    assert f"Update triggered for {normal.name}" in captured.out

    migrated.refresh_from_db()
    assert migrated.dispatcher_by_integration.configuration["deployment_settings"]["source_code_path"] == dispatcher_source_release_1
    assert f"Update triggered for {migrated.name}" not in captured.out

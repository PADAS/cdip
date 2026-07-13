import pytest
from google.api_core.exceptions import NotFound

from deployments.models import DispatcherDeployment
from deployments.tasks import delete_serverless_dispatcher


pytestmark = pytest.mark.django_db


@pytest.fixture
def orphaned_deployment(mocker):
    # Stub the auto-deploy hook triggered on creation
    mocker.patch("deployments.models.transaction.on_commit", lambda fn: None)
    return DispatcherDeployment.objects.create(
        name="orphan-dispatcher",
        topic_name="orphan-topic",
        configuration={
            "env_vars": {"GCP_PROJECT_ID": "test-project"},
            "deployment_settings": {"region": "us-central1"},
        },
    )


def test_delete_task_for_orphaned_deployment_tries_function_and_service(
    mocker, orphaned_deployment
):
    """With both integration FKs null the dispatcher kind is unknown, so the
    task must attempt to delete both a Cloud Function and a Cloud Run service.
    """
    mock_delete_function = mocker.patch("deployments.tasks.delete_function")
    mock_delete_service = mocker.patch("deployments.tasks.delete_cloudrun_service")
    mock_delete_topic = mocker.patch("deployments.tasks.delete_topic")
    mock_delete_subscription = mocker.patch("deployments.tasks.delete_subscription")

    delete_serverless_dispatcher(
        deployment_id=str(orphaned_deployment.id), topic="orphan-topic"
    )

    mock_delete_function.assert_called_once_with(
        function_name="orphan-dispatcher",
        configuration=orphaned_deployment.configuration,
    )
    mock_delete_service.assert_called_once_with(
        service_name="orphan-dispatcher",
        configuration=orphaned_deployment.configuration,
    )
    mock_delete_topic.assert_called_once()
    mock_delete_subscription.assert_called_once()
    # The row is removed once GCP resources are gone
    assert not DispatcherDeployment.objects.filter(id=orphaned_deployment.id).exists()


def test_delete_task_for_orphaned_deployment_tolerates_not_found(
    mocker, orphaned_deployment
):
    mock_delete_function = mocker.patch(
        "deployments.tasks.delete_function", side_effect=NotFound("no function")
    )
    mock_delete_service = mocker.patch(
        "deployments.tasks.delete_cloudrun_service",
        side_effect=NotFound("no service"),
    )
    mocker.patch("deployments.tasks.delete_topic")
    mocker.patch("deployments.tasks.delete_subscription")

    delete_serverless_dispatcher(
        deployment_id=str(orphaned_deployment.id), topic="orphan-topic"
    )

    mock_delete_function.assert_called_once()
    mock_delete_service.assert_called_once()
    assert not DispatcherDeployment.objects.filter(id=orphaned_deployment.id).exists()


def test_delete_task_orphan_tries_service_even_if_function_deletion_errors(
    mocker, orphaned_deployment
):
    """A non-NotFound failure in one deletion path must not prevent the other
    attempt; the row is left in ERROR state for retry/investigation.
    """
    mocker.patch(
        "deployments.tasks.delete_function",
        side_effect=Exception("permission denied"),
    )
    mock_delete_service = mocker.patch("deployments.tasks.delete_cloudrun_service")
    mocker.patch("deployments.tasks.delete_topic")
    mocker.patch("deployments.tasks.delete_subscription")
    # The final deployment.delete() re-queues teardown when status is ERROR
    mock_delete_task = mocker.MagicMock()
    mocker.patch("deployments.models.delete_serverless_dispatcher", mock_delete_task)

    delete_serverless_dispatcher(
        deployment_id=str(orphaned_deployment.id), topic="orphan-topic"
    )

    mock_delete_service.assert_called_once()
    orphaned_deployment.refresh_from_db()
    assert orphaned_deployment.status == DispatcherDeployment.Status.ERROR
    assert "permission denied" in orphaned_deployment.status_details


def test_delete_task_skips_topic_deletion_when_no_topic_recorded(mocker):
    """--delete-unused can target rows with a NULL/empty topic_name; the task
    must not try to build a Pub/Sub path from it (e.g. .../topics/None).
    """
    mocker.patch("deployments.models.transaction.on_commit", lambda fn: None)
    mocker.patch("deployments.tasks.delete_function", side_effect=NotFound("x"))
    mocker.patch("deployments.tasks.delete_cloudrun_service", side_effect=NotFound("x"))
    mock_delete_topic = mocker.patch("deployments.tasks.delete_topic")
    mocker.patch("deployments.tasks.delete_subscription")
    deployment = DispatcherDeployment.objects.create(
        name="orphan-dispatcher-no-topic",
        topic_name=None,
        configuration={
            "env_vars": {"GCP_PROJECT_ID": "test-project"},
            "deployment_settings": {"region": "us-central1"},
        },
    )

    delete_serverless_dispatcher(deployment_id=str(deployment.id), topic=None)

    mock_delete_topic.assert_not_called()
    assert not DispatcherDeployment.objects.filter(id=deployment.id).exists()

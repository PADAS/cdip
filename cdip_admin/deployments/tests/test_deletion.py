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
    mocker.patch(
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

    mock_delete_service.assert_called_once()
    assert not DispatcherDeployment.objects.filter(id=orphaned_deployment.id).exists()

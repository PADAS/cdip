import pytest
from django.conf import settings
from django_celery_beat.models import PeriodicTask
from django.test import override_settings
from integrations.models import OutboundIntegrationConfiguration, Integration


pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("legacy_integration_type", [
    ("legacy_integration_type_earthranger"),
    ("legacy_integration_type_smart"),
    ("legacy_integration_type_wpswatch"),
])
@override_settings(GCP_ENVIRONMENT_ENABLED=True)
def test_automatic_dispatcher_deployments_v1(
        mocker, request, organization, legacy_integration_type, mock_get_dispatcher_defaults_from_gcp_secrets
):
    # Mock the task to trigger the dispatcher deployment
    mocked_deployment_task = mocker.MagicMock()
    mocker.patch(
        "deployments.models.deploy_serverless_dispatcher", mocked_deployment_task
    )
    # Mock calls to external services
    mocker.patch("integrations.models.v1.models.get_dispatcher_defaults_from_gcp_secrets", mock_get_dispatcher_defaults_from_gcp_secrets)
    # Patch on_commit to execute the function immediately
    mocker.patch("deployments.models.transaction.on_commit", lambda fn: fn())
    mocker.patch("integrations.models.v1.models.transaction.on_commit", lambda fn: fn())

    integration = OutboundIntegrationConfiguration.objects.create(
        type=request.getfixturevalue(legacy_integration_type),
        name=f"My Reserve",
        owner=organization,
        endpoint=f"https://reserve.domain.org",
        # additional  # Not set, let it be set automatically
    )

    integration.refresh_from_db()
    # Check settings
    assert integration.additional.get("broker") == "gcp_pubsub"
    assert integration.additional.get("topic")  # ramdom name generated
    # Check that a deployment record was created in the DB
    assert integration.dispatcher_by_outbound
    # Check that the task to trigger the dispatcher deployment was created
    mocked_deployment_task.delay.assert_called_once_with(deployment_id=integration.dispatcher_by_outbound.id)


@pytest.mark.parametrize("integration_type", [
    ("integration_type_er"),
    ("integration_type_smart"),
])
@override_settings(GCP_ENVIRONMENT_ENABLED=True)
def test_automatic_dispatcher_deployments_v2(
        mocker, request, organization, integration_type, mock_get_dispatcher_defaults_from_gcp_secrets
):
    # Mock the task to trigger the dispatcher deployment
    mocked_deployment_task = mocker.MagicMock()
    mocker.patch(
        "deployments.models.deploy_serverless_dispatcher", mocked_deployment_task
    )
    # Mock calls to external services
    mocker.patch("integrations.models.v2.models.get_dispatcher_defaults_from_gcp_secrets", mock_get_dispatcher_defaults_from_gcp_secrets)
    # Patch on_commit to execute the function immediately
    mocker.patch("deployments.models.transaction.on_commit", lambda fn: fn())
    mocker.patch("integrations.models.v2.models.transaction.on_commit", lambda fn: fn())

    integration = Integration.objects.create(
        type=request.getfixturevalue(integration_type),
        name=f"My Reserve",
        owner=organization,
        base_url=f"https://reserve.domain.org",
        # additional  # Not set, let it be set automatically
    )

    integration.refresh_from_db()
    # Check settings
    assert integration.additional.get("broker") == "gcp_pubsub"
    assert integration.additional.get("topic")  # ramdom name generated
    # Check that a deployment record was created in the DB
    assert integration.dispatcher_by_integration
    # Check that the task to trigger the dispatcher deployment was created
    mocked_deployment_task.delay.assert_called_once_with(deployment_id=integration.dispatcher_by_integration.id)

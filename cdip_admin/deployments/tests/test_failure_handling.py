import pytest
from google.api_core import exceptions as gcp_exceptions

from deployments.utils import (
    classify_deployment_error,
    FAILURE_REASON_QUOTA_EXHAUSTED,
    FAILURE_REASON_TRANSIENT,
    FAILURE_REASON_CONFIG_ERROR,
    FAILURE_REASON_UNKNOWN,
)


class TestClassifyDeploymentError:
    def test_resource_exhausted_is_quota(self):
        exc = gcp_exceptions.ResourceExhausted("Quota exceeded for cloudrun services")
        assert classify_deployment_error(exc) == FAILURE_REASON_QUOTA_EXHAUSTED

    def test_too_many_requests_is_quota(self):
        exc = gcp_exceptions.TooManyRequests("429")
        assert classify_deployment_error(exc) == FAILURE_REASON_QUOTA_EXHAUSTED

    def test_quota_message_on_plain_exception_is_quota(self):
        # Real-world shape: LRO operation.result() failure surfaces as a plain
        # Exception whose message starts "Operation failed due to insufficient quota."
        exc = Exception(
            "429 Could not create Cloud Run service olaremot-earth-dis-bbb92f66. "
            "Operation failed due to insufficient quota."
        )
        assert classify_deployment_error(exc) == FAILURE_REASON_QUOTA_EXHAUSTED

    def test_invalid_argument_is_config_error(self):
        exc = gcp_exceptions.InvalidArgument("bad service name")
        assert classify_deployment_error(exc) == FAILURE_REASON_CONFIG_ERROR

    def test_permission_denied_is_config_error(self):
        exc = gcp_exceptions.PermissionDenied("missing role")
        assert classify_deployment_error(exc) == FAILURE_REASON_CONFIG_ERROR

    def test_deadline_exceeded_is_transient(self):
        exc = gcp_exceptions.DeadlineExceeded("timed out")
        assert classify_deployment_error(exc) == FAILURE_REASON_TRANSIENT

    def test_service_unavailable_is_transient(self):
        exc = gcp_exceptions.ServiceUnavailable("503")
        assert classify_deployment_error(exc) == FAILURE_REASON_TRANSIENT

    def test_unrecognized_falls_back_to_unknown(self):
        assert classify_deployment_error(RuntimeError("???")) == FAILURE_REASON_UNKNOWN


@pytest.mark.django_db
def test_quota_exhausted_marks_failure_and_cleans_up_topic(
    mocker, organization, integration_type_smart, mock_get_dispatcher_defaults_from_gcp_secrets,
    smart_action_push_events,
):
    """When Cloud Run returns 429, the deployment should:
       - end in ERROR with failure_reason=QUOTA_EXHAUSTED
       - record the full error in last_error
       - delete the topic that was created in this run
       - never reach create_subscription
    """
    from django.test import override_settings
    from integrations.models import Integration
    from deployments.models import DispatcherDeployment

    # Stub the per-integration auto-deploy hook so creating the Integration
    # doesn't synchronously try to deploy. We drive the task explicitly below.
    mocker.patch("deployments.models.transaction.on_commit", lambda fn: None)
    mocker.patch("integrations.models.v2.models.transaction.on_commit", lambda fn: None)
    mocker.patch(
        "integrations.models.v2.models.get_dispatcher_defaults_from_gcp_secrets",
        mock_get_dispatcher_defaults_from_gcp_secrets,
    )

    with override_settings(GCP_ENVIRONMENT_ENABLED=True):
        integration = Integration.objects.create(
            type=integration_type_smart,
            name="Reserve",
            owner=organization,
            base_url="https://reserve.domain.org",
        )

    deployment = integration.dispatcher_by_integration
    assert deployment is not None

    # Patch the GCP-touching helpers used by deploy_serverless_dispatcher.
    create_topic_mock = mocker.patch(
        "deployments.tasks.create_topic", return_value=True
    )
    delete_topic_mock = mocker.patch("deployments.tasks.delete_topic")
    create_subscription_mock = mocker.patch("deployments.tasks.create_subscription")
    quota_error = Exception(
        "429 Could not create Cloud Run service. "
        "Operation failed due to insufficient quota."
    )
    mocker.patch(
        "deployments.tasks.create_or_update_cloud_run_service",
        side_effect=quota_error,
    )

    from deployments.tasks import deploy_serverless_dispatcher
    deploy_serverless_dispatcher(deployment_id=deployment.id)

    deployment.refresh_from_db()
    assert deployment.status == DispatcherDeployment.Status.ERROR
    assert deployment.failure_reason == DispatcherDeployment.FailureReason.QUOTA_EXHAUSTED
    assert "insufficient quota" in deployment.last_error
    assert deployment.attempt_count == 1
    assert deployment.last_attempt_at is not None

    create_topic_mock.assert_called_once()
    delete_topic_mock.assert_called_once()
    create_subscription_mock.assert_not_called()


@pytest.mark.django_db
def test_quota_exhausted_skips_topic_cleanup_when_topic_preexisted(
    mocker, organization, integration_type_smart, mock_get_dispatcher_defaults_from_gcp_secrets,
    smart_action_push_events,
):
    """If the topic already existed (AlreadyExists), we did not create it in
    this run and must not delete it on quota failure — another deployment may
    legitimately own it.
    """
    from django.test import override_settings
    from integrations.models import Integration
    from deployments.models import DispatcherDeployment

    mocker.patch("deployments.models.transaction.on_commit", lambda fn: None)
    mocker.patch("integrations.models.v2.models.transaction.on_commit", lambda fn: None)
    mocker.patch(
        "integrations.models.v2.models.get_dispatcher_defaults_from_gcp_secrets",
        mock_get_dispatcher_defaults_from_gcp_secrets,
    )

    with override_settings(GCP_ENVIRONMENT_ENABLED=True):
        integration = Integration.objects.create(
            type=integration_type_smart,
            name="Reserve",
            owner=organization,
            base_url="https://reserve.domain.org",
        )

    deployment = integration.dispatcher_by_integration

    mocker.patch("deployments.tasks.create_topic", return_value=False)  # already existed
    delete_topic_mock = mocker.patch("deployments.tasks.delete_topic")
    mocker.patch(
        "deployments.tasks.create_or_update_cloud_run_service",
        side_effect=Exception("429 insufficient quota"),
    )
    mocker.patch("deployments.tasks.create_subscription")

    from deployments.tasks import deploy_serverless_dispatcher
    deploy_serverless_dispatcher(deployment_id=deployment.id)

    deployment.refresh_from_db()
    assert deployment.failure_reason == DispatcherDeployment.FailureReason.QUOTA_EXHAUSTED
    delete_topic_mock.assert_not_called()


@pytest.mark.django_db
def test_quota_failure_records_activity_log(
    mocker, organization, integration_type_smart, mock_get_dispatcher_defaults_from_gcp_secrets,
    smart_action_push_events,
):
    """A quota failure should write an ActivityLog tied to the v2 Integration
    so existing health calculations and the activity feed pick it up.
    """
    from django.test import override_settings
    from integrations.models import Integration
    from activity_log.models import ActivityLog

    mocker.patch("deployments.models.transaction.on_commit", lambda fn: None)
    mocker.patch("integrations.models.v2.models.transaction.on_commit", lambda fn: None)
    mocker.patch(
        "integrations.models.v2.models.get_dispatcher_defaults_from_gcp_secrets",
        mock_get_dispatcher_defaults_from_gcp_secrets,
    )

    with override_settings(GCP_ENVIRONMENT_ENABLED=True):
        integration = Integration.objects.create(
            type=integration_type_smart,
            name="Reserve",
            owner=organization,
            base_url="https://reserve.domain.org",
        )

    deployment = integration.dispatcher_by_integration

    mocker.patch("deployments.tasks.create_topic", return_value=True)
    mocker.patch("deployments.tasks.delete_topic")
    mocker.patch("deployments.tasks.create_subscription")
    mocker.patch(
        "deployments.tasks.create_or_update_cloud_run_service",
        side_effect=Exception(
            "429 Could not create Cloud Run service. "
            "Operation failed due to insufficient quota."
        ),
    )

    from deployments.tasks import deploy_serverless_dispatcher
    deploy_serverless_dispatcher(deployment_id=deployment.id)

    logs = ActivityLog.objects.filter(
        integration=integration, origin=ActivityLog.Origin.DISPATCHER
    )
    assert logs.count() == 1
    log = logs.first()
    assert log.log_level == ActivityLog.LogLevels.ERROR
    assert log.log_type == ActivityLog.LogTypes.EVENT
    assert log.value == "dispatcher_quota_exhausted"
    assert "quota" in log.title.lower()
    assert log.details["failure_reason"] == "quota_exhausted"
    assert log.details["attempt_count"] == 1
    assert "insufficient quota" in log.details["error"]


@pytest.mark.django_db
def test_non_quota_failure_records_generic_activity_log(
    mocker, organization, integration_type_smart, mock_get_dispatcher_defaults_from_gcp_secrets,
    smart_action_push_events,
):
    """Non-quota failures still get an ActivityLog, with the generic slug."""
    from django.test import override_settings
    from integrations.models import Integration
    from activity_log.models import ActivityLog

    mocker.patch("deployments.models.transaction.on_commit", lambda fn: None)
    mocker.patch("integrations.models.v2.models.transaction.on_commit", lambda fn: None)
    mocker.patch(
        "integrations.models.v2.models.get_dispatcher_defaults_from_gcp_secrets",
        mock_get_dispatcher_defaults_from_gcp_secrets,
    )

    with override_settings(GCP_ENVIRONMENT_ENABLED=True):
        integration = Integration.objects.create(
            type=integration_type_smart,
            name="Reserve",
            owner=organization,
            base_url="https://reserve.domain.org",
        )

    deployment = integration.dispatcher_by_integration

    mocker.patch("deployments.tasks.create_topic", return_value=True)
    mocker.patch("deployments.tasks.delete_topic")
    mocker.patch("deployments.tasks.create_subscription")
    mocker.patch(
        "deployments.tasks.create_or_update_cloud_run_service",
        side_effect=RuntimeError("something else went wrong"),
    )

    from deployments.tasks import deploy_serverless_dispatcher
    deploy_serverless_dispatcher(deployment_id=deployment.id)

    log = ActivityLog.objects.filter(
        integration=integration, origin=ActivityLog.Origin.DISPATCHER
    ).first()
    assert log is not None
    assert log.value == "dispatcher_deploy_failed"
    assert log.details["failure_reason"] == "unknown"


@pytest.mark.django_db
def test_calculate_integration_status_unhealthy_when_dispatcher_quota_exhausted(
    mocker, organization, integration_type_smart, mock_get_dispatcher_defaults_from_gcp_secrets,
    smart_action_push_events,
):
    """A dispatcher in ERROR/QUOTA_EXHAUSTED should immediately make the
    integration UNHEALTHY, with quota-specific status_details — no need to wait
    for 3 activity-log errors to accumulate.
    """
    from django.test import override_settings
    from integrations.models import Integration
    from integrations.models.v2.models import IntegrationStatus
    from integrations.models.v2.services import calculate_integration_status
    from deployments.models import DispatcherDeployment

    mocker.patch("deployments.models.transaction.on_commit", lambda fn: None)
    mocker.patch("integrations.models.v2.models.transaction.on_commit", lambda fn: None)
    mocker.patch(
        "integrations.models.v2.models.get_dispatcher_defaults_from_gcp_secrets",
        mock_get_dispatcher_defaults_from_gcp_secrets,
    )

    with override_settings(GCP_ENVIRONMENT_ENABLED=True):
        integration = Integration.objects.create(
            type=integration_type_smart,
            name="Reserve",
            owner=organization,
            base_url="https://reserve.domain.org",
        )

    deployment = integration.dispatcher_by_integration
    deployment.status = DispatcherDeployment.Status.ERROR
    deployment.failure_reason = DispatcherDeployment.FailureReason.QUOTA_EXHAUSTED
    deployment.last_error = "429 insufficient quota"
    deployment.save()

    status = calculate_integration_status(integration.id)
    assert status == IntegrationStatus.Status.UNHEALTHY
    integration.status.refresh_from_db()
    assert "quota" in integration.status.status_details.lower()


@pytest.mark.django_db
def test_calculate_integration_status_healthy_when_dispatcher_complete(
    mocker, organization, integration_type_smart, mock_get_dispatcher_defaults_from_gcp_secrets,
    smart_action_push_events,
):
    """When the dispatcher is COMPLETE and there are no error logs, the
    integration is HEALTHY — confirms the new short-circuit doesn't false-positive.
    """
    from django.test import override_settings
    from integrations.models import Integration
    from integrations.models.v2.models import IntegrationStatus
    from integrations.models.v2.services import calculate_integration_status
    from deployments.models import DispatcherDeployment

    mocker.patch("deployments.models.transaction.on_commit", lambda fn: None)
    mocker.patch("integrations.models.v2.models.transaction.on_commit", lambda fn: None)
    mocker.patch(
        "integrations.models.v2.models.get_dispatcher_defaults_from_gcp_secrets",
        mock_get_dispatcher_defaults_from_gcp_secrets,
    )

    with override_settings(GCP_ENVIRONMENT_ENABLED=True):
        integration = Integration.objects.create(
            type=integration_type_smart,
            name="Reserve",
            owner=organization,
            base_url="https://reserve.domain.org",
        )

    deployment = integration.dispatcher_by_integration
    deployment.status = DispatcherDeployment.Status.COMPLETE
    deployment.save()

    assert calculate_integration_status(integration.id) == IntegrationStatus.Status.HEALTHY

import pytest
from integrations.models import IntegrationStatus, Integration
from activity_log.models import ActivityLog
from ..models.v2 import calculate_integration_status


pytestmark = pytest.mark.django_db


def test_calculate_provider_integration_status_healthy(
        provider_lotek_panthera,
        pull_observations_action_started_activity_log,
        pull_observations_action_complete_activity_log  # Successful integration run
):
    calculate_integration_status(integration_id=provider_lotek_panthera.id)
    provider_lotek_panthera.status.refresh_from_db()
    assert provider_lotek_panthera.status.status == IntegrationStatus.Status.HEALTHY


def test_calculate_destination_integration_status_healthy(
        provider_lotek_panthera, destination_movebank,
        pull_observations_action_started_activity_log,
        pull_observations_action_complete_activity_log,  # Successful integration run
        observation_delivery_succeeded_activity_log,  # Successful delivery
        observation_delivery_succeeded_activity_log_2
):
    calculate_integration_status(integration_id=destination_movebank.id)
    destination_movebank.status.refresh_from_db()
    assert destination_movebank.status.status == IntegrationStatus.Status.HEALTHY


def test_calculate_provider_integration_status_unhealthy(
        provider_lotek_panthera,
        pull_observations_action_started_activity_log,
        pull_observations_action_failed_activity_log,
        pull_observations_action_failed_activity_log_2,
        pull_observations_action_failed_activity_log_3
):
    calculate_integration_status(integration_id=provider_lotek_panthera.id)
    provider_lotek_panthera.status.refresh_from_db()
    assert provider_lotek_panthera.status.status == IntegrationStatus.Status.UNHEALTHY


def test_calculate_destination_integration_status_unhealthy(
    provider_lotek_panthera, destination_movebank,
    pull_observations_action_started_activity_log,
    pull_observations_action_complete_activity_log,  # Successful integration run
    observation_delivery_to_movebank_failed_activity_log,
    observation_delivery_to_movebank_failed_activity_log_2,
    observation_delivery_to_movebank_failed_activity_log_3  # Failed delivery three times (default threshold)
):
    calculate_integration_status(integration_id=destination_movebank.id)
    destination_movebank.status.refresh_from_db()
    assert destination_movebank.status.status == IntegrationStatus.Status.UNHEALTHY


def test_calculate_integration_status_disabled(provider_lotek_panthera):
    provider_lotek_panthera.enabled = False
    provider_lotek_panthera.save()
    calculate_integration_status(integration_id=provider_lotek_panthera.id)
    provider_lotek_panthera.status.refresh_from_db()
    assert provider_lotek_panthera.status.status == IntegrationStatus.Status.DISABLED


def test_calculate_provider_integration_status_with_custom_threshold(
        provider_lotek_panthera,
        pull_observations_action_started_activity_log,
        pull_observations_action_failed_activity_log,
        pull_observations_action_failed_activity_log_2  # Two errors (custom threshold=2)
):
    provider_lotek_panthera.health_check_settings.error_count_threshold = 2
    provider_lotek_panthera.health_check_settings.save()
    calculate_integration_status(integration_id=provider_lotek_panthera.id)
    provider_lotek_panthera.status.refresh_from_db()
    assert provider_lotek_panthera.status.status == IntegrationStatus.Status.UNHEALTHY


def test_calculate_destination_integration_status_with_custom_threshold(
        provider_lotek_panthera, destination_movebank,
        pull_observations_action_started_activity_log,
        pull_observations_action_complete_activity_log,  # Successful integration run
        observation_delivery_to_movebank_failed_activity_log  # Single error (custom threshold=2)
):
    destination_movebank.health_check_settings.error_count_threshold = 1
    destination_movebank.health_check_settings.save()
    calculate_integration_status(integration_id=destination_movebank.id)
    destination_movebank.status.refresh_from_db()
    assert destination_movebank.status.status == IntegrationStatus.Status.UNHEALTHY


@pytest.mark.parametrize('enabled', [False, True,])
def test_update_health_status_on_integration_enabled_change(
        request,
        enabled,
        provider_lotek_panthera,
):
    provider_enabled = request.getfixturevalue('enabled')
    provider_lotek_panthera.enabled = provider_enabled
    provider_lotek_panthera.save()
    health_status = provider_lotek_panthera.status.status
    expected_status = IntegrationStatus.Status.HEALTHY if provider_enabled else IntegrationStatus.Status.DISABLED
    assert health_status == expected_status.value


def test_health_status_matches_integration_disabled_on_creation(integration_type_lotek, organization):
    integration = Integration.objects.create(
        type=integration_type_lotek,
        name=f"Lotek Provider Disabled",
        owner=organization,
        base_url=f"api.test.lotek.com",
        enabled=False
    )
    assert integration.status.status == IntegrationStatus.Status.DISABLED.value


def test_health_check_settings_have_retriable_error_threshold(provider_lotek_panthera):
    settings = provider_lotek_panthera.health_check_settings
    assert settings.retriable_error_count_threshold == 30


def _make_retriable_delivery_warning_logs(integration, count, value="observation_delivery_failed"):
    return [
        ActivityLog.objects.create(
            log_level=ActivityLog.LogLevels.WARNING,
            log_type=ActivityLog.LogTypes.EVENT,
            origin=ActivityLog.Origin.DISPATCHER,
            integration=integration,
            value=value,
            title="Error Delivering Observation to 'https://fake-site.pamdas.org'",
            details={"server_response_status": 503},
            is_reversible=False,
        )
        for _ in range(count)
    ]


def test_sustained_retriable_delivery_errors_mark_integration_unhealthy(provider_lotek_panthera):
    provider_lotek_panthera.health_check_settings.retriable_error_count_threshold = 3
    provider_lotek_panthera.health_check_settings.save()
    _make_retriable_delivery_warning_logs(provider_lotek_panthera, count=3)

    calculate_integration_status(integration_id=provider_lotek_panthera.id)

    provider_lotek_panthera.status.refresh_from_db()
    assert provider_lotek_panthera.status.status == IntegrationStatus.Status.UNHEALTHY
    assert provider_lotek_panthera.status.status_details == (
        "Sustained delivery errors - destination may be down or overloaded"
    )


def test_few_retriable_delivery_errors_keep_integration_healthy(provider_lotek_panthera):
    # Below the threshold (default 30), retriable warnings must not alarm
    _make_retriable_delivery_warning_logs(provider_lotek_panthera, count=5)

    calculate_integration_status(integration_id=provider_lotek_panthera.id)

    provider_lotek_panthera.status.refresh_from_db()
    assert provider_lotek_panthera.status.status == IntegrationStatus.Status.HEALTHY


def test_zero_retriable_threshold_disables_sustained_error_check(provider_lotek_panthera):
    # A threshold of 0 must disable the check, not make count() >= 0 always true
    provider_lotek_panthera.health_check_settings.retriable_error_count_threshold = 0
    provider_lotek_panthera.health_check_settings.save()
    _make_retriable_delivery_warning_logs(provider_lotek_panthera, count=5)

    calculate_integration_status(integration_id=provider_lotek_panthera.id)

    provider_lotek_panthera.status.refresh_from_db()
    assert provider_lotek_panthera.status.status == IntegrationStatus.Status.HEALTHY


def test_unrelated_warnings_do_not_count_toward_sustained_errors(provider_lotek_panthera):
    provider_lotek_panthera.health_check_settings.retriable_error_count_threshold = 3
    provider_lotek_panthera.health_check_settings.save()
    _make_retriable_delivery_warning_logs(provider_lotek_panthera, count=3, value="custom_dispatcher_log")

    calculate_integration_status(integration_id=provider_lotek_panthera.id)

    provider_lotek_panthera.status.refresh_from_db()
    assert provider_lotek_panthera.status.status == IntegrationStatus.Status.HEALTHY


def test_error_threshold_takes_precedence_over_warning_threshold(
        provider_lotek_panthera,
        pull_observations_action_started_activity_log,
        pull_observations_action_failed_activity_log,
        pull_observations_action_failed_activity_log_2,
        pull_observations_action_failed_activity_log_3
):
    # When both thresholds are crossed, the ERROR branch runs first and its
    # status_details wins (the elif chain in calculate_integration_status).
    provider_lotek_panthera.health_check_settings.retriable_error_count_threshold = 3
    provider_lotek_panthera.health_check_settings.save()
    _make_retriable_delivery_warning_logs(provider_lotek_panthera, count=3)

    calculate_integration_status(integration_id=provider_lotek_panthera.id)

    provider_lotek_panthera.status.refresh_from_db()
    assert provider_lotek_panthera.status.status == IntegrationStatus.Status.UNHEALTHY
    assert provider_lotek_panthera.status.status_details != (
        "Sustained delivery errors - destination may be down or overloaded"
    )


def test_dispatcher_error_threshold_takes_precedence_over_warning_threshold(
        provider_lotek_panthera, destination_movebank,
        observation_delivery_to_movebank_failed_activity_log,
        observation_delivery_to_movebank_failed_activity_log_2,
        observation_delivery_to_movebank_failed_activity_log_3
):
    # DISPATCHER-origin ERROR logs (the branch directly above the new WARNING
    # branch) must win when both thresholds are crossed.
    destination_movebank.health_check_settings.retriable_error_count_threshold = 3
    destination_movebank.health_check_settings.save()
    _make_retriable_delivery_warning_logs(destination_movebank, count=3)

    calculate_integration_status(integration_id=destination_movebank.id)

    destination_movebank.status.refresh_from_db()
    assert destination_movebank.status.status == IntegrationStatus.Status.UNHEALTHY
    assert destination_movebank.status.status_details == (
        "Errors were detected while pushing data to the destination"
    )


def test_retriable_update_failures_count_toward_sustained_errors(provider_lotek_panthera):
    provider_lotek_panthera.health_check_settings.retriable_error_count_threshold = 4
    provider_lotek_panthera.health_check_settings.save()
    _make_retriable_delivery_warning_logs(provider_lotek_panthera, count=2)
    _make_retriable_delivery_warning_logs(provider_lotek_panthera, count=2, value="observation_update_failed")

    calculate_integration_status(integration_id=provider_lotek_panthera.id)

    provider_lotek_panthera.status.refresh_from_db()
    assert provider_lotek_panthera.status.status == IntegrationStatus.Status.UNHEALTHY

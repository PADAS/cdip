import pytest
from integrations.models import IntegrationStatus
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

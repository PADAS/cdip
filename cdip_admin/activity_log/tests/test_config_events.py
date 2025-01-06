import pytest
import gundi_core.events as gundi_core_events

from integrations.models import IntegrationConfiguration
from ..models import ActivityLog, build_event_from_log


pytestmark = pytest.mark.django_db


def test_build_event_from_log_integration_created(provider_lotek_panthera):
    integration = provider_lotek_panthera
    activity_log = ActivityLog.objects.filter(integration=integration, value="integration_created").first()

    event = build_event_from_log(activity_log)

    assert event
    assert isinstance(event, gundi_core_events.IntegrationCreated)
    assert isinstance(event.payload, gundi_core_events.IntegrationSummary)
    assert str(event.payload.id) == str(integration.id)


def test_build_event_from_log_integration_updated(integration_ats_no_configs):
    integration = integration_ats_no_configs
    integration.name = "New name"
    integration.base_url = "https://new.url.org"
    integration.save()  # This will create an activity log with value="integration_updated"

    activity_log = ActivityLog.objects.filter(integration=integration, value="integration_updated").first()

    event = build_event_from_log(activity_log)

    assert event
    assert isinstance(event, gundi_core_events.IntegrationUpdated)
    assert isinstance(event.payload, gundi_core_events.IntegrationConfigChanges)
    assert str(event.payload.id) == str(integration.id)
    assert event.payload.changes.get("name") == "New name"
    assert event.payload.changes.get("base_url") == "https://new.url.org"


def test_build_event_from_log_integration_deleted(integration_ats_no_configs):
    integration = integration_ats_no_configs
    integration_id = str(integration.id)
    integration.delete()  # This will create an activity log with value="integration_deleted"

    activity_log = ActivityLog.objects.filter(integration=integration, value="integration_deleted").first()

    event = build_event_from_log(activity_log)

    assert event
    assert isinstance(event, gundi_core_events.IntegrationDeleted)
    assert isinstance(event.payload, gundi_core_events.IntegrationDeletionDetails)
    assert str(event.payload.id) == integration_id


def test_build_event_from_log_configuration_created(integration_ats_no_configs, ats_action_pull_observations):
    integration = integration_ats_no_configs
    config_data = {
        "data_endpoint": "http://12.34.56.7/Service1.svc/GetPointsAtsIri/1",
        "transmissions_endpoint": "http://12.34.56.7/Service1.svc/GetAllTransmission/1"
    }
    IntegrationConfiguration.objects.create(
        integration=integration,
        action=ats_action_pull_observations,
        data=config_data,
    )  # This will create an activity log with value="integrationconfiguration_created"
    activity_log = ActivityLog.objects.filter(integration=integration, value="integrationconfiguration_created").first()

    event = build_event_from_log(activity_log)

    assert event
    assert isinstance(event, gundi_core_events.ActionConfigCreated)
    assert isinstance(event.payload, gundi_core_events.IntegrationActionConfiguration)
    assert str(event.payload.integration) == str(integration.id)
    assert event.payload.action.value == ats_action_pull_observations.value
    assert event.payload.data == config_data


def test_build_event_from_log_configuration_updated(provider_ats, ats_action_pull_observations):
    integration = provider_ats
    action_config = integration.configurations_by_integration.get(action=ats_action_pull_observations)
    new_config_data = {
        "data_endpoint": "http://98.76.54.3/Service1.svc/GetPointsAtsIri/2",
        "transmissions_endpoint": "http://98.76.54.3/Service1.svc/GetAllTransmission/2"
    }
    action_config.data = new_config_data
    action_config.save()  # This will create an activity log with value="integrationconfiguration_updated"
    activity_log = ActivityLog.objects.filter(integration=integration, value="integrationconfiguration_updated").first()

    event = build_event_from_log(activity_log)

    assert event
    assert isinstance(event, gundi_core_events.ActionConfigUpdated)
    assert isinstance(event.payload, gundi_core_events.ActionConfigChanges)
    assert str(event.payload.integration_id) == str(integration.id)
    assert str(event.payload.id) == str(action_config.id)
    assert event.payload.alt_id == action_config.action_value
    assert event.payload.changes.get("data") == new_config_data


def test_build_event_from_log_configuration_deleted(provider_ats, ats_action_pull_observations):
    integration = provider_ats
    action_config = integration.configurations_by_integration.get(action=ats_action_pull_observations)
    action_config_id = str(action_config.id)
    action_config.delete()  # This will create an activity log with value="integrationconfiguration_deleted"
    activity_log = ActivityLog.objects.filter(integration=integration, value="integrationconfiguration_deleted").first()

    event = build_event_from_log(activity_log)

    assert event
    assert isinstance(event, gundi_core_events.ActionConfigDeleted)
    assert isinstance(event.payload, gundi_core_events.ActionConfigDeletionDetails)
    assert str(event.payload.integration_id) == str(integration.id)
    assert str(event.payload.id) == action_config_id
    assert event.payload.alt_id == action_config.action_value


@pytest.mark.parametrize(
    "data_change_activity_log",
    [
        "integration_created", "integration_updated", "integration_deleted",
        "integrationconfiguration_created", "integrationconfiguration_updated", "integrationconfiguration_deleted",
    ],
    indirect=["data_change_activity_log"])
def test_publish_events_from_activity_logs(mocker, data_change_activity_log, mock_pubsub_publisher):
    # Test that event are published when certain activity logs are created
    assert mock_pubsub_publisher.delay.called
    assert mock_pubsub_publisher.delay.call_count == 1

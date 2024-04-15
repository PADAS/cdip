import pytest
from sync_integrations.er_smart_sync import ER_SMART_Synchronizer


pytestmark = pytest.mark.django_db


def test_synchronizer_get_events(
        mocker, mock_das_client, mock_smart_client, mock_pubsub_publisher, mock_cloud_storage,
        mock_last_poll, inbound_integration_er, outbound_integration_smart
):
    # Setup ER -> SMART connection
    inbound_integration_er.default_devicegroup.destinations.add(outbound_integration_smart)

    # Mock state
    mocker.patch("sync_integrations.er_smart_sync.get_earthranger_last_poll", mock_last_poll)
    mocker.patch("sync_integrations.er_smart_sync.set_earthranger_last_poll", mocker.MagicMock())

    er_smart_sync = ER_SMART_Synchronizer(
        smart_config=outbound_integration_smart,
        er_config=inbound_integration_er
    )
    # Mock external dependencies
    er_smart_sync.das_client = mock_das_client
    er_smart_sync.smart_client = mock_smart_client
    er_smart_sync.publisher = mock_pubsub_publisher
    er_smart_sync.cloud_storage = mock_cloud_storage

    # Run the synchronizer on events
    er_smart_sync.get_er_events(config=inbound_integration_er)

    # Check that events were fetched from ER
    events = mock_das_client.get_events.return_value
    assert mock_das_client.get_events.called
    # Check that events were sent to routing
    assert mock_pubsub_publisher.publish.called
    assert mock_pubsub_publisher.publish.call_count == len(events)


def test_synchronizer_get_patrols(
        mocker, mock_das_client, mock_smart_client, mock_pubsub_publisher, mock_cloud_storage,
        mock_last_poll, inbound_integration_er, outbound_integration_smart
):
    # Setup ER -> SMART connection
    inbound_integration_er.default_devicegroup.destinations.add(outbound_integration_smart)

    # Mock state
    mocker.patch("sync_integrations.er_smart_sync.get_earthranger_last_poll", mock_last_poll)
    mocker.patch("sync_integrations.er_smart_sync.set_earthranger_last_poll", mocker.MagicMock())

    er_smart_sync = ER_SMART_Synchronizer(
        smart_config=outbound_integration_smart,
        er_config=inbound_integration_er
    )
    # Mock external dependencies
    er_smart_sync.das_client = mock_das_client
    er_smart_sync.smart_client = mock_smart_client
    er_smart_sync.publisher = mock_pubsub_publisher
    er_smart_sync.cloud_storage = mock_cloud_storage

    # Run the synchronizer on patrols
    er_smart_sync.get_er_patrols(config=inbound_integration_er)

    # Check that patrols were fetched from ER
    patrols = mock_das_client.get_patrols.return_value
    assert mock_das_client.get_patrols.called
    # Check that patrols were sent to routing
    assert mock_pubsub_publisher.publish.called
    assert mock_pubsub_publisher.publish.call_count == len(patrols)

import pytest

from sync_integrations import tasks

pytestmark = pytest.mark.django_db


@pytest.fixture
def synchronizer(mocker):
    sync = mocker.MagicMock()
    mocker.patch("sync_integrations.tasks.build_synchronizer", return_value=sync)
    return sync


def _ids(outbound_integration_smart, inbound_integration_er):
    return dict(
        smart_integration_id=str(outbound_integration_smart.id),
        er_integration_id=str(inbound_integration_er.id),
    )


def test_sync_er_smart_datamodels_runs_both_datamodel_syncs(
    synchronizer, outbound_integration_smart, inbound_integration_er
):
    tasks.sync_er_smart_datamodels(**_ids(outbound_integration_smart, inbound_integration_er))
    tasks.build_synchronizer.assert_called_once_with(
        smart_config=outbound_integration_smart, er_config=inbound_integration_er
    )
    synchronizer.synchronize_datamodel.assert_called_once_with()
    synchronizer.sync_patrol_datamodel.assert_called_once_with()


def test_sync_er_events_runs_event_sync(synchronizer, outbound_integration_smart, inbound_integration_er):
    tasks.sync_er_events(**_ids(outbound_integration_smart, inbound_integration_er))
    synchronizer.synchronize_er_events.assert_called_once_with()


def test_sync_er_patrols_runs_patrol_sync(synchronizer, outbound_integration_smart, inbound_integration_er):
    tasks.sync_er_patrols(**_ids(outbound_integration_smart, inbound_integration_er))
    synchronizer.synchronize_er_patrols.assert_called_once_with()


def test_sync_task_logs_and_returns_when_integration_missing(
    synchronizer, outbound_integration_smart, caplog
):
    tasks.sync_er_events(
        smart_integration_id=str(outbound_integration_smart.id),
        er_integration_id="00000000-0000-0000-0000-000000000000",
    )
    tasks.build_synchronizer.assert_not_called()
    assert "does not exist" in caplog.text


def test_synchronize_smart_datamodels_uses_er_integration_from_additional(
    synchronizer, outbound_integration_smart, inbound_integration_er
):
    outbound_integration_smart.additional = {"er_integration_id": str(inbound_integration_er.id)}
    outbound_integration_smart.save()
    tasks.synchronize_smart_datamodels(str(outbound_integration_smart.id))
    tasks.build_synchronizer.assert_called_once_with(
        smart_config=outbound_integration_smart, er_config=inbound_integration_er
    )
    synchronizer.synchronize_datamodel.assert_called_once_with()


@pytest.mark.parametrize("er_integration_id", [None, "not-a-uuid", "00000000-0000-0000-0000-000000000000"])
def test_synchronize_smart_datamodels_without_valid_er_integration_logs_and_returns(
    synchronizer, outbound_integration_smart, caplog, er_integration_id
):
    outbound_integration_smart.additional = (
        {"er_integration_id": er_integration_id} if er_integration_id is not None else {}
    )
    outbound_integration_smart.save()
    tasks.synchronize_smart_datamodels(str(outbound_integration_smart.id))
    tasks.build_synchronizer.assert_not_called()
    assert "er_integration_id" in caplog.text

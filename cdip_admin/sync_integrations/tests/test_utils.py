import pytest

from sync_integrations.utils import maintain_smart_integration

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("additional", [{}, {"ca_uuids": None}, {"ca_uuids": []}])
def test_maintain_smart_integration_without_ca_uuids_warns_and_returns(
    mocker, outbound_integration_smart, caplog, additional
):
    smart_client = mocker.patch("sync_integrations.utils.SmartClient")
    outbound_integration_smart.additional = additional
    outbound_integration_smart.save()

    maintain_smart_integration(integration_id=str(outbound_integration_smart.id), force=True)

    smart_client.return_value.get_data_model.assert_not_called()
    assert "no ca_uuids" in caplog.text


def test_maintain_smart_integration_downloads_each_ca(mocker, outbound_integration_smart):
    smart_client = mocker.patch("sync_integrations.utils.SmartClient").return_value
    smart_client.list_configurable_datamodels.return_value = []
    outbound_integration_smart.additional = {"ca_uuids": ["ca-1", "ca-2"]}
    outbound_integration_smart.save()

    maintain_smart_integration(integration_id=str(outbound_integration_smart.id), force=True)

    assert [c.kwargs["ca_uuid"] for c in smart_client.get_data_model.call_args_list] == ["ca-1", "ca-2"]
    outbound_integration_smart.refresh_from_db()
    assert outbound_integration_smart.additional["configurable_models_lists"] == {"ca-1": [], "ca-2": []}

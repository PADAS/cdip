import pytest

from organizations.models import Organization
from ..models import (
    OutboundIntegrationType,
    OutboundIntegrationConfiguration,
    Integration,
    IntegrationAction,
    IntegrationConfiguration,
    Device,
    Source
)
from ..tasks import recreate_and_send_movebank_permissions_csv_file, update_mb_permissions_for_group
from ..utils import build_mb_tag_id


@pytest.mark.django_db
def test_movebank_permissions_set_is_updated_on_device_addition_v1(
        mocker,
        setup_movebank_test_devices_sources
):
    mocked_csv_task = mocker.MagicMock()
    mocker.patch(
        "integrations.models.v1.models.recreate_and_send_movebank_permissions_csv_file", mocked_csv_task
    )
    # Patch on_commit to execute the function immediately
    mocker.patch('integrations.models.v1.models.transaction.on_commit', lambda fn: fn())


    # Get test configs / devices
    ii = setup_movebank_test_devices_sources["v1"].get("inbound")
    oi = setup_movebank_test_devices_sources["v1"].get("config")

    # get test device
    d1 = setup_movebank_test_devices_sources["v1"].get("device")

    # Get device_group (for v1 test)
    dg = setup_movebank_test_devices_sources["v1"].get("device_group")

    # add "additional" blob to oi
    oi.additional["permissions"]["permissions"] = [
        {
            "tag_id": build_mb_tag_id(d1, "v1"),
            "username": "victorg"
        }
    ]
    oi.save()
    oi.refresh_from_db()

    # Add Movebank destination in the default group
    ii.default_devicegroup.destinations.add(oi)

    # Only 1 permissions dict registered
    assert len(oi.additional["permissions"].get("permissions", [])) == 1

    # Add new device to device_group
    new_device = Device.objects.create(external_id="device-123", inbound_configuration=ii)

    # Refresh again for getting new devices
    oi.refresh_from_db()

    # Now we have 2
    assert new_device
    assert len(oi.additional["permissions"].get("permissions", [])) == 2
    # The new permission set is related to newly added device
    assert oi.additional["permissions"].get("permissions", [])[1].get("tag_id") == build_mb_tag_id(new_device, "v1")

    # Check that the task to send data to Movebank was called (after device adding)
    assert mocked_csv_task.delay.called


@pytest.mark.django_db
def test_movebank_permissions_set_is_updated_on_device_addition_v2(
        mocker,
        setup_movebank_test_devices_sources
):
    mocked_csv_task = mocker.MagicMock()
    mocker.patch(
        "integrations.models.v2.models.recreate_and_send_movebank_permissions_csv_file", mocked_csv_task
    )
    # Patch on_commit to execute the function immediately
    mocker.patch('integrations.models.v1.models.transaction.on_commit', lambda fn: fn())

    # Get test configs / devices
    integration_config = setup_movebank_test_devices_sources["v2"].get("config")

    # get test devices
    d2 = setup_movebank_test_devices_sources["v2"].get("device")

    # add "data" blob to integration_config
    integration_config.data["permissions"] = [
        {
            "tag_id": build_mb_tag_id(d2, "v2"),
            "username": "victorg"
        }
    ]
    integration_config.save()
    integration_config.refresh_from_db()

    # Only 1 permissions dict registered
    assert len(integration_config.data.get("permissions", [])) == 1

    # Add new source
    source = Source.objects.create(
        external_id=f"device-456",
        integration=d2.integration
    )

    # Refresh again for getting new devices
    integration_config.refresh_from_db()

    # Now we have 2
    assert len(integration_config.data.get("permissions", [])) == 2
    # The new permission set is related to newly added source
    assert integration_config.data.get("permissions", [])[1].get("tag_id") == build_mb_tag_id(source, "v2")

    # Check that the task to send data to Movebank was called (after source adding)
    assert mocked_csv_task.delay.called


@pytest.mark.django_db
def test_movebank_permissions_file_upload_task_creates_permissions_json(
        mocker,
        mock_movebank_client_class,
        caplog,
        setup_movebank_test_devices_sources
):
    mocker.patch("integrations.tasks.MovebankClient", mock_movebank_client_class)

    # Get test configs / devices
    oi = setup_movebank_test_devices_sources["v1"].get("config")
    integration_config = setup_movebank_test_devices_sources["v2"].get("config")

    d1 = setup_movebank_test_devices_sources["v1"].get("device")
    d2 = setup_movebank_test_devices_sources["v2"].get("device")

    # No "permissions" dict set yet
    assert "permissions" not in oi.additional.get("permissions").keys()
    assert "permissions" not in integration_config.data.keys()

    recreate_and_send_movebank_permissions_csv_file()

    # Refresh from db to get updates made
    oi.refresh_from_db()
    integration_config.refresh_from_db()

    # "permissions" dict set
    assert "permissions" in oi.additional.get("permissions").keys()
    assert "permissions" in integration_config.data.keys()

    v1_tags = [tag.get("tag_id") for tag in oi.additional["permissions"]["permissions"]]
    v2_tags = [tag.get("tag_id") for tag in integration_config.data["permissions"]]

    # Check devices in permissions dict
    tag_id_1 = f"{d1.inbound_configuration.type.slug}."\
               f"{d1.external_id}."\
               f"{str(d1.inbound_configuration.id)}"

    tag_id_2 = f"{d2.integration.type.value}." \
               f"{d2.external_id}." \
               f"{str(d2.integration_id)}"

    assert tag_id_1 in v1_tags
    assert tag_id_2 in v2_tags

    # Check that the tag data was NOT sent to Movebank
    assert not mock_movebank_client_class.called


@pytest.mark.django_db
def test_movebank_permissions_file_upload_task_no_configs(mocker, caplog, mock_movebank_client_class):
    mocker.patch("integrations.tasks.MovebankClient", mock_movebank_client_class)
    recreate_and_send_movebank_permissions_csv_file()
    # Check that the tag data was NOT sent to Movebank
    assert not mock_movebank_client_class.called
    assert not mock_movebank_client_class.return_value.post_permissions.called
    log_to_test = ' -- No configs available to send --'
    assert log_to_test in [r.message for r in caplog.records]


@pytest.mark.django_db
def test_movebank_permissions_file_upload_task_with_configs(
        mocker,
        caplog,
        setup_movebank_test_data,
        mock_movebank_client_class
):
    movebank_client_params = {
        "base_url": "https://www.test-movebank.com",
        "password": "test_pwd",
        "username": "test_user"
    }

    mocker.patch("integrations.tasks.MovebankClient", mock_movebank_client_class)

    # v1 configs
    OutboundIntegrationConfiguration.objects.create(
        type=OutboundIntegrationType.objects.first(),
        owner=Organization.objects.first(),
        additional={
            "broker": "gcp_pubsub",
            "topic": "destination-v2-gundi-load-testing-legacy",
            "permissions": {
                "permissions": [
                    {
                        "tag_id": "awt.test-device-orfxingdskmp.2b029799-a5a1-4794-a1bd-ac12b85f9249",
                        "username": "test1"
                    }
                ],
                "study": "gundi"
            }
        }
    )

    # v2 configs
    IntegrationConfiguration.objects.create(
        integration=Integration.objects.first(),
        action=IntegrationAction.objects.first(),
        data={
            "study": "gundi",
            "permissions": [
                {
                    "tag_id": "awt.test-device-orfxingdskmp.2b029799-a5a1-4794-a1bd-ac12b85f9249",
                    "username": "test2"
                }
            ]
        }
    )

    recreate_and_send_movebank_permissions_csv_file(**movebank_client_params)

    # Check that the tag data was sent to Movebank
    assert mock_movebank_client_class.called
    assert mock_movebank_client_class.return_value.post_permissions.called

    logs_to_test = [
        ' -- Got 2 user/tag rows (v1: 1, v2: 1) --',
        ' -- CSV temp file created successfully. --',
        ' -- CSV file uploaded to Movebank successfully --'
    ]

    logs = [r.message for r in caplog.records]

    for log in logs_to_test:
        assert log in logs


@pytest.mark.django_db
def test_movebank_permissions_file_upload_task_with_bad_configs(
        mocker,
        caplog,
        setup_movebank_test_data,
        mock_movebank_client_class
):
    movebank_client_params = {
        "base_url": "https://www.test-movebank.com",
        "password": "test_pwd",
        "username": "test_user"
    }

    mocker.patch("integrations.tasks.MovebankClient", mock_movebank_client_class)

    # v1
    OutboundIntegrationConfiguration.objects.create(
        type=OutboundIntegrationType.objects.first(),
        owner=Organization.objects.first(),
        name="Wrong config",
        additional={
            "broker": "gcp_pubsub",
            "topic": "destination-v2-gundi-load-testing-legacy",
            "permissions": {
                "permissions": [
                    {
                        "tag": "awt.test-device-orfxingdskmp.2b029799-a5a1-4794-a1bd-ac12b85f9249",
                        "user": "test1"
                    }
                ],
                "study": "gundi"
            }
        }
    )
    OutboundIntegrationConfiguration.objects.create(
        type=OutboundIntegrationType.objects.first(),
        owner=Organization.objects.first(),
        name="Good config",
        additional={
            "broker": "gcp_pubsub",
            "topic": "destination-v2-gundi-load-testing-legacy",
            "permissions": {
                "permissions": [
                    {
                        "tag_id": "awt.test-device-orfxingdskmp.2b029799-a5a1-4794-a1bd-ac12b85f9249",
                        "username": "test1"
                    }
                ],
                "study": "gundi"
            }
        }
    )

    # v2
    IntegrationConfiguration.objects.create(
        integration=Integration.objects.first(),
        action=IntegrationAction.objects.first(),
        data={
            "study": "gundi",
            "permissions": [
                {
                    "tag": "awt.test-device-orfxingdskmp.2b029799-a5a1-4794-a1bd-ac12b85f9249",  # Bad config
                    "user": "test2"
                }
            ]
        }
    )
    IntegrationConfiguration.objects.create(
        integration=Integration.objects.first(),
        action=IntegrationAction.objects.first(),
        data={
            "study": "gundi",
            "permissions": [
                {
                    "tag_id": "awt.test-device-orfxingdskmp.2b029799-a5a1-4794-a1bd-ac12b85f9249",  # Good config
                    "username": "test2"
                }
            ]
        }
    )

    recreate_and_send_movebank_permissions_csv_file(**movebank_client_params)

    # Check that the tag data was sent to Movebank
    assert mock_movebank_client_class.called
    assert mock_movebank_client_class.return_value.post_permissions.called

    logs_to_test = [
        'Error parsing MBPermissionsActionConfig model (v1)',  # exception message when bad config appears
        'Error parsing MBPermissionsActionConfig model (v2)',  # exception message when bad config appears
        ' -- Got 2 user/tag rows (v1: 1, v2: 1) --',
        ' -- CSV temp file created successfully. --',
        ' -- CSV file uploaded to Movebank successfully --'
    ]

    logs = [r.message for r in caplog.records]

    for log in logs_to_test:
        assert log in logs

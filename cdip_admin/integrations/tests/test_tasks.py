import pytest

from organizations.models import Organization
from ..models import (
    Device,
    Source,
    OutboundIntegrationType,
    OutboundIntegrationConfiguration,
    Integration,
    IntegrationAction,
    IntegrationConfiguration
)
from ..tasks import recreate_and_send_movebank_permissions_csv_file


@pytest.mark.django_db
def test_movebank_permissions_file_upload_task_creates_permissions_json(
        mocker,
        mock_movebank_client_class,
        caplog,
        setup_movebank_test_devices_sources
):
    mocker.patch("integrations.tasks.MovebankClient", mock_movebank_client_class)

    # Get configs / devices
    oi = OutboundIntegrationConfiguration.objects.get(
        id=setup_movebank_test_devices_sources["v1"].get("config_id")
    )
    integration_config = IntegrationConfiguration.objects.get(
        id=setup_movebank_test_devices_sources["v2"].get("config_id")
    )

    d1 = Device.objects.get(
        id=setup_movebank_test_devices_sources["v1"].get("device_id")
    )
    d2 = Source.objects.get(
        id=setup_movebank_test_devices_sources["v2"].get("device_id")
    )

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

    # Check that the tag data was sent to Movebank
    assert mock_movebank_client_class.called
    assert mock_movebank_client_class.return_value.post_permissions.called


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

import pytest
from pytest_httpx import HTTPXMock

from organizations.models import Organization
from ..models import (
    OutboundIntegrationType,
    OutboundIntegrationConfiguration,
    Integration,
    IntegrationAction,
    IntegrationConfiguration
)
from ..tasks import recreate_and_send_movebank_permissions_csv_file


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

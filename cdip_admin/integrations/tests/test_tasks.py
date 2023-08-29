import pytest
from pytest_httpx import HTTPXMock

from organizations.models import Organization
from ..models import (
    OutboundIntegrationType,
    OutboundIntegrationConfiguration,
    IntegrationType, Integration,
    IntegrationAction,
    IntegrationConfiguration
)
from ..tasks import recreate_and_send_movebank_permissions_csv_file


@pytest.mark.django_db
def test_movebank_permissions_file_upload_task_no_configs(caplog):
    recreate_and_send_movebank_permissions_csv_file()
    log_to_test = ' -- No configs available to send --'
    assert log_to_test in [r.message for r in caplog.records]


@pytest.mark.django_db
def test_movebank_permissions_file_upload_task_with_configs(caplog, httpx_mock: HTTPXMock):
    movebank_client_params = {
        "base_url": "https://www.test-movebank.com",
        "password": "test_pwd",
        "username": "test_user"
    }
    httpx_mock.add_response(method="POST")

    # Add values to DB
    # v1
    Organization.objects.create(name="Test Org")

    OutboundIntegrationType.objects.create(name="Movebank", slug="movebank")
    OutboundIntegrationConfiguration.objects.create(
        type=OutboundIntegrationType.objects.first(),
        owner=Organization.objects.first(),
        additional={
          "broker": "gcp_pubsub",
          "permissions": {
            "permissions": [
              {
                "tag_id": "awt.test-device-orfxingdskmp.2b029799-a5a1-4794-a1bd-ac12b85f9249",
                "username": "test1"
              },
              {
                "tag_id": "awt.test-device-ptyjhlnkfqgb.2b029799-a5a1-4794-a1bd-ac12b85f9249",
                "username": "test1"
              },
              {
                "tag_id": "awt.test-device-qjlvtwzrynfm.2b029799-a5a1-4794-a1bd-ac12b85f9249",
                "username": "test1"
              },
              {
                "tag_id": "awt.test-device-jqlvtwzrynfm.2b029798-a5a5-4799-a1bd-ac12b85f9279",
                "username": "test1"
              }
            ],
            "study": "gundi"
          },
          "topic": "destination-v2-gundi-load-testing-legacy"
        }
    )

    # v2
    IntegrationType.objects.create(name="Movebank", value="movebank")
    Integration.objects.create(
        type=IntegrationType.objects.first(),
        owner=Organization.objects.first(),
    )
    IntegrationAction.objects.create(
        type=IntegrationAction.ActionTypes.AUTHENTICATION,
        name="Permissions",
        value="permissions",
        integration_type=IntegrationType.objects.first(),
    )
    IntegrationConfiguration.objects.create(
        integration=Integration.objects.first(),
        action=IntegrationAction.objects.first(),
        data={
            "study": "gundi",
            "permissions": [
                {
                    "tag_id": "awt.test-device-orfxingdskmp.2b029799-a5a1-4794-a1bd-ac12b85f9249",
                    "username": "test2"
                },
                {
                    "tag_id": "awt.test-device-ptyjhlnkfqgb.2b029799-a5a1-4794-a1bd-ac12b85f9249",
                    "username": "test2"
                },
                {
                    "tag_id": "awt.test-device-qjlvtwzrynfm.2b029799-a5a1-4794-a1bd-ac12b85f9249",
                    "username": "test2"
                },
                {
                    "tag_id": "awt.test-device-jqlvtwzrynfm.2b029798-a5a5-4799-a1bd-ac12b85f9279",
                    "username": "test2"
                }
            ]
        }
    )

    recreate_and_send_movebank_permissions_csv_file(**movebank_client_params)

    logs_to_test = [
        ' -- Got 8 user/tag rows (v1: 4, v2: 4) --',
        ' -- CSV temp file created successfully. --',
        ' -- CSV file uploaded to Movebank successfully --'
    ]

    logs = [r.message for r in caplog.records]

    for log in logs_to_test:
        assert log in logs


@pytest.mark.django_db
def test_movebank_permissions_file_upload_task_with_bad_configs(caplog, httpx_mock: HTTPXMock):
    movebank_client_params = {
        "base_url": "https://www.test-movebank.com",
        "password": "test_pwd",
        "username": "test_user"
    }
    httpx_mock.add_response(method="POST")

    # Add values to DB
    # v1
    Organization.objects.create(name="Test Org")

    OutboundIntegrationType.objects.create(name="Movebank", slug="movebank")
    OutboundIntegrationConfiguration.objects.create(
        type=OutboundIntegrationType.objects.first(),
        owner=Organization.objects.first(),
        name="Wrong config",
        additional={
          "broker": "gcp_pubsub",
          "permissions": {
            "permissions": [
              {
                "tag": "awt.test-device-orfxingdskmp.2b029799-a5a1-4794-a1bd-ac12b85f9249",
                "user": "test1"
              }
            ],
            "study": "gundi"
          },
          "topic": "destination-v2-gundi-load-testing-legacy"
        }
    )
    OutboundIntegrationConfiguration.objects.create(
        type=OutboundIntegrationType.objects.first(),
        owner=Organization.objects.first(),
        name="Good config",
        additional={
            "broker": "gcp_pubsub",
            "permissions": {
                "permissions": [
                    {
                        "tag_id": "awt.test-device-orfxingdskmp.2b029799-a5a1-4794-a1bd-ac12b85f9249",
                        "username": "test1"
                    }
                ],
                "study": "gundi"
            },
            "topic": "destination-v2-gundi-load-testing-legacy"
        }
    )

    # v2
    IntegrationType.objects.create(name="Movebank", value="movebank")
    Integration.objects.create(
        type=IntegrationType.objects.first(),
        owner=Organization.objects.first(),
    )
    IntegrationAction.objects.create(
        type=IntegrationAction.ActionTypes.AUTHENTICATION,
        name="Permissions",
        value="permissions",
        integration_type=IntegrationType.objects.first(),
    )
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

    logs_to_test = [
        'Error parsing MBPermissionsActionConfig model (v1)',  # exception message when bad config appears
        'Error parsing MBPermissionsActionConfig model (v2)',
        ' -- Got 2 user/tag rows (v1: 1, v2: 1) --',
        ' -- CSV temp file created successfully. --',
        ' -- CSV file uploaded to Movebank successfully --'
    ]

    logs = [r.message for r in caplog.records]

    for log in logs_to_test:
        assert log in logs

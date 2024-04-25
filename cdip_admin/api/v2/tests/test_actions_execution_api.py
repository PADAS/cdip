import pytest
from django.urls import reverse
from urllib.parse import urljoin
from rest_framework import status

from conftest import org_viewer_user

pytestmark = pytest.mark.django_db


def _test_execute_action(
        api_client, mocker, requests_mock,
        user, integration, action, action_response, expected_response,
        run_in_background=False, config_overrides=None
):
    mocker.patch("integrations.models.v2.models.google.auth.transport.requests.Request", mocker.MagicMock())
    mocker.patch("integrations.models.v2.models.google.oauth2.id_token.fetch_id_token", mocker.MagicMock(return_value="fake_id_token"))
    integration_service_url = integration.type.service_url
    actions_execute_url = urljoin(integration_service_url, "/v1/actions/execute")
    requests_mock.post(actions_execute_url, json=action_response, status_code=status.HTTP_200_OK)
    api_url = reverse("actions-execute", kwargs={"integration_pk": integration.id, "value": action.value})
    request_data = {}
    if config_overrides:
        request_data["configurations"] = config_overrides
    if run_in_background:
        request_data["run_in_background"] = True
    api_client.force_authenticate(user)

    response = api_client.post(
        api_url,
        data=request_data,
        format='json'
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == expected_response


def _test_cannot_execute_action(
        api_client, mocker, requests_mock,
        user, integration, action,
        run_in_background=False, config_overrides=None
):
    mocker.patch("integrations.models.v2.models.google.auth.transport.requests.Request", mocker.MagicMock())
    mocker.patch("integrations.models.v2.models.google.oauth2.id_token.fetch_id_token", mocker.MagicMock(return_value="fake_id_token"))
    integration_service_url = integration.type.service_url
    actions_execute_url = urljoin(integration_service_url, "/v1/actions/execute")
    requests_mock.post(actions_execute_url, status_code=status.HTTP_403_FORBIDDEN)
    api_url = reverse("actions-execute", kwargs={"integration_pk": integration.id, "value": action.value})
    request_data = {}
    if config_overrides:
        request_data["configurations"] = config_overrides
    if run_in_background:
        request_data["run_in_background"] = True
    api_client.force_authenticate(user)

    response = api_client.post(
        api_url,
        data=request_data,
        format='json'
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_execute_action_as_superuser(
        api_client, mocker, requests_mock, superuser, organization,
        cellstop_integration, cellstop_action_fetch_samples, cellstop_fetch_samples_response
):
    _test_execute_action(
        mocker=mocker,
        api_client=api_client,
        requests_mock=requests_mock,
        user=superuser,
        integration=cellstop_integration,
        action=cellstop_action_fetch_samples,
        action_response=cellstop_fetch_samples_response,
        expected_response=cellstop_fetch_samples_response
    )


def test_execute_action_as_org_admin(
        api_client, mocker, requests_mock, org_admin_user, organization,
        cellstop_integration, cellstop_action_auth, cellstop_action_auth_response
):
    _test_execute_action(
        mocker=mocker,
        api_client=api_client,
        requests_mock=requests_mock,
        user=org_admin_user,
        integration=cellstop_integration,
        action=cellstop_action_auth,
        action_response=cellstop_action_auth_response,
        expected_response=cellstop_action_auth_response
    )


def test_cannot_execute_action_as_org_viewer(
        api_client, mocker, requests_mock, org_viewer_user, organization,
        cellstop_integration, cellstop_action_auth, cellstop_action_auth_response
):
    _test_cannot_execute_action(
        mocker=mocker,
        api_client=api_client,
        requests_mock=requests_mock,
        user=org_viewer_user,
        integration=cellstop_integration,
        action=cellstop_action_auth
    )

import pytest
from django.urls import reverse
from urllib.parse import urljoin
from rest_framework import status

from conftest import org_viewer_user

pytestmark = pytest.mark.django_db


def _test_execute_action(
        api_client, mocker, requests_mock,
        user, integration, action, action_response, expected_response,
        run_in_background=False, config_overrides=None, triggered_by=None,
        expected_triggered_by="manual",
):
    mocker.patch("integrations.models.v2.models.google.auth.transport.requests.Request", mocker.MagicMock())
    mocker.patch("integrations.models.v2.models.google.oauth2.id_token.fetch_id_token", mocker.MagicMock(return_value="fake_id_token"))
    integration_service_url = integration.type.service_url
    actions_execute_url = urljoin(integration_service_url, "/v1/actions/execute")
    gcp_request_mock = requests_mock.post(actions_execute_url, json=action_response, status_code=status.HTTP_200_OK)
    api_url = reverse("actions-execute", kwargs={"integration_pk": integration.id, "value": action.value})
    request_data = {}
    if config_overrides:
        request_data["config_overrides"] = config_overrides
    if run_in_background:
        request_data["run_in_background"] = True
    if triggered_by:
        request_data["triggered_by"] = triggered_by
    api_client.force_authenticate(user)

    response = api_client.post(
        api_url,
        data=request_data,
        format='json'
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == expected_response
    if config_overrides:
        assert gcp_request_mock.last_request.json().get("config_overrides") == config_overrides
    # The portal forwards how the run was initiated; direct API calls default
    # to "manual" so the action runner stays strict (GUNDI-5400).
    assert gcp_request_mock.last_request.json().get("triggered_by") == expected_triggered_by


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


@pytest.mark.parametrize("user", [
    ("superuser"),
    ("org_admin_user"),
])
def test_execute_action_with_config_overrides(
        request, api_client, mocker, requests_mock, user, organization,
        cellstop_integration, cellstop_action_auth, cellstop_action_auth_response
):
    user = request.getfixturevalue(user)
    _test_execute_action(
        mocker=mocker,
        api_client=api_client,
        requests_mock=requests_mock,
        user=user,
        integration=cellstop_integration,
        action=cellstop_action_auth,
        action_response=cellstop_action_auth_response,
        expected_response=cellstop_action_auth_response,
        config_overrides={"username": "test_user", "password": "test_password"}  # pragma: allowlist secret
    )


def test_execute_reference_action_as_superuser(
        api_client, mocker, requests_mock, superuser, organization,
        cellstop_integration, cellstop_action_list_tag_names, cellstop_list_tag_names_response
):
    # RFC ask 2: reference-type actions are not gated by an is_executable flag
    # or an action-type check in the proxy; the same role rules that apply to
    # other action types apply here.
    mocker.patch("integrations.models.v2.models.google.auth.transport.requests.Request", mocker.MagicMock())
    mocker.patch("integrations.models.v2.models.google.oauth2.id_token.fetch_id_token", mocker.MagicMock(return_value="fake_id_token"))
    integration_service_url = cellstop_integration.type.service_url
    actions_execute_url = urljoin(integration_service_url, "/v1/actions/execute")
    gcp_request_mock = requests_mock.post(
        actions_execute_url, json=cellstop_list_tag_names_response, status_code=status.HTTP_200_OK
    )
    api_url = reverse(
        "actions-execute",
        kwargs={"integration_pk": cellstop_integration.id, "value": cellstop_action_list_tag_names.value},
    )
    config_overrides = {"tag_type": "vessel"}
    api_client.force_authenticate(superuser)

    response = api_client.post(api_url, data={"config_overrides": config_overrides}, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == cellstop_list_tag_names_response
    sent_payload = gcp_request_mock.last_request.json()
    assert sent_payload["integration_id"] == str(cellstop_integration.id)
    assert sent_payload["action_id"] == "list_tag_names"
    assert sent_payload["config_overrides"] == config_overrides


def test_execute_reference_action_as_org_admin(
        api_client, mocker, requests_mock, org_admin_user, organization,
        cellstop_integration, cellstop_action_list_tag_names, cellstop_list_tag_names_response
):
    mocker.patch("integrations.models.v2.models.google.auth.transport.requests.Request", mocker.MagicMock())
    mocker.patch("integrations.models.v2.models.google.oauth2.id_token.fetch_id_token", mocker.MagicMock(return_value="fake_id_token"))
    integration_service_url = cellstop_integration.type.service_url
    actions_execute_url = urljoin(integration_service_url, "/v1/actions/execute")
    gcp_request_mock = requests_mock.post(
        actions_execute_url, json=cellstop_list_tag_names_response, status_code=status.HTTP_200_OK
    )
    api_url = reverse(
        "actions-execute",
        kwargs={"integration_pk": cellstop_integration.id, "value": cellstop_action_list_tag_names.value},
    )
    api_client.force_authenticate(org_admin_user)

    response = api_client.post(api_url, data={}, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == cellstop_list_tag_names_response
    sent_payload = gcp_request_mock.last_request.json()
    assert sent_payload["integration_id"] == str(cellstop_integration.id)
    assert sent_payload["action_id"] == "list_tag_names"


def test_cannot_execute_reference_action_as_org_viewer(
        api_client, mocker, requests_mock, org_viewer_user, organization,
        cellstop_integration, cellstop_action_list_tag_names
):
    _test_cannot_execute_action(
        mocker=mocker,
        api_client=api_client,
        requests_mock=requests_mock,
        user=org_viewer_user,
        integration=cellstop_integration,
        action=cellstop_action_list_tag_names,
    )


def test_execute_action_forwards_explicit_triggered_by(
        api_client, mocker, requests_mock, superuser, organization,
        cellstop_integration, cellstop_action_auth, cellstop_action_auth_response
):
    # A caller may override the default and declare the run automated; the
    # portal forwards it verbatim to the action runner.
    _test_execute_action(
        mocker=mocker,
        api_client=api_client,
        requests_mock=requests_mock,
        user=superuser,
        integration=cellstop_integration,
        action=cellstop_action_auth,
        action_response=cellstop_action_auth_response,
        expected_response=cellstop_action_auth_response,
        triggered_by="auto",
        expected_triggered_by="auto",
    )


def _ephemeral_url(integration_type, action_value):
    from django.urls import reverse
    return reverse(
        "integration-types-execute-reference-action",
        kwargs={"value": integration_type.value, "action_value": action_value},
    )


def _mock_runner(mocker, requests_mock, integration_type, response_body=None, status_code=status.HTTP_200_OK):
    mocker.patch(
        "integrations.models.v2.models.google.auth.transport.requests.Request",
        mocker.MagicMock(),
    )
    mocker.patch(
        "integrations.models.v2.models.google.oauth2.id_token.fetch_id_token",
        mocker.MagicMock(return_value="fake_id_token"),
    )
    actions_execute_url = urljoin(integration_type.service_url, "/v1/actions/execute")
    return requests_mock.post(
        actions_execute_url, json=response_body or {}, status_code=status_code,
    )


def _ephemeral_body(organization, base_url="https://sandbox.example.com", token="ephemeral-token-abc"):
    return {
        "owner": str(organization.id),
        "base_url": base_url,
        "configurations": [
            {"action_value": "auth", "data": {"username": "user@example.com", "password": token}},
        ],
        "config_overrides": {"tag_type": "vessel"},
    }


def test_ephemeral_execute_as_superuser_forwards_draft_state(
        api_client, mocker, requests_mock, superuser, organization,
        integration_type_cellstop, cellstop_action_list_tag_names, cellstop_list_tag_names_response,
):
    gcp_mock = _mock_runner(
        mocker, requests_mock, integration_type_cellstop, cellstop_list_tag_names_response,
    )
    api_client.force_authenticate(superuser)
    body = _ephemeral_body(organization)

    response = api_client.post(
        _ephemeral_url(integration_type_cellstop, cellstop_action_list_tag_names.value),
        data=body, format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == cellstop_list_tag_names_response
    sent = gcp_mock.last_request.json()
    assert sent["integration_id"] is None
    assert sent["action_id"] == "list_tag_names"
    assert sent["run_in_background"] is False
    assert sent["config_overrides"] == {"tag_type": "vessel"}
    integration_state = sent["integration_state"]
    assert integration_state["type_value"] == "cellstop"
    assert integration_state["base_url"] == "https://sandbox.example.com"
    assert integration_state["configurations"] == [
        {"action_value": "auth", "data": {"username": "user@example.com", "password": "ephemeral-token-abc"}},
    ]


def test_ephemeral_execute_as_org_admin_of_owner(
        api_client, mocker, requests_mock, org_admin_user, organization,
        integration_type_cellstop, cellstop_action_list_tag_names, cellstop_list_tag_names_response,
):
    _mock_runner(
        mocker, requests_mock, integration_type_cellstop, cellstop_list_tag_names_response,
    )
    api_client.force_authenticate(org_admin_user)

    response = api_client.post(
        _ephemeral_url(integration_type_cellstop, cellstop_action_list_tag_names.value),
        data=_ephemeral_body(organization), format="json",
    )

    assert response.status_code == status.HTTP_200_OK


def test_ephemeral_execute_rejects_non_member_org_admin(
        api_client, mocker, requests_mock, org_admin_user_2, organization,
        integration_type_cellstop, cellstop_action_list_tag_names,
):
    _mock_runner(mocker, requests_mock, integration_type_cellstop)
    api_client.force_authenticate(org_admin_user_2)

    response = api_client.post(
        _ephemeral_url(integration_type_cellstop, cellstop_action_list_tag_names.value),
        data=_ephemeral_body(organization), format="json",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_ephemeral_execute_rejects_org_viewer(
        api_client, mocker, requests_mock, org_viewer_user, organization,
        integration_type_cellstop, cellstop_action_list_tag_names,
):
    _mock_runner(mocker, requests_mock, integration_type_cellstop)
    api_client.force_authenticate(org_viewer_user)

    response = api_client.post(
        _ephemeral_url(integration_type_cellstop, cellstop_action_list_tag_names.value),
        data=_ephemeral_body(organization), format="json",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_ephemeral_execute_rejects_non_reference_action(
        api_client, mocker, requests_mock, superuser, organization,
        integration_type_cellstop, cellstop_action_auth,
):
    gcp_mock = _mock_runner(mocker, requests_mock, integration_type_cellstop)
    api_client.force_authenticate(superuser)

    response = api_client.post(
        _ephemeral_url(integration_type_cellstop, cellstop_action_auth.value),
        data=_ephemeral_body(organization), format="json",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert not gcp_mock.called


def test_ephemeral_execute_unknown_action_returns_404(
        api_client, mocker, requests_mock, superuser, organization,
        integration_type_cellstop,
):
    _mock_runner(mocker, requests_mock, integration_type_cellstop)
    api_client.force_authenticate(superuser)

    response = api_client.post(
        _ephemeral_url(integration_type_cellstop, "nonexistent_action"),
        data=_ephemeral_body(organization), format="json",
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_ephemeral_execute_creates_no_activity_log(
        api_client, mocker, requests_mock, superuser, organization,
        integration_type_cellstop, cellstop_action_list_tag_names, cellstop_list_tag_names_response,
):
    from activity_log.models import ActivityLog
    _mock_runner(
        mocker, requests_mock, integration_type_cellstop, cellstop_list_tag_names_response,
    )
    api_client.force_authenticate(superuser)
    starting_count = ActivityLog.objects.count()

    response = api_client.post(
        _ephemeral_url(integration_type_cellstop, cellstop_action_list_tag_names.value),
        data=_ephemeral_body(organization), format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert ActivityLog.objects.count() == starting_count


def test_ephemeral_execute_type_without_service_url_returns_502(
        api_client, mocker, requests_mock, superuser, organization,
        integration_type_cellstop, cellstop_action_list_tag_names,
):
    integration_type_cellstop.service_url = ""
    integration_type_cellstop.save()
    api_client.force_authenticate(superuser)

    response = api_client.post(
        _ephemeral_url(integration_type_cellstop, cellstop_action_list_tag_names.value),
        data=_ephemeral_body(organization), format="json",
    )

    assert response.status_code == status.HTTP_502_BAD_GATEWAY


def test_ephemeral_execute_runner_timeout_returns_502(
        api_client, mocker, requests_mock, superuser, organization,
        integration_type_cellstop, cellstop_action_list_tag_names,
):
    # A hung/unreachable runner must surface as a clean 502 (so the portal
    # falls back to plain text), not a 500 from an unhandled RequestException.
    import requests as requests_lib
    mocker.patch(
        "integrations.models.v2.models.google.auth.transport.requests.Request",
        mocker.MagicMock(),
    )
    mocker.patch(
        "integrations.models.v2.models.google.oauth2.id_token.fetch_id_token",
        mocker.MagicMock(return_value="fake_id_token"),
    )
    actions_execute_url = urljoin(integration_type_cellstop.service_url, "/v1/actions/execute")
    requests_mock.post(actions_execute_url, exc=requests_lib.exceptions.ConnectTimeout)
    api_client.force_authenticate(superuser)

    response = api_client.post(
        _ephemeral_url(integration_type_cellstop, cellstop_action_list_tag_names.value),
        data=_ephemeral_body(organization), format="json",
    )

    assert response.status_code == status.HTTP_502_BAD_GATEWAY


def test_ephemeral_execute_non_json_response_returns_502(
        api_client, mocker, requests_mock, superuser, organization,
        integration_type_cellstop, cellstop_action_list_tag_names,
):
    # A 200 with a non-JSON body (e.g. HTML from a broken proxy) must degrade
    # to 502 rather than escape as an uncaught JSONDecodeError → 500.
    mocker.patch(
        "integrations.models.v2.models.google.auth.transport.requests.Request",
        mocker.MagicMock(),
    )
    mocker.patch(
        "integrations.models.v2.models.google.oauth2.id_token.fetch_id_token",
        mocker.MagicMock(return_value="fake_id_token"),
    )
    actions_execute_url = urljoin(integration_type_cellstop.service_url, "/v1/actions/execute")
    requests_mock.post(actions_execute_url, text="<html>oops</html>", status_code=200)
    api_client.force_authenticate(superuser)

    response = api_client.post(
        _ephemeral_url(integration_type_cellstop, cellstop_action_list_tag_names.value),
        data=_ephemeral_body(organization), format="json",
    )

    assert response.status_code == status.HTTP_502_BAD_GATEWAY


def test_ephemeral_execute_auth_failure_returns_502(
        api_client, mocker, requests_mock, superuser, organization,
        integration_type_cellstop, cellstop_action_list_tag_names,
):
    # A GCP metadata / auth-service outage during id_token fetch must degrade
    # to 502, not bubble up as an unhandled GoogleAuthError → 500.
    from google.auth.exceptions import RefreshError
    mocker.patch(
        "integrations.models.v2.models.google.auth.transport.requests.Request",
        mocker.MagicMock(),
    )
    mocker.patch(
        "integrations.models.v2.models.google.oauth2.id_token.fetch_id_token",
        mocker.MagicMock(side_effect=RefreshError("metadata unreachable")),
    )
    api_client.force_authenticate(superuser)

    response = api_client.post(
        _ephemeral_url(integration_type_cellstop, cellstop_action_list_tag_names.value),
        data=_ephemeral_body(organization), format="json",
    )

    assert response.status_code == status.HTTP_502_BAD_GATEWAY


def test_ephemeral_execute_missing_owner_is_400(
        api_client, mocker, requests_mock, superuser, organization,
        integration_type_cellstop, cellstop_action_list_tag_names,
):
    _mock_runner(mocker, requests_mock, integration_type_cellstop)
    api_client.force_authenticate(superuser)
    body = _ephemeral_body(organization)
    body.pop("owner")

    response = api_client.post(
        _ephemeral_url(integration_type_cellstop, cellstop_action_list_tag_names.value),
        data=body, format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.parametrize("owner_value", [
    "not-a-uuid",                             # bad UUID string
    123,                                      # integer — .replace() on it raises AttributeError
    True,                                     # bool
    ["a", "b"],                               # list
    {"nested": "dict"},                       # dict
])
def test_ephemeral_execute_malformed_owner_is_403(
        api_client, mocker, requests_mock, org_admin_user, organization,
        integration_type_cellstop, cellstop_action_list_tag_names, owner_value,
):
    # A malformed `owner` (bad UUID, non-string, non-scalar) must be rejected
    # by the permission check as 403 (not resolvable to an org the caller
    # belongs to), not crash as 500. `uuid.UUID(non-string)` raises
    # AttributeError, not just ValueError/TypeError — every truthy non-string
    # value must survive the guard.
    _mock_runner(mocker, requests_mock, integration_type_cellstop)
    api_client.force_authenticate(org_admin_user)
    body = _ephemeral_body(organization)
    body["owner"] = owner_value

    response = api_client.post(
        _ephemeral_url(integration_type_cellstop, cellstop_action_list_tag_names.value),
        data=body, format="json",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_ephemeral_execute_non_dict_body_is_403(
        api_client, mocker, requests_mock, org_admin_user,
        integration_type_cellstop, cellstop_action_list_tag_names,
):
    # A JSON array body would make `request.data.get('owner')` raise
    # AttributeError from the permission layer. Guard against that too.
    _mock_runner(mocker, requests_mock, integration_type_cellstop)
    api_client.force_authenticate(org_admin_user)

    response = api_client.post(
        _ephemeral_url(integration_type_cellstop, cellstop_action_list_tag_names.value),
        data=["not", "a", "dict"], format="json",
    )

    assert response.status_code in (
        status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN,
    )


@pytest.mark.parametrize("field,bad_value", [
    ("config_overrides", "not-a-dict"),
    ("config_overrides", ["a", "b"]),
    ("config_overrides", 42),
])
def test_ephemeral_execute_non_dict_config_overrides_is_400(
        api_client, mocker, requests_mock, superuser, organization,
        integration_type_cellstop, cellstop_action_list_tag_names, field, bad_value,
):
    # A non-dict config_overrides used to leak through the serializer as
    # JSONField and blow up as 502 from the runner-side pydantic dict
    # rejection. DictField makes it a clean 400 with the field name.
    _mock_runner(mocker, requests_mock, integration_type_cellstop)
    api_client.force_authenticate(superuser)
    body = _ephemeral_body(organization)
    body[field] = bad_value

    response = api_client.post(
        _ephemeral_url(integration_type_cellstop, cellstop_action_list_tag_names.value),
        data=body, format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert field in response.json()

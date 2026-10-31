import pytest
import respx
from django.urls import reverse

from conftest import setup_account_profile_mapping
from core.enums import RoleChoices
from integrations.models import OutboundIntegrationConfiguration


pytestmark = pytest.mark.django_db

SMART_SERVER_BASE = "https://test2.fakesmartconnect.com/server"
CONFIGURED_CA_UUID = "73eeb82d-64b1-4f8b-8ed4-9d80ac427204"
OTHER_CA_UUID = "0d5c4f5e-7b0a-4c39-9a8e-2f1f6f0f2a11"


def conservation_area(ca_uuid, label):
    return {"uuid": ca_uuid, "label": label, "status": "ACTIVE", "revision": 1}


@pytest.fixture
def smart_config(outbound_integration_smart):
    outbound_integration_smart.endpoint = SMART_SERVER_BASE
    outbound_integration_smart.login = "smart-user"
    outbound_integration_smart.password = "smart-password"  # pragma: allowlist secret
    outbound_integration_smart.additional.update({"version": "7.5", "ca_uuids": [CONFIGURED_CA_UUID]})
    outbound_integration_smart.save()
    return outbound_integration_smart


@pytest.fixture
def smart_server():
    with respx.mock(base_url=SMART_SERVER_BASE, assert_all_called=False) as router:
        router.get("/connect/home", name="landing_page").respond(200, html="<html></html>")
        router.post("/j_security_check", name="login").respond(302, headers={"location": "/server/connect/home"})
        router.get("/api/info", name="api_info").respond(200, json={"build-version": "7.5.7"})
        router.get("/api/conservationarea", name="conservation_areas").respond(
            200, json=[conservation_area(CONFIGURED_CA_UUID, "Curicaca [CUR]")]
        )
        yield router


def post_connection_test(client, user, config, **data):
    client.force_login(user.user)
    return client.post(
        reverse("outbound_test_smart_connection", kwargs={"configuration_id": config.id}),
        data=data,
        HTTP_X_USERINFO=user.user_info,
    )


def test_smart_connection_test_succeeds(client, global_admin_user, smart_config, smart_server):
    response = post_connection_test(client, global_admin_user, smart_config)

    assert response.status_code == 200
    result = response.json()
    assert result["ok"] is True
    assert result["normalized_endpoint"] == SMART_SERVER_BASE
    assert result["endpoint_was_normalized"] is False
    assert result["configured_version"] == "7.5"
    assert result["checks"]["api_info"]["server"] == {"build-version": "7.5.7"}
    assert result["checks"]["conservation_areas"]["configured"] == [
        {"uuid": CONFIGURED_CA_UUID, "found": True, "label": "Curicaca [CUR]"}
    ]
    assert smart_server["login"].calls.last.request.content == (
        b"j_username=smart-user&j_password=smart-password"  # pragma: allowlist secret
    )


def test_smart_connection_test_normalizes_unsaved_web_ui_endpoint(client, global_admin_user, smart_config, smart_server):
    web_ui_endpoint = f"{SMART_SERVER_BASE}/connect/home"

    response = post_connection_test(client, global_admin_user, smart_config, endpoint=web_ui_endpoint)

    result = response.json()
    assert result["ok"] is True
    assert result["endpoint"] == web_ui_endpoint
    assert result["normalized_endpoint"] == SMART_SERVER_BASE
    assert result["endpoint_was_normalized"] is True


def test_smart_connection_test_reports_html_instead_of_json(client, global_admin_user, smart_config, smart_server):
    smart_server["api_info"].respond(200, html="<html>SMART Connect</html>")

    response = post_connection_test(client, global_admin_user, smart_config)

    result = response.json()
    assert result["ok"] is False
    assert result["checks"]["api_info"]["ok"] is False
    assert "Expected JSON" in result["checks"]["api_info"]["error"]
    assert "conservation_areas" not in result["checks"]


def test_smart_connection_test_reports_unauthorized(client, global_admin_user, smart_config, smart_server):
    smart_server["api_info"].respond(401)

    response = post_connection_test(client, global_admin_user, smart_config)

    result = response.json()
    assert result["ok"] is False
    assert result["checks"]["api_info"]["status"] == 401
    assert "Not authorized" in result["checks"]["api_info"]["error"]


def test_smart_connection_test_reports_unreachable_landing_page(client, global_admin_user, smart_config, smart_server):
    smart_server["landing_page"].respond(503)

    response = post_connection_test(client, global_admin_user, smart_config)

    result = response.json()
    assert result["ok"] is False
    assert result["checks"]["login"]["ok"] is False
    assert "api_info" not in result["checks"]


def test_smart_connection_test_reports_missing_conservation_area(client, global_admin_user, smart_config, smart_server):
    smart_server["conservation_areas"].respond(200, json=[conservation_area(OTHER_CA_UUID, "Elsewhere [ELS]")])

    response = post_connection_test(client, global_admin_user, smart_config)

    result = response.json()
    assert result["ok"] is False
    assert result["checks"]["conservation_areas"]["configured"] == [
        {"uuid": CONFIGURED_CA_UUID, "found": False, "label": None}
    ]
    assert result["checks"]["conservation_areas"]["available"] == [
        {"uuid": OTHER_CA_UUID, "label": "Elsewhere [ELS]"}
    ]


def test_smart_connection_test_rejects_non_smart_configuration(
        client, global_admin_user, organization, legacy_integration_type_wpswatch
):
    config = OutboundIntegrationConfiguration.objects.create(
        type=legacy_integration_type_wpswatch,
        name="WPS Watch Site",
        owner=organization,
        endpoint="https://wps.example.org",
    )

    response = post_connection_test(client, global_admin_user, config)

    assert response.status_code == 404


def test_smart_connection_test_allows_admin_of_owning_organization(
        client, organization_member_user, organization, smart_config, smart_server
):
    setup_account_profile_mapping({(organization_member_user.user, organization, RoleChoices.ADMIN)})

    response = post_connection_test(client, organization_member_user, smart_config)

    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_smart_connection_test_rejects_member_of_other_organization_before_any_request(
        client, organization_member_user, other_organization, smart_config, smart_server
):
    setup_account_profile_mapping({(organization_member_user.user, other_organization, RoleChoices.ADMIN)})
    attacker_endpoint = "https://attacker.example.org/server"

    response = post_connection_test(client, organization_member_user, smart_config, endpoint=attacker_endpoint)

    assert response.status_code == 403
    assert smart_server.calls.call_count == 0

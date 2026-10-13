from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from integrations.models import Device, DeviceGroup
from sync_integrations.management.commands.er_smart_sync_preflight import (
    summarize_dry_run,
    sync_pairs,
)
from sync_integrations.tasks import er_integrations_for

pytestmark = pytest.mark.django_db

@pytest.fixture
def device_group(organization, outbound_integration_smart):
    group = DeviceGroup.objects.create(name="smart group", owner=organization)
    group.destinations.add(outbound_integration_smart)
    return group


def test_er_integration_found_via_default_device_group(
    outbound_integration_smart, inbound_integration_er, device_group
):
    inbound_integration_er.default_devicegroup = device_group
    inbound_integration_er.save()

    assert list(er_integrations_for(outbound_integration_smart)) == [inbound_integration_er]


def test_er_integration_found_via_device_membership(
    outbound_integration_smart, inbound_integration_er, device_group
):
    device = Device.objects.create(external_id="collar-1", inbound_configuration=inbound_integration_er)
    device_group.devices.add(device)

    assert list(er_integrations_for(outbound_integration_smart)) == [inbound_integration_er]


def test_disabled_er_integration_is_not_a_pair(
    outbound_integration_smart, inbound_integration_er, device_group
):
    inbound_integration_er.default_devicegroup = device_group
    inbound_integration_er.enabled = False
    inbound_integration_er.save()

    assert list(er_integrations_for(outbound_integration_smart)) == []
    assert sync_pairs() == []


def test_summarize_dry_run_flags_error_codes_and_long_values():
    results = [
        {"event_type": "clean", "errors": [], "warnings": [{"code": "schema_transform"}], "hardcoded_choices": []},
        {"event_type": "already", "errors": [{"code": "version_validation"}], "hardcoded_choices": []},
        {"event_type": "broken", "errors": [{"code": "schema_parse"}], "hardcoded_choices": []},
        {
            "event_type": "long",
            "errors": [],
            "hardcoded_choices": [{"choices": [{"value": "x" * 101}, {"value": "short"}]}],
        },
    ]

    summary = summarize_dry_run(results, max_value_length=100)

    assert summary["evaluated"] == 4
    assert summary["already_v2"] == 1
    assert summary["problems"] == {
        "broken": {"errors": ["schema_parse"], "long_values": []},
        "long": {"errors": [], "long_values": ["x" * 101]},
    }


@pytest.fixture
def pair(outbound_integration_smart, inbound_integration_er, device_group):
    inbound_integration_er.default_devicegroup = device_group
    inbound_integration_er.endpoint = "https://site.pamdas.org"
    inbound_integration_er.token = "er-token"  # pragma: allowlist secret
    inbound_integration_er.save()
    return outbound_integration_smart, inbound_integration_er


SITE = "https://site.pamdas.org"


def _site(requests_mock, version, dry_run_results=None):
    requests_mock.get(f"{SITE}/api/v1.0/status", json={"data": {"version": version}})
    return requests_mock.post(
        f"{SITE}/api/v2.0/activity/eventtypes/migrate/", json={"data": dry_run_results or []}
    )


def test_command_passes_on_recent_site(requests_mock, pair):
    _site(requests_mock, "2.147.0")
    out = StringIO()

    call_command("er_smart_sync_preflight", stdout=out)

    assert "ER 2.147.0: OK" in out.getvalue()
    assert "0 failure(s)" in out.getvalue()
    assert requests_mock.last_request.headers["Authorization"] == "Bearer er-token"


def test_command_fails_on_old_site(requests_mock, pair):
    _site(requests_mock, "2.140.0")

    with pytest.raises(CommandError, match="1 preflight failure"):
        call_command("er_smart_sync_preflight", stdout=StringIO())


def test_command_dry_run_reports_problem_types(requests_mock, pair):
    migrate = _site(
        requests_mock,
        "2.147.0",
        [
            {"event_type": "ok", "errors": [], "hardcoded_choices": []},
            {"event_type": "bad", "errors": [{"code": "schema_parse"}], "hardcoded_choices": []},
        ],
    )
    out = StringIO()

    with pytest.raises(CommandError, match="1 preflight failure"):
        call_command("er_smart_sync_preflight", "--migrate-dry-run", stdout=out)

    assert migrate.last_request.json() == {"dry_run": True, "event_types": []}
    assert "2 v1 types evaluated, 0 already v2, 1 with problems" in out.getvalue()
    assert "bad: errors=schema_parse" in out.getvalue()


def test_command_uses_password_grant_without_token(requests_mock, pair):
    _, er = pair
    er.token = ""
    er.login = "er-user"
    er.password = "er-pass"  # pragma: allowlist secret
    er.save()
    token = requests_mock.post(f"{SITE}/oauth2/token", json={"access_token": "granted"})
    _site(requests_mock, "2.147.0")

    call_command("er_smart_sync_preflight", stdout=StringIO())

    assert token.last_request.text.startswith("grant_type=password")
    assert requests_mock.last_request.headers["Authorization"] == "Bearer granted"


def test_command_reports_unreachable_site_and_fails(requests_mock, pair):
    requests_mock.get(f"{SITE}/api/v1.0/status", exc=ConnectionError("refused"))

    with pytest.raises(CommandError):
        call_command("er_smart_sync_preflight", stdout=StringIO())

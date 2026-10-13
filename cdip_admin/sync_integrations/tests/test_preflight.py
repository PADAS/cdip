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

PREFLIGHT = "sync_integrations.management.commands.er_smart_sync_preflight"


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


def _client(mocker, version, dry_run_results=None):
    client = mocker.MagicMock()
    client._get.return_value = {"version": version}
    client._post.return_value = dry_run_results or []
    client._api_root.return_value = "https://site.pamdas.org/api/v2.0"
    return mocker.patch(f"{PREFLIGHT}.ERClient", return_value=client).return_value


def test_command_passes_on_recent_site(mocker, pair):
    _client(mocker, "2.147.0")
    out = StringIO()

    call_command("er_smart_sync_preflight", stdout=out)

    assert "ER 2.147.0: OK" in out.getvalue()
    assert "0 failure(s)" in out.getvalue()


def test_command_fails_on_old_site(mocker, pair):
    _client(mocker, "2.140.0")

    with pytest.raises(CommandError, match="1 preflight failure"):
        call_command("er_smart_sync_preflight", stdout=StringIO())


def test_command_dry_run_reports_problem_types(mocker, pair):
    client = _client(
        mocker,
        "2.147.0",
        [
            {"event_type": "ok", "errors": [], "hardcoded_choices": []},
            {"event_type": "bad", "errors": [{"code": "schema_parse"}], "hardcoded_choices": []},
        ],
    )
    out = StringIO()

    with pytest.raises(CommandError, match="1 preflight failure"):
        call_command("er_smart_sync_preflight", "--migrate-dry-run", stdout=out)

    client._post.assert_called_once_with(
        path="activity/eventtypes/migrate/",
        payload={"dry_run": True, "event_types": []},
        base_url="https://site.pamdas.org/api/v2.0",
    )
    assert "2 v1 types evaluated, 0 already v2, 1 with problems" in out.getvalue()
    assert "bad: errors=schema_parse" in out.getvalue()


def test_command_reports_unreachable_site_and_fails(mocker, pair):
    client = _client(mocker, "2.147.0")
    client._get.side_effect = ConnectionError("refused")

    with pytest.raises(CommandError):
        call_command("er_smart_sync_preflight", stdout=StringIO())

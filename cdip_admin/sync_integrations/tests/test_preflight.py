from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from integrations.models import Device, DeviceGroup
from sync_integrations.management.commands.er_smart_sync_preflight import (
    summarize_dry_run,
    sync_pairs,
    version_tuple,
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


CA = "273807b3-2c53-42fd-beac-704f25b30721"


def test_summarize_dry_run_flags_error_codes_and_long_values():
    results = [
        {"event_type": f"{CA}_clean", "errors": [], "warnings": [{"code": "schema_transform"}], "hardcoded_choices": []},
        {"event_type": f"{CA}_already", "errors": [{"code": "version_validation"}], "hardcoded_choices": []},
        {"event_type": f"{CA}_broken", "errors": [{"code": "schema_parse"}], "hardcoded_choices": []},
        {
            "event_type": f"{CA}_long",
            "errors": [],
            "hardcoded_choices": [{"choices": [{"value": "x" * 101}, {"value": "short"}]}],
        },
        {"event_type": "rhino_sighting_rep", "errors": [{"code": "schema_transform"}], "hardcoded_choices": []},
    ]

    summary = summarize_dry_run(results, max_value_length=100)

    assert summary["evaluated"] == 5
    assert summary["already_v2"] == 1
    assert summary["problems"] == {
        f"{CA}_broken": {"errors": ["schema_parse"], "long_values": []},
        f"{CA}_long": {"errors": [], "long_values": ["x" * 101]},
    }
    # Hand-made v1 types are reported but never sent to the migrate endpoint.
    assert summary["other_problems"] == {"rhino_sighting_rep": {"errors": ["schema_transform"], "long_values": []}}


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
            {"event_type": f"{CA}_ok", "errors": [], "hardcoded_choices": []},
            {"event_type": f"{CA}_bad", "errors": [{"code": "schema_parse"}], "hardcoded_choices": []},
            {"event_type": "handmade", "errors": [{"code": "schema_transform"}], "hardcoded_choices": []},
            {
                "event_type": f"{CA}_long",
                "errors": [],
                "hardcoded_choices": [{"choices": [{"value": "k" * 120}]}],
            },
        ],
    )
    out = StringIO()

    with pytest.raises(CommandError, match="2 preflight failure"):
        call_command("er_smart_sync_preflight", "--migrate-dry-run", "--show-values", stdout=out)

    assert migrate.last_request.json() == {"dry_run": True, "event_types": []}
    text = out.getvalue()
    assert "4 v1 types evaluated, 0 already v2, 2 SMART-derived with problems, 1 other v1 types" in text
    assert f"{CA}_bad: errors=schema_parse" in text
    assert "(other) handmade: errors=schema_transform" in text
    assert "1 distinct over-long choice value(s):" in text
    assert "[120] " + "k" * 120 in text


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


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("release-2.148.1-a15e403", (2, 148, 1)),
        ("2.146.1", (2, 146, 1)),
        ("v2.130.0", (2, 130, 0)),
        ("", ()),
    ],
)
def test_version_tuple_reads_the_dotted_number_only(raw, expected):
    assert version_tuple(raw) == expected


def test_command_treats_release_prefixed_old_version_as_low(requests_mock, pair):
    _site(requests_mock, "release-2.140.0-abc123")

    with pytest.raises(CommandError, match="1 preflight failure"):
        call_command("er_smart_sync_preflight", stdout=StringIO())


def test_command_reports_paused_pair_without_checking_it(requests_mock, pair):
    smart, _ = pair
    smart.additional = {"er_smart_sync_paused": True}
    smart.save()
    out = StringIO()

    call_command("er_smart_sync_preflight", "--migrate-dry-run", stdout=out)

    assert "paused (additional.er_smart_sync_paused)" in out.getvalue()
    assert "1 paused, 0 site(s) checked, 0 failure(s)" in out.getvalue()
    assert requests_mock.call_count == 0

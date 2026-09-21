import json
import uuid
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from activity_log.models import ActivityLog
from integrations.models import (
    IntegrationAction, IntegrationConfiguration, Integration, Route, RouteProvider, RouteDestination,
)


pytestmark = pytest.mark.django_db


def test_call_set_action_configs_command_with_integration_id(
    er_destination_without_show_permissions_config, er_action_show_permissions
):
    integration_id = str(er_destination_without_show_permissions_config.id)
    config_json = '{"include_subjects_from_subgroups_in_parent":true}'

    call_command(
        "set_action_configs",
        "--integration", str(integration_id),
        "--action", "show_permissions",
        "--data", config_json
    )

    new_config = er_destination_without_show_permissions_config.configurations.filter(
        integration=er_destination_without_show_permissions_config,
        action=er_action_show_permissions
    ).first()
    assert new_config is not None
    assert new_config.data == json.loads(config_json)


def test_repair_integration_configurations_with_integration_id(
    er_destination_without_show_permissions_config, er_action_show_permissions,
):
    integration = er_destination_without_show_permissions_config
    assert not integration.configurations.filter(action=er_action_show_permissions).exists()

    call_command(
        "repair_integration_configurations",
        "--integration", str(integration.id),
    )

    new_config = integration.configurations.filter(action=er_action_show_permissions).first()
    assert new_config is not None
    assert new_config.data == {}


def test_repair_integration_configurations_with_integration_type(
    er_destination_without_show_permissions_config, er_action_show_permissions,
):
    integration = er_destination_without_show_permissions_config
    assert not integration.configurations.filter(action=er_action_show_permissions).exists()

    call_command(
        "repair_integration_configurations",
        "--integration-type", "earth_ranger",
    )

    assert integration.configurations.filter(action=er_action_show_permissions).exists()


def test_repair_integration_configurations_excludes_reference_actions(
    er_destination_without_show_permissions_config, er_action_show_permissions,
    integration_type_er,
):
    # Reference actions have no per-integration configuration (see
    # Integration.create_missing_configurations), so the repair command
    # shouldn't report or count them as "missing" — that would forever show
    # up in dry-run/live output even though no row would ever be created.
    integration = er_destination_without_show_permissions_config
    reference_action = IntegrationAction.objects.create(
        integration_type=integration_type_er,
        type=IntegrationAction.ActionTypes.REFERENCE,
        name="Reference Lookup",
        value="reference_lookup",
    )

    out = StringIO()
    call_command(
        "repair_integration_configurations",
        "--integration", str(integration.id),
        stdout=out,
    )

    output = out.getvalue()
    assert "reference_lookup" not in output
    assert not IntegrationConfiguration.objects.filter(
        integration=integration, action=reference_action,
    ).exists()
    assert integration.configurations.filter(action=er_action_show_permissions).exists()


def test_repair_integration_configurations_dry_run_creates_nothing(
    er_destination_without_show_permissions_config, er_action_show_permissions,
):
    integration = er_destination_without_show_permissions_config
    config_count_before = integration.configurations.count()

    call_command(
        "repair_integration_configurations",
        "--integration", str(integration.id),
        "--dry-run",
    )

    assert integration.configurations.count() == config_count_before
    assert not integration.configurations.filter(action=er_action_show_permissions).exists()


def test_repair_integration_configurations_is_idempotent(
    er_destination_without_show_permissions_config, er_action_show_permissions,
):
    integration = er_destination_without_show_permissions_config

    call_command("repair_integration_configurations", "--integration", str(integration.id))
    count_after_first = integration.configurations.count()

    call_command("repair_integration_configurations", "--integration", str(integration.id))
    count_after_second = integration.configurations.count()

    assert count_after_first == count_after_second


def test_repair_integration_configurations_refuses_without_selector():
    with pytest.raises(CommandError, match="Refusing to run without a target"):
        call_command("repair_integration_configurations")


def test_repair_integration_configurations_unknown_integration_raises():
    with pytest.raises(CommandError, match="not found"):
        call_command(
            "repair_integration_configurations",
            "--integration", "00000000-0000-0000-0000-000000000000",
        )


def test_repair_integration_configurations_unknown_type_raises():
    with pytest.raises(CommandError, match="not found"):
        call_command(
            "repair_integration_configurations",
            "--integration-type", "definitely-not-a-real-type",
        )


def test_repair_integration_configurations_rejects_combined_selectors():
    with pytest.raises(CommandError, match="exactly one of"):
        call_command(
            "repair_integration_configurations",
            "--integration", "00000000-0000-0000-0000-000000000000",
            "--integration-type", "earth_ranger",
        )


def test_repair_integration_configurations_rejects_all_with_other_selector():
    with pytest.raises(CommandError, match="exactly one of"):
        call_command(
            "repair_integration_configurations",
            "--all",
            "--integration-type", "earth_ranger",
        )


def test_repair_integration_configurations_with_all_flag(
    er_destination_without_show_permissions_config, er_action_show_permissions,
):
    integration = er_destination_without_show_permissions_config
    assert not integration.configurations.filter(action=er_action_show_permissions).exists()

    call_command("repair_integration_configurations", "--all")

    assert integration.configurations.filter(action=er_action_show_permissions).exists()


def test_call_set_action_configs_command_with_integration_type(
    er_destination_without_show_permissions_config, er_action_show_permissions
):
    integration_type = "earth_ranger"
    config_json = '{"include_subjects_from_subgroups_in_parent":false}'

    call_command(
        "set_action_configs",
        "--integration-type", integration_type,
        "--max", "1",
        "--action", "show_permissions",
        "--data", config_json
    )

    new_config = er_destination_without_show_permissions_config.configurations.filter(
        integration=er_destination_without_show_permissions_config,
        action=er_action_show_permissions
    ).first()
    assert new_config is not None
    assert new_config.data == json.loads(config_json)


# --- check_default_routes -------------------------------------------------------

@pytest.fixture
def broken_providers(organization, integration_type_lotek, destination_movebank):
    def provider(name):
        return Integration.objects.create(
            type=integration_type_lotek, owner=organization, name=name, base_url="https://api.test.lotek.com",
        )

    def route(name, providers=(), destinations=()):
        r = Route.objects.create(owner=organization, name=name)
        RouteProvider.objects.bulk_create([RouteProvider(integration=p, route=r) for p in providers])
        RouteDestination.objects.bulk_create([RouteDestination(integration=d, route=r) for d in destinations])
        return r

    fixable = provider("Fixable")                      # NULL default, one route → repairable
    fixable_route = route("Fixable route", providers=[fixable], destinations=[destination_movebank])

    ambiguous = provider("Ambiguous")                  # NULL default, two delivering routes → needs a human
    route("Amb A", providers=[ambiguous], destinations=[destination_movebank])
    route("Amb B", providers=[ambiguous], destinations=[destination_movebank])

    fine = provider("Fine")
    fine_route = route("Fine route", providers=[fine], destinations=[destination_movebank])
    Integration.objects.filter(pk=fine.pk).update(default_route=fine_route)

    return {"fixable": fixable, "fixable_route": fixable_route, "ambiguous": ambiguous, "fine": fine}


def _run(*args):
    out, err = StringIO(), StringIO()
    call_command("check_default_routes", *args, stdout=out, stderr=err)
    return out.getvalue(), err.getvalue()


def test_check_default_routes_dry_run_lists_violators_and_exits_nonzero(broken_providers):
    out = StringIO()
    with pytest.raises(CommandError, match="2 provider"):
        call_command("check_default_routes", stdout=out)

    text = out.getvalue()
    assert str(broken_providers["fixable"].id) in text and "missing" in text
    assert str(broken_providers["ambiguous"].id) in text
    assert str(broken_providers["fine"].id) not in text
    broken_providers["fixable"].refresh_from_db()
    assert broken_providers["fixable"].default_route is None          # dry run wrote nothing


def test_check_default_routes_exits_zero_when_clean(broken_providers):
    out, _ = _run("--integration", str(broken_providers["fine"].id))
    assert "No default route violations" in out


def test_check_default_routes_fix_repairs_unambiguous_and_lists_ambiguous(broken_providers):
    out = StringIO()
    with pytest.raises(CommandError, match="1 provider"):
        call_command("check_default_routes", "--fix", stdout=out)

    fixable = broken_providers["fixable"]
    fixable.refresh_from_db()
    assert fixable.default_route == broken_providers["fixable_route"]
    log = ActivityLog.objects.get(integration=fixable, value="default_route_auto_assigned")
    assert log.details["via"] == "check_default_routes"
    broken_providers["ambiguous"].refresh_from_db()
    assert broken_providers["ambiguous"].default_route is None
    text = out.getvalue()
    assert "fixed" in text and "ambiguous" in text and "Amb A" in text and "Amb B" in text


def test_check_default_routes_fix_exits_zero_when_everything_was_repaired(broken_providers):
    out, _ = _run("--fix", "--integration", str(broken_providers["fixable"].id))
    assert "fixed" in out


def test_check_default_routes_integration_scope(broken_providers):
    out = StringIO()
    with pytest.raises(CommandError, match="1 provider"):
        call_command("check_default_routes", "--integration", str(broken_providers["ambiguous"].id), stdout=out)
    assert str(broken_providers["fixable"].id) not in out.getvalue()


def test_check_default_routes_unknown_integration_is_an_error(broken_providers):
    with pytest.raises(CommandError, match="not found"):
        call_command("check_default_routes", "--integration", str(uuid.uuid4()), stdout=StringIO())


def test_check_default_routes_json_output(broken_providers):
    out = StringIO()
    with pytest.raises(CommandError):
        call_command("check_default_routes", "--json", stdout=out)

    report = json.loads(out.getvalue())
    by_id = {entry["id"]: entry for entry in report}
    fixable = by_id[str(broken_providers["fixable"].id)]
    assert fixable["violation"] == "missing"
    assert fixable["default_route"] is None
    assert fixable["candidates"] == [
        {"id": str(broken_providers["fixable_route"].id), "name": "Fixable route", "destination_count": 1}
    ]
    assert set(fixable) >= {"id", "name", "type", "owner", "default_route", "violation", "candidates"}

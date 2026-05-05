import json
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from integrations.models import IntegrationAction, IntegrationConfiguration


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

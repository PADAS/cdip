import json
import pytest
from django.core.management import call_command


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

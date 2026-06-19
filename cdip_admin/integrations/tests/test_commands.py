import json
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from integrations.models import IntegrationAction, IntegrationConfiguration, IntegrationStatus


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


def test_recalculate_integration_statuses_command_for_single_integration(
    provider_lotek_panthera,
    pull_observations_action_started_activity_log,
    pull_observations_action_failed_activity_log,
    pull_observations_action_failed_activity_log_2,
    pull_observations_action_failed_activity_log_3,
):
    # Start from a stale healthy status; the command must recompute it from the error logs.
    provider_lotek_panthera.status.status = IntegrationStatus.Status.HEALTHY
    provider_lotek_panthera.status.save()

    call_command(
        "recalculate_integration_statuses",
        "--integration-id", str(provider_lotek_panthera.id),
    )

    provider_lotek_panthera.status.refresh_from_db()
    assert provider_lotek_panthera.status.status == IntegrationStatus.Status.UNHEALTHY


def test_recalculate_integration_statuses_command_async_enqueues_task(mocker, provider_lotek_panthera):
    mocked_task = mocker.patch("integrations.tasks.calculate_integration_statuses.delay")

    call_command(
        "recalculate_integration_statuses",
        "--integration-id", str(provider_lotek_panthera.id),
        "--async",
    )

    mocked_task.assert_called_once_with(integration_ids=[str(provider_lotek_panthera.id)])


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

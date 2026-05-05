import pytest
from django_celery_beat.models import PeriodicTask

from integrations.models import IntegrationAction, IntegrationConfiguration


pytestmark = pytest.mark.django_db


@pytest.fixture
def run_on_commit_immediately(mocker):
    # The post_save signal schedules backfill via transaction.on_commit, which
    # does not fire inside django_db's nested transaction. Run it inline in tests.
    mocker.patch("integrations.signals.transaction.on_commit", lambda fn: fn())


def test_new_action_backfills_existing_integrations(
    run_on_commit_immediately, er_destination_without_show_permissions_config, integration_type_er,
):
    integration = er_destination_without_show_permissions_config
    config_count_before = integration.configurations.count()

    new_action = IntegrationAction.objects.create(
        integration_type=integration_type_er,
        type=IntegrationAction.ActionTypes.GENERIC,
        name="New Generic Action",
        value="new_generic_action",
    )

    new_config = IntegrationConfiguration.objects.filter(
        integration=integration, action=new_action,
    ).first()
    assert new_config is not None
    assert new_config.data == {}
    assert integration.configurations.count() == config_count_before + 1


def test_new_periodic_action_creates_periodic_task(
    run_on_commit_immediately, er_destination_without_show_permissions_config, integration_type_er,
):
    integration = er_destination_without_show_permissions_config

    new_periodic_action = IntegrationAction.objects.create(
        integration_type=integration_type_er,
        type=IntegrationAction.ActionTypes.PULL_DATA,
        name="New Periodic Pull",
        value="new_periodic_pull",
        is_periodic_action=True,
    )

    new_config = IntegrationConfiguration.objects.get(
        integration=integration, action=new_periodic_action,
    )
    assert new_config.periodic_task is not None
    assert PeriodicTask.objects.filter(id=new_config.periodic_task_id).exists()


def test_updating_existing_action_does_not_recreate_configs(
    run_on_commit_immediately, er_destination_without_show_permissions_config,
    er_action_push_positions,
):
    integration = er_destination_without_show_permissions_config
    config_count_before = integration.configurations.count()

    er_action_push_positions.name = "Push Positions (renamed)"
    er_action_push_positions.save()

    assert integration.configurations.count() == config_count_before


def test_new_action_does_not_duplicate_existing_configs(
    run_on_commit_immediately, er_destination_without_show_permissions_config,
    integration_type_er, er_action_push_positions,
):
    integration = er_destination_without_show_permissions_config
    push_positions_configs_before = integration.configurations.filter(
        action=er_action_push_positions,
    ).count()

    IntegrationAction.objects.create(
        integration_type=integration_type_er,
        type=IntegrationAction.ActionTypes.GENERIC,
        name="Yet Another Action",
        value="yet_another_action",
    )

    push_positions_configs_after = integration.configurations.filter(
        action=er_action_push_positions,
    ).count()
    assert push_positions_configs_before == push_positions_configs_after

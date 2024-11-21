import pytest
import json
from django_celery_beat.models import  PeriodicTask
from ..models import IntegrationConfiguration


pytestmark = pytest.mark.django_db


def test_periodic_task_is_created_for_periodic_actions(provider_lotek_panthera, lotek_action_auth, lotek_action_pull_positions):
    # Check that a schedule was created, only for periodic actions
    periodic_tasks = PeriodicTask.objects.filter(task="integrations.tasks.run_integration")
    assert periodic_tasks.count() == 1  # Only one task should be created, for the pull_observations action
    task_parameters = json.loads(periodic_tasks[0].kwargs)
    assert task_parameters.get("integration_id") == str(provider_lotek_panthera.id)
    assert task_parameters.get("action_id") == lotek_action_pull_positions.value


def test_disable_periodic_task_on_integration_disabled(provider_lotek_panthera, lotek_action_auth, lotek_action_pull_positions):
    provider_lotek_panthera.enabled = False
    provider_lotek_panthera.save()
    periodic_task = PeriodicTask.objects.get(task="integrations.tasks.run_integration")
    assert not periodic_task.enabled


def test_enable_periodic_task_on_integration_enabled(provider_lotek_panthera, lotek_action_auth, lotek_action_pull_positions):
    provider_lotek_panthera.enabled = False
    provider_lotek_panthera.save()
    provider_lotek_panthera.enabled = True
    provider_lotek_panthera.save()
    periodic_task = PeriodicTask.objects.get(task="integrations.tasks.run_integration")
    assert periodic_task.enabled

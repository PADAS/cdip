import pytest
import json
from django_celery_beat.models import  PeriodicTask
from ..models import IntegrationConfiguration


pytestmark = pytest.mark.django_db


def test_periodic_task_is_created_for_periodic_actions(provider_lotek_panthera, lotek_action_auth, lotek_action_pull_positions):
    # Crete configurations for a provider integration
    IntegrationConfiguration.objects.create(
        integration=provider_lotek_panthera,
        action=lotek_action_auth,  # Not a periodic action
        data={
            "username": "test",
            "password": "test"
        }
    )
    IntegrationConfiguration.objects.create(
        integration=provider_lotek_panthera,  # Periodic action
        action=lotek_action_pull_positions,
        data={
            "start_time": "2023-10-31T00:00:00"
        }
    )
    # Check that a schedule was created, only for periodic actions
    periodic_tasks = PeriodicTask.objects.filter(task="integrations.tasks.run_integration")
    assert periodic_tasks.count() == 1
    task_parameters = json.loads(periodic_tasks[0].kwargs)
    assert task_parameters.get("integration_id") == str(provider_lotek_panthera.id)
    assert task_parameters.get("action_id") == lotek_action_pull_positions.value

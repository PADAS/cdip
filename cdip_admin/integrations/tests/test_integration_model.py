import pytest
from django.conf import settings
from django_celery_beat.models import PeriodicTask

from ..models import Integration, OutboundIntegrationConfiguration


pytestmark = pytest.mark.django_db


def test_create_movebank_destination_v1_with_default_settings(other_organization, legacy_integration_type_movebank):
    integration = OutboundIntegrationConfiguration.objects.create(
        type=legacy_integration_type_movebank,
        name=f"Movebank Site",
        owner=other_organization,
        endpoint=f"https://api.test.movebank.com",
        # additional  # Not set, let it use defaults
    )
    assert integration.additional.get("broker") == "gcp_pubsub"
    assert integration.additional.get("topic") == settings.MOVEBANK_DISPATCHER_DEFAULT_TOPIC


def test_create_movebank_destination_v2_with_default_settings(other_organization, integration_type_movebank):
    integration = Integration.objects.create(
        type=integration_type_movebank,
        name=f"Movebank Site",
        owner=other_organization,
        base_url=f"https://api.test.movebank.com",
        # additional  # Not set, let it use defaults
    )
    assert integration.additional.get("broker") == "gcp_pubsub"
    assert integration.additional.get("topic") == settings.MOVEBANK_DISPATCHER_DEFAULT_TOPIC


def test_delete_integration_with_default_route(provider_lotek_panthera):
    provider_lotek_panthera.delete()


def test_delete_periodic_tasks_on_integration_delete(provider_lotek_panthera):
    task_ids = [c.periodic_task.id for c in provider_lotek_panthera.configurations if c.action.is_periodic_action]

    provider_lotek_panthera.delete()

    # Configurations are be deleted on cascade, and associated tasks should be deleted as well
    for task_id in task_ids:
        with pytest.raises(PeriodicTask.DoesNotExist):
            PeriodicTask.objects.get(id=task_id)

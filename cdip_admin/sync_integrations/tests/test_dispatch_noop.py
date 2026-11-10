import pytest

from sync_integrations.tasks import synchronize_smart_datamodels


pytestmark = pytest.mark.django_db


def test_celery_once_task_dispatch_does_not_reach_the_broker():
    """
    celery-once tasks override apply_async and take a Redis lock before
    dispatching, so the test no-op must cover them as well as plain tasks.
    """
    result = synchronize_smart_datamodels.delay("00000000-0000-0000-0000-000000000000")

    assert result is not None

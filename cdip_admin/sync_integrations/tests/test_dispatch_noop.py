from unittest.mock import MagicMock

import pytest
from kombu.exceptions import EncodeError

from activity_log.tasks import publish_configuration_event
from sync_integrations.tasks import synchronize_smart_datamodels


def test_celery_once_task_dispatch_does_not_reach_the_broker():
    """
    celery-once tasks override apply_async and take a Redis lock before
    dispatching, so the test no-op must cover them as well as plain tasks.
    """
    result = synchronize_smart_datamodels.delay("00000000-0000-0000-0000-000000000000")

    assert isinstance(result, MagicMock)
    assert isinstance(result.id, str) and result.id


def test_dispatch_still_serializes_arguments():
    """
    Production serializes task arguments to JSON on dispatch. The no-op keeps
    that check so an unserializable argument fails here, not in production.
    """
    with pytest.raises(EncodeError):
        publish_configuration_event.delay(event_data={"obj": object()}, attributes={})


@pytest.fixture(scope="module")
def dispatched_from_a_module_fixture():
    return synchronize_smart_datamodels.delay("00000000-0000-0000-0000-000000000000")


def test_dispatch_is_a_noop_during_higher_scoped_fixtures(dispatched_from_a_module_fixture):
    """Fixture setup above function scope runs before function-scoped patches would apply."""
    assert isinstance(dispatched_from_a_module_fixture, MagicMock)


def test_send_task_by_name_with_positional_arguments_is_a_noop():
    """
    Celery.send_task takes the task name before args and kwargs, unlike
    Task.apply_async; the no-op must honour that signature.
    """
    result = synchronize_smart_datamodels.app.send_task(
        "sync_integrations.tasks.synchronize_smart_datamodels",
        ("00000000-0000-0000-0000-000000000000",),
    )

    assert isinstance(result, MagicMock)
    assert isinstance(result.id, str) and result.id


def test_send_task_by_name_still_serializes_positional_arguments():
    with pytest.raises(EncodeError):
        synchronize_smart_datamodels.app.send_task(
            "sync_integrations.tasks.synchronize_smart_datamodels",
            ("00000000-0000-0000-0000-000000000000",),
            {"obj": object()},
        )

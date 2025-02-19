from activity_log.core import ActivityActions
from activity_log.models import ActivityLog


def _test_activity_logs_on_instance_created(activity_log, instance, user):
    Model = instance._meta.model
    model_name = str(Model.__name__)
    details = activity_log.details
    assert activity_log
    assert activity_log.log_type == ActivityLog.LogTypes.DATA_CHANGE
    assert activity_log.log_level == ActivityLog.LogLevels.INFO
    assert activity_log.origin == ActivityLog.Origin.PORTAL
    expected_title = f"{model_name} {ActivityActions.CREATED.value}"
    if hasattr(Model, "logs_id_field"):
        expected_title += f" ({getattr(instance, Model.logs_id_field)})"
    if user and not user.is_anonymous:
        expected_title += f" by {user}"
    assert activity_log.title == expected_title
    assert details.get("model_name") == model_name
    assert details.get("instance_pk") == str(instance.pk)
    assert details.get("action") == ActivityActions.CREATED.value
    assert activity_log.is_reversible
    assert activity_log.revert_data == {
        "model_name": model_name,
        "instance_pk": str(instance.pk)
    }


def _test_activity_logs_on_instance_updated(activity_log, instance, user, expected_changes, expected_revert_data):
    model = str(instance._meta.model.__name__)
    details = activity_log.details
    assert activity_log
    assert activity_log.log_type == ActivityLog.LogTypes.DATA_CHANGE
    assert activity_log.log_level == ActivityLog.LogLevels.INFO
    assert activity_log.origin == ActivityLog.Origin.PORTAL
    expected_title = f"{model} {ActivityActions.UPDATED.value}"
    if alt_id := activity_log.details.get("alt_id"):
        expected_title += f" ({alt_id})"
    if user and not user.is_anonymous:
        expected_title += f" by {user}"
    assert activity_log.title == expected_title
    assert details.get("model_name") == model
    assert details.get("instance_pk") == str(instance.pk)
    assert details.get("action") == ActivityActions.UPDATED.value
    assert "changes" in details
    assert activity_log.is_reversible
    changes = details.get("changes")
    for field, value in expected_changes.items():
        assert changes.get(field) == value
    revert_data = activity_log.revert_data
    for field, value in expected_revert_data.items():
        if isinstance(value, dict):
            for key, val in value.items():
                assert revert_data.get(field).get(key) == val
        else:
            assert revert_data.get(field) == value

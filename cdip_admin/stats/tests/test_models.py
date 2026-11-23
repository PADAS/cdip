import datetime
import uuid

import pytest
from django.db import IntegrityError, transaction

from stats.models import ErrorRollup, RollupRunState, ThroughputRollup

pytestmark = pytest.mark.django_db

BUCKET = datetime.datetime(2026, 11, 20, 14, 0, tzinfo=datetime.timezone.utc)


def _throughput(**overrides):
    values = dict(
        bucket=BUCKET,
        data_provider_id=uuid.uuid4(),
        destination_id=None,
        object_type="obv",
        metric=ThroughputRollup.Metric.RECEIVED,
        count=3,
    )
    values.update(overrides)
    return ThroughputRollup.objects.create(**values)


def _error(**overrides):
    values = dict(
        bucket=BUCKET,
        integration_id=uuid.uuid4(),
        origin="disp",
        value="observation_delivery_failed",
        log_level=40,
        count=2,
    )
    values.update(overrides)
    return ErrorRollup.objects.create(**values)


def test_throughput_row_without_destination_is_valid():
    for metric in (
        ThroughputRollup.Metric.RECEIVED,
        ThroughputRollup.Metric.DUPLICATE,
        ThroughputRollup.Metric.DISCARDED,
    ):
        row = _throughput(metric=metric)
        assert row.destination_id is None


def test_throughput_duplicate_key_with_destination_is_rejected():
    provider, destination = uuid.uuid4(), uuid.uuid4()
    key = dict(
        data_provider_id=provider,
        destination_id=destination,
        metric=ThroughputRollup.Metric.DELIVERED,
    )
    _throughput(**key)
    with pytest.raises(IntegrityError), transaction.atomic():
        _throughput(**key)


def test_throughput_duplicate_key_with_null_destination_is_rejected():
    # PostgreSQL treats NULLs as distinct in a plain unique constraint, so this
    # case needs its own partial constraint.
    provider = uuid.uuid4()
    _throughput(data_provider_id=provider)
    with pytest.raises(IntegrityError), transaction.atomic():
        _throughput(data_provider_id=provider)


def test_throughput_same_key_in_another_bucket_or_metric_is_allowed():
    provider = uuid.uuid4()
    _throughput(data_provider_id=provider)
    _throughput(data_provider_id=provider, bucket=BUCKET + datetime.timedelta(hours=1))
    _throughput(data_provider_id=provider, metric=ThroughputRollup.Metric.DUPLICATE)
    _throughput(data_provider_id=provider, object_type="ev")
    assert ThroughputRollup.objects.filter(data_provider_id=provider).count() == 4


def test_error_duplicate_key_with_integration_is_rejected():
    integration = uuid.uuid4()
    _error(integration_id=integration)
    with pytest.raises(IntegrityError), transaction.atomic():
        _error(integration_id=integration)


def test_error_duplicate_key_with_null_integration_is_rejected():
    _error(integration_id=None)
    with pytest.raises(IntegrityError), transaction.atomic():
        _error(integration_id=None)


def test_error_same_key_with_another_level_is_allowed():
    integration = uuid.uuid4()
    _error(integration_id=integration, log_level=40)
    _error(integration_id=integration, log_level=30)
    assert ErrorRollup.objects.filter(integration_id=integration).count() == 2


def test_rollup_rows_survive_deletion_of_their_integration(provider_lotek_panthera):
    integration_id = provider_lotek_panthera.id
    _throughput(data_provider_id=integration_id)
    _throughput(
        data_provider_id=uuid.uuid4(),
        destination_id=integration_id,
        metric=ThroughputRollup.Metric.DELIVERED,
    )
    _error(integration_id=integration_id)

    provider_lotek_panthera.delete()

    assert ThroughputRollup.objects.filter(data_provider_id=integration_id).count() == 1
    assert ThroughputRollup.objects.filter(destination_id=integration_id).count() == 1
    assert ErrorRollup.objects.filter(integration_id=integration_id).count() == 1


def test_run_state_is_a_single_row_with_one_time_per_task():
    state = RollupRunState.load()
    assert state.frequent_run_completed_at is None
    assert state.daily_run_completed_at is None

    state.frequent_run_completed_at = BUCKET
    state.save()

    again = RollupRunState.load()
    assert again.pk == state.pk
    assert again.frequent_run_completed_at == BUCKET
    assert again.daily_run_completed_at is None
    assert RollupRunState.objects.count() == 1


def test_rollup_admins_are_read_only(rf, admin_user):
    from django.contrib import admin

    request = rf.get("/admin/")
    request.user = admin_user
    for model in (ThroughputRollup, ErrorRollup, RollupRunState):
        model_admin = admin.site._registry[model]
        assert not model_admin.has_add_permission(request)
        assert not model_admin.has_change_permission(request)
        assert not model_admin.has_delete_permission(request)

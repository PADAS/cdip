"""Unit tests for deployments.utils.subscription_is_drained.

Portal subscriptions are push subscriptions, so a subscriber-side pull can
never succeed against them (Pub/Sub returns FAILED_PRECONDITION). These tests
cover the Cloud Monitoring based replacement: it reads the
``pubsub.googleapis.com/subscription/num_undelivered_messages`` metric and
looks at the most recent data point across whatever time series come back.

The ``google.cloud.monitoring_v3`` module is mocked at the point it's
imported into ``deployments.utils`` (``deployments.utils.monitoring_v3``), not
in the real client library, so these tests never make a network call.
"""
from unittest.mock import MagicMock

from deployments.utils import subscription_is_drained


def _make_point(end_seconds, value):
    point = MagicMock()
    point.interval.end_time.seconds = end_seconds
    point.value.int64_value = value
    return point


def _make_series(*points):
    series = MagicMock()
    series.points = list(points)
    return series


def _configuration():
    return {"env_vars": {"GCP_PROJECT_ID": "test-project"}}


def _mock_client():
    client = MagicMock()
    client.__enter__.return_value = client
    client.__exit__.return_value = False
    return client


def test_subscription_is_drained_true_when_latest_point_is_zero(mocker):
    mock_client = _mock_client()
    mock_client.list_time_series.return_value = [
        _make_series(_make_point(end_seconds=100, value=5), _make_point(end_seconds=200, value=0)),
    ]
    mock_monitoring_v3 = mocker.patch("deployments.utils.monitoring_v3")
    mock_monitoring_v3.MetricServiceClient.return_value = mock_client

    assert subscription_is_drained("some-sub", _configuration()) is True


def test_subscription_is_drained_false_when_latest_point_is_nonzero(mocker):
    mock_client = _mock_client()
    mock_client.list_time_series.return_value = [
        _make_series(_make_point(end_seconds=100, value=0), _make_point(end_seconds=200, value=5)),
    ]
    mock_monitoring_v3 = mocker.patch("deployments.utils.monitoring_v3")
    mock_monitoring_v3.MetricServiceClient.return_value = mock_client

    assert subscription_is_drained("some-sub", _configuration()) is False


def test_subscription_is_drained_false_when_no_data_points(mocker):
    mock_client = _mock_client()
    mock_client.list_time_series.return_value = []  # empty series -> no data points at all
    mock_monitoring_v3 = mocker.patch("deployments.utils.monitoring_v3")
    mock_monitoring_v3.MetricServiceClient.return_value = mock_client

    assert subscription_is_drained("some-sub", _configuration()) is False

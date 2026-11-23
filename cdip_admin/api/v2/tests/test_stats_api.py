import datetime
import uuid

import pytest
from django.contrib.auth.models import Group, User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework import status

from core.enums import DjangoGroups
from stats import queries
from stats.models import ErrorRollup, RollupRunState, ThroughputRollup

pytestmark = pytest.mark.django_db

UTC = datetime.timezone.utc
HOUR = datetime.timedelta(hours=1)
DAY0 = datetime.datetime(2026, 11, 19, 0, 0, tzinfo=UTC)
DAY1 = DAY0 + datetime.timedelta(days=1)
RANGE = {"from_date": DAY0.isoformat(), "to_date": (DAY0 + datetime.timedelta(days=2)).isoformat()}
Metric = ThroughputRollup.Metric
ENDPOINTS = ("stats-throughput", "stats-errors", "stats-usage")


def iso(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture(autouse=True)
def stats_settings(settings):
    settings.STATS_THROUGHPUT_START = datetime.datetime(2020, 1, 1, tzinfo=UTC)
    return settings


@pytest.fixture
def viewer_client(api_client, metrics_viewer):
    api_client.force_authenticate(metrics_viewer)
    return api_client


def throughput_row(provider_id, metric, count, bucket=DAY0, destination_id=None, object_type="obv"):
    return ThroughputRollup.objects.create(
        bucket=bucket, data_provider_id=provider_id, destination_id=destination_id,
        object_type=object_type, metric=metric, count=count,
    )


def error_row(integration_id, count, bucket=DAY0, value="observation_delivery_failed",
              origin="disp", log_level=40):
    return ErrorRollup.objects.create(
        bucket=bucket, integration_id=integration_id, origin=origin, value=value,
        log_level=log_level, count=count,
    )


def get(client, name, **params):
    return client.get(reverse(name), params)


# --- access -----------------------------------------------------------------

@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_metrics_viewer_can_read(viewer_client, endpoint):
    assert get(viewer_client, endpoint).status_code == status.HTTP_200_OK


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_superuser_can_read(api_client, superuser, endpoint):
    api_client.force_authenticate(superuser)
    assert get(api_client, endpoint).status_code == status.HTTP_200_OK


@pytest.mark.parametrize("endpoint", ENDPOINTS)
@pytest.mark.parametrize("user_fixture", ["org_admin_user", "org_viewer_user"])
def test_organization_members_are_forbidden(api_client, request, endpoint, user_fixture):
    api_client.force_authenticate(request.getfixturevalue(user_fixture))
    assert get(api_client, endpoint).status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_global_admin_outside_the_group_is_forbidden(api_client, endpoint):
    user = User.objects.create_user(username="global-admin@gundiservice.org")
    user.groups.add(Group.objects.get(name=DjangoGroups.GLOBAL_ADMIN.value))
    api_client.force_authenticate(user)
    assert get(api_client, endpoint).status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_staff_user_outside_the_group_is_forbidden(api_client, endpoint):
    user = User.objects.create_user(username="staff@gundiservice.org", is_staff=True)
    api_client.force_authenticate(user)
    assert get(api_client, endpoint).status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_service_account_is_forbidden(api_client, endpoint):
    # A service account authenticates as a plain user carrying a client id.
    user = User.objects.create_user(username="service-account-test-function")
    api_client.force_authenticate(user)
    assert get(api_client, endpoint).status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_anonymous_client_is_rejected(api_client, endpoint):
    assert get(api_client, endpoint).status_code in (
        status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN
    )


@pytest.mark.parametrize("endpoint", ENDPOINTS)
@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_endpoints_are_read_only(viewer_client, endpoint, method):
    response = getattr(viewer_client, method)(reverse(endpoint), {})
    assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


def test_stats_paths_use_stateless_auth(settings):
    path = reverse("stats-throughput")
    assert path == "/v2/stats/throughput/"
    assert any(path.startswith(prefix) for prefix in settings.STATELESS_AUTH_PATH_PREFIXES)


# --- throughput -------------------------------------------------------------

def test_throughput_defaults_to_hourly_buckets_of_the_last_24_hours(viewer_client, provider_lotek_panthera):
    now = datetime.datetime.now(UTC)
    current = now.replace(minute=0, second=0, microsecond=0)
    throughput_row(provider_lotek_panthera.id, Metric.RECEIVED, 5, bucket=current - HOUR)
    throughput_row(provider_lotek_panthera.id, Metric.DUPLICATE, 1, bucket=current - HOUR)
    throughput_row(provider_lotek_panthera.id, Metric.RECEIVED, 2, bucket=current - 3 * HOUR)
    throughput_row(provider_lotek_panthera.id, Metric.RECEIVED, 9, bucket=current - 30 * HOUR)  # too old

    response = get(viewer_client, "stats-throughput")

    data = response.json()
    assert data["interval"] == "hour"
    assert data["group_by"] == []
    assert data["from"] == iso(current - 24 * HOUR)
    assert data["results"] == [
        {"bucket": iso(current - 3 * HOUR), "received": 2, "delivered": 0, "discarded": 0, "duplicate": 0},
        {"bucket": iso(current - HOUR), "received": 5, "delivered": 0, "discarded": 0, "duplicate": 1},
    ]


def test_throughput_day_interval_sums_the_hours_of_each_day(
    viewer_client, provider_lotek_panthera, integrations_list_er
):
    destination = integrations_list_er[0]
    throughput_row(provider_lotek_panthera.id, Metric.RECEIVED, 5, bucket=DAY0 + HOUR)
    throughput_row(provider_lotek_panthera.id, Metric.RECEIVED, 7, bucket=DAY0 + 23 * HOUR)
    throughput_row(provider_lotek_panthera.id, Metric.DELIVERED, 4, bucket=DAY0 + 2 * HOUR,
                   destination_id=destination.id)
    throughput_row(provider_lotek_panthera.id, Metric.DISCARDED, 3, bucket=DAY1)

    data = get(viewer_client, "stats-throughput", interval="day", **RANGE).json()

    assert data["interval"] == "day"
    assert data["results"] == [
        {"bucket": iso(DAY0), "received": 12, "delivered": 4, "discarded": 0, "duplicate": 0},
        {"bucket": iso(DAY1), "received": 0, "delivered": 0, "discarded": 3, "duplicate": 0},
    ]


def test_throughput_range_end_is_exclusive_and_start_is_floored_to_the_interval(
    viewer_client, provider_lotek_panthera
):
    throughput_row(provider_lotek_panthera.id, Metric.RECEIVED, 1, bucket=DAY0)
    throughput_row(provider_lotek_panthera.id, Metric.RECEIVED, 2, bucket=DAY0 + 2 * HOUR)

    data = get(
        viewer_client, "stats-throughput",
        from_date=(DAY0 + datetime.timedelta(minutes=30)).isoformat(),
        to_date=(DAY0 + 2 * HOUR).isoformat(),
    ).json()

    # The response states the range it served.
    assert data["from"] == iso(DAY0)
    assert data["to"] == iso(DAY0 + 2 * HOUR)
    assert [row["received"] for row in data["results"]] == [1]


def test_throughput_grouped_by_integration_type_sums_across_integrations(
    viewer_client, provider_lotek_panthera, provider_movebank_ewt, integrations_list_er
):
    er_a, er_b = integrations_list_er[0], integrations_list_er[1]
    throughput_row(er_a.id, Metric.RECEIVED, 3)
    throughput_row(er_b.id, Metric.RECEIVED, 4)
    throughput_row(provider_lotek_panthera.id, Metric.RECEIVED, 10)

    data = get(viewer_client, "stats-throughput", group_by="integration_type", **RANGE).json()

    assert data["group_by"] == ["integration_type"]
    by_type = {row["integration_type"]: row["received"] for row in data["results"]}
    assert by_type == {er_a.type.value: 7, provider_lotek_panthera.type.value: 10}


def test_throughput_grouped_by_two_dimensions(viewer_client, provider_lotek_panthera, integrations_list_er):
    destination = integrations_list_er[0]
    throughput_row(provider_lotek_panthera.id, Metric.DELIVERED, 4, destination_id=destination.id)
    throughput_row(provider_lotek_panthera.id, Metric.DELIVERED, 6, destination_id=destination.id,
                   object_type="ev")
    throughput_row(provider_lotek_panthera.id, Metric.RECEIVED, 11)

    data = get(viewer_client, "stats-throughput", group_by="destination,data_type", **RANGE).json()

    assert data["group_by"] == ["destination", "data_type"]
    rows = {(row["destination_id"], row["data_type"]): row for row in data["results"]}
    assert rows[(str(destination.id), "obv")]["delivered"] == 4
    assert rows[(str(destination.id), "obv")]["destination"] == destination.name
    assert rows[(str(destination.id), "ev")]["delivered"] == 6
    # Received counts have no destination.
    assert rows[(None, "obv")]["received"] == 11
    assert rows[(None, "obv")]["destination"] is None


def test_throughput_filtered_by_organization_returns_only_its_data_providers(
    viewer_client, organization, other_organization, provider_lotek_panthera, integrations_list_er
):
    other_provider = next(i for i in integrations_list_er if i.owner_id == other_organization.id)
    assert provider_lotek_panthera.owner_id == organization.id
    throughput_row(provider_lotek_panthera.id, Metric.RECEIVED, 5)
    throughput_row(other_provider.id, Metric.RECEIVED, 8)

    data = get(
        viewer_client, "stats-throughput", organization=str(organization.id),
        group_by="data_provider", **RANGE
    ).json()

    assert [(row["data_provider_id"], row["data_provider"], row["received"]) for row in data["results"]] == [
        (str(provider_lotek_panthera.id), provider_lotek_panthera.name, 5)
    ]


@pytest.mark.parametrize("param,attr", [
    ("data_provider", "provider"), ("destination", "destination"), ("data_type", "data_type"),
    ("integration_type", "integration_type"),
])
def test_throughput_filters(viewer_client, provider_lotek_panthera, integrations_list_er, param, attr):
    destination = integrations_list_er[0]
    throughput_row(provider_lotek_panthera.id, Metric.DELIVERED, 4, destination_id=destination.id)
    throughput_row(integrations_list_er[1].id, Metric.DELIVERED, 9,
                   destination_id=integrations_list_er[2].id, object_type="ev")
    value = {
        "provider": str(provider_lotek_panthera.id),
        "destination": str(destination.id),
        "data_type": "obv",
        "integration_type": provider_lotek_panthera.type.value,
    }[attr]

    data = get(viewer_client, "stats-throughput", **{param: value}, **RANGE).json()

    assert [row["delivered"] for row in data["results"]] == [4]


def test_throughput_rows_of_a_deleted_integration_are_labelled_unknown_and_still_counted(
    viewer_client, provider_lotek_panthera
):
    deleted_id = uuid.uuid4()
    throughput_row(deleted_id, Metric.RECEIVED, 6)
    throughput_row(provider_lotek_panthera.id, Metric.RECEIVED, 1)

    total = get(viewer_client, "stats-throughput", **RANGE).json()
    by_provider = get(viewer_client, "stats-throughput", group_by="data_provider", **RANGE).json()
    by_type = get(viewer_client, "stats-throughput", group_by="integration_type", **RANGE).json()

    assert total["results"][0]["received"] == 7
    labels = {row["data_provider_id"]: row["data_provider"] for row in by_provider["results"]}
    assert labels[str(deleted_id)] == "unknown"
    assert {row["integration_type"]: row["received"] for row in by_type["results"]}["unknown"] == 6


# --- errors -----------------------------------------------------------------

def test_errors_returns_error_counts_only_by_default(viewer_client, provider_lotek_panthera):
    error_row(provider_lotek_panthera.id, 3)
    error_row(provider_lotek_panthera.id, 5, log_level=30)
    error_row(provider_lotek_panthera.id, 2, bucket=DAY0 + HOUR, log_level=30)  # retriable only

    data = get(viewer_client, "stats-errors", **RANGE).json()

    assert data["results"] == [{"bucket": iso(DAY0), "errors": 3}]


def test_errors_adds_retriable_counts_on_request(viewer_client, provider_lotek_panthera):
    error_row(provider_lotek_panthera.id, 3)
    error_row(provider_lotek_panthera.id, 5, log_level=30)
    error_row(provider_lotek_panthera.id, 2, bucket=DAY0 + HOUR, log_level=30)

    data = get(viewer_client, "stats-errors", include_retriable="true", **RANGE).json()

    assert data["results"] == [
        {"bucket": iso(DAY0), "errors": 3, "retriable": 5},
        {"bucket": iso(DAY0 + HOUR), "errors": 0, "retriable": 2},
    ]


def test_errors_grouped_by_integration_origin_and_kind(viewer_client, provider_lotek_panthera):
    error_row(provider_lotek_panthera.id, 3)
    error_row(provider_lotek_panthera.id, 4, value="integration_action_failed", origin="inte")
    error_row(None, 1, value="integration_action_failed", origin="inte")

    data = get(viewer_client, "stats-errors", group_by="integration,origin,kind", interval="day", **RANGE).json()

    rows = {(row["integration_id"], row["origin"], row["kind"]): row for row in data["results"]}
    provider_id = str(provider_lotek_panthera.id)
    assert rows[(provider_id, "disp", "observation_delivery_failed")]["errors"] == 3
    assert rows[(provider_id, "inte", "integration_action_failed")]["errors"] == 4
    assert rows[(provider_id, "disp", "observation_delivery_failed")]["integration"] == provider_lotek_panthera.name
    assert rows[(None, "inte", "integration_action_failed")]["integration"] == "unknown"


def test_errors_filtered_and_grouped_by_organization_and_type(
    viewer_client, organization, other_organization, provider_lotek_panthera, integrations_list_er
):
    other = next(i for i in integrations_list_er if i.owner_id == other_organization.id)
    error_row(provider_lotek_panthera.id, 3)
    error_row(other.id, 8)

    filtered = get(viewer_client, "stats-errors", organization=str(organization.id), **RANGE).json()
    grouped = get(viewer_client, "stats-errors", group_by="organization,integration_type", **RANGE).json()
    by_kind = get(viewer_client, "stats-errors", kind="no_such_kind", **RANGE).json()

    assert [row["errors"] for row in filtered["results"]] == [3]
    assert {(row["organization"], row["integration_type"]): row["errors"] for row in grouped["results"]} == {
        (organization.name, provider_lotek_panthera.type.value): 3,
        (other_organization.name, other.type.value): 8,
    }
    assert by_kind["results"] == []


# --- usage ------------------------------------------------------------------

def test_usage_returns_totals_active_counts_and_rankings(
    viewer_client, organization, other_organization, provider_lotek_panthera, provider_movebank_ewt,
    integrations_list_er
):
    from integrations.models import Integration, Route
    from organizations.models import Organization

    destination = integrations_list_er[0]
    throughput_row(provider_lotek_panthera.id, Metric.RECEIVED, 10)
    throughput_row(provider_lotek_panthera.id, Metric.RECEIVED, 5, bucket=DAY0 + HOUR)
    throughput_row(provider_lotek_panthera.id, Metric.DELIVERED, 12, destination_id=destination.id)
    throughput_row(provider_movebank_ewt.id, Metric.DISCARDED, 2)  # discarded only: not active
    throughput_row(provider_movebank_ewt.id, Metric.RECEIVED, 99, bucket=DAY0 - HOUR)  # outside the window

    data = get(viewer_client, "stats-usage", **RANGE).json()

    connections = Integration.objects.filter(routing_rules_by_provider__isnull=False).distinct().count()
    assert connections >= 1
    assert data["totals"] == {
        "organizations": Organization.objects.count(),
        "integrations": Integration.objects.count(),
        "connections": connections,
        "active_organizations": 1,
        "active_integrations": 2,
        "active_connections": 1,
    }
    rankings = {}
    for row in data["results"]:
        rankings.setdefault(row["dimension"], []).append(row)
    assert rankings["integration_type"] == [{
        "dimension": "integration_type", "id": None, "name": provider_lotek_panthera.type.value,
        "received": 15, "delivered": 12,
    }]
    assert rankings["organization"] == [{
        "dimension": "organization", "id": str(organization.id), "name": organization.name,
        "received": 15, "delivered": 12,
    }]
    assert rankings["destination"] == [{
        "dimension": "destination", "id": str(destination.id), "name": destination.name,
        "received": 0, "delivered": 12,
    }]


def test_usage_rankings_are_ordered_by_volume_and_limited(viewer_client, integrations_list_er):
    for index, integration in enumerate(integrations_list_er[:4]):
        throughput_row(integrations_list_er[5].id, Metric.DELIVERED, 10 * (index + 1),
                       destination_id=integration.id, object_type=f"t{index}")

    data = get(viewer_client, "stats-usage", limit=2, **RANGE).json()

    destinations = [row for row in data["results"] if row["dimension"] == "destination"]
    assert [row["delivered"] for row in destinations] == [40, 30]


# --- freshness and bounds ---------------------------------------------------

@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_freshness_is_null_before_the_first_successful_run(viewer_client, endpoint):
    data = get(viewer_client, endpoint, **RANGE).json()

    assert data["data_as_of"] is None and data["reconciled_as_of"] is None
    assert data["results"] == []
    assert data["from"] == iso(DAY0)


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_empty_range_still_reports_freshness(viewer_client, endpoint):
    state = RollupRunState.load()
    state.frequent_run_completed_at = DAY1
    state.daily_run_completed_at = DAY0
    state.save()

    data = get(viewer_client, endpoint, **RANGE).json()

    assert data["results"] == []
    assert data["data_as_of"] == iso(DAY1)
    assert data["reconciled_as_of"] == iso(DAY0)


@pytest.mark.parametrize("endpoint", ("stats-throughput", "stats-usage"))
def test_throughput_freshness_is_null_while_throughput_is_not_aggregated(
    viewer_client, stats_settings, endpoint
):
    # A run that aggregated errors only must not make throughput look fresh.
    stats_settings.STATS_THROUGHPUT_START = None
    state = RollupRunState.load()
    state.frequent_run_completed_at = DAY1
    state.daily_run_completed_at = DAY0
    state.save()

    data = get(viewer_client, endpoint, **RANGE).json()
    errors = get(viewer_client, "stats-errors", **RANGE).json()

    assert data["throughput_available_from"] is None
    assert data["data_as_of"] is None and data["reconciled_as_of"] is None
    assert errors["data_as_of"] == iso(DAY1) and errors["reconciled_as_of"] == iso(DAY0)
    assert "throughput_available_from" not in errors


def test_throughput_reports_the_time_it_is_available_from(viewer_client, stats_settings):
    stats_settings.STATS_THROUGHPUT_START = DAY0

    data = get(viewer_client, "stats-throughput", **RANGE).json()

    assert data["throughput_available_from"] == iso(DAY0)


@pytest.mark.parametrize("endpoint", ENDPOINTS)
@pytest.mark.parametrize("interval,days", [("hour", 31), ("day", 366)])
def test_range_of_exactly_the_limit_is_served_when_the_start_is_not_aligned(
    viewer_client, endpoint, interval, days
):
    end = DAY1 + datetime.timedelta(hours=13, minutes=37)
    start = end - datetime.timedelta(days=days)

    response = get(
        viewer_client, endpoint, interval=interval, from_date=start.isoformat(), to_date=end.isoformat()
    )

    assert response.status_code == status.HTTP_200_OK, response.content


def test_requests_over_a_limit_share_one_error_shape(viewer_client, provider_lotek_panthera, mocker):
    over_range = get(
        viewer_client, "stats-throughput", from_date="2026-01-01T00:00:00Z", to_date="2026-03-01T00:00:00Z"
    )
    mocker.patch.object(queries, "MAX_ROWS", 0)
    throughput_row(provider_lotek_panthera.id, Metric.RECEIVED, 1)
    over_rows = get(viewer_client, "stats-throughput", **RANGE)

    for response in (over_range, over_rows):
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert list(response.json()) == ["detail"]
        assert isinstance(response.json()["detail"], str)
    assert "31 days" in over_range.json()["detail"]
    assert "0 rows" in over_rows.json()["detail"]


@pytest.mark.parametrize("endpoint", ENDPOINTS)
@pytest.mark.parametrize("params,fragment", [
    ({"interval": "hour", "from_date": "2026-01-01T00:00:00Z", "to_date": "2026-03-01T00:00:00Z"}, "31 days"),
    ({"interval": "day", "from_date": "2024-01-01T00:00:00Z", "to_date": "2026-03-01T00:00:00Z"}, "366 days"),
])
def test_range_over_the_limit_is_rejected_with_the_limit(viewer_client, endpoint, params, fragment):
    response = get(viewer_client, endpoint, **params)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert fragment in str(response.json())


def test_row_count_over_the_limit_is_rejected_with_the_limit(viewer_client, provider_lotek_panthera, mocker):
    mocker.patch.object(queries, "MAX_ROWS", 2)
    for offset in range(3):
        throughput_row(provider_lotek_panthera.id, Metric.RECEIVED, 1, bucket=DAY0 + offset * HOUR)
        error_row(provider_lotek_panthera.id, 1, bucket=DAY0 + offset * HOUR)

    for endpoint in ("stats-throughput", "stats-errors"):
        response = get(viewer_client, endpoint, **RANGE)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "2 rows" in str(response.json())


@pytest.mark.parametrize("endpoint,params", [
    ("stats-throughput", {"group_by": "colour"}),
    ("stats-throughput", {"group_by": "origin"}),  # an errors-only dimension
    ("stats-errors", {"group_by": "destination"}),  # a throughput-only dimension
    ("stats-throughput", {"interval": "week"}),
    ("stats-throughput", {"from_date": "2026-11-20T00:00:00Z", "to_date": "2026-11-19T00:00:00Z"}),
    ("stats-throughput", {"from_date": "yesterday"}),
    ("stats-throughput", {"organization": "not-a-uuid"}),
    ("stats-errors", {"include_retriable": "maybe"}),
    ("stats-usage", {"limit": 0}),
    ("stats-usage", {"limit": 1000}),
])
def test_invalid_parameters_are_rejected(viewer_client, endpoint, params):
    assert get(viewer_client, endpoint, **params).status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_requests_never_query_the_trace_or_activity_log_tables(
    viewer_client, provider_lotek_panthera, endpoint
):
    throughput_row(provider_lotek_panthera.id, Metric.RECEIVED, 1)
    error_row(provider_lotek_panthera.id, 1)

    with CaptureQueriesContext(connection) as captured:
        response = get(
            viewer_client, endpoint, group_by="" if endpoint == "stats-usage" else "integration_type", **RANGE
        )

    assert response.status_code == status.HTTP_200_OK
    for query in captured:
        assert "gunditrace" not in query["sql"].lower()
        assert "activity_log" not in query["sql"].lower()


def test_stats_routes_appear_in_the_openapi_document(api_client, superuser):
    api_client.force_authenticate(superuser)

    document = api_client.get("/v2/swagger.json").json()

    base = document.get("basePath", "").rstrip("/")
    paths = {f"{base}{path}": spec for path, spec in document["paths"].items()}
    for path in ("/v2/stats/throughput/", "/v2/stats/errors/", "/v2/stats/usage/"):
        assert path in paths, sorted(paths)
        parameters = {p["name"] for p in paths[path]["get"]["parameters"]}
        assert {"from_date", "to_date", "interval"} <= parameters

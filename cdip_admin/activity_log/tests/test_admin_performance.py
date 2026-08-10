import pytest
from django.contrib import admin as django_admin
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from activity_log.models import ActivityLog
from integrations.models import Integration

pytestmark = pytest.mark.django_db


def _changelist_query_count(admin_client, url):
    with CaptureQueriesContext(connection) as ctx:
        response = admin_client.get(url)
    assert response.status_code == 200, response.status_code
    return len(ctx.captured_queries)


def _bulk_logs(integration, count, title_prefix="log"):
    ActivityLog.objects.bulk_create(
        [
            ActivityLog(
                log_level=ActivityLog.LogLevels.INFO,
                log_type=ActivityLog.LogTypes.EVENT,
                origin=ActivityLog.Origin.DISPATCHER,
                value=f"value_{i}",
                title=f"{title_prefix} {i}",
                integration=integration,
                details={"i": i},
                revert_data={},
            )
            for i in range(count)
        ]
    )


@pytest.fixture
def provider(organization, integration_type_er):
    return Integration.objects.create(
        type=integration_type_er,
        owner=organization,
        name="Provider",
        base_url="https://provider.example.org",
    )


def test_changelist_query_count_does_not_scale_with_row_count(admin_client, provider):
    """The changelist must not issue per-row queries.

    ``list_select_related = True`` silently skips *nullable* FKs, and both
    ``integration`` and ``created_by`` are nullable, so every displayed row
    dereferences them lazily -- and ``Integration.__str__`` then touches
    owner.name and type.name. That is ~4 queries per row on a page of 100.
    """
    url = reverse("admin:activity_log_activitylog_changelist")

    _bulk_logs(provider, 5)
    baseline = _changelist_query_count(admin_client, url)

    _bulk_logs(provider, 95, title_prefix="extra")
    after = _changelist_query_count(admin_client, url)

    assert after - baseline <= 2, (
        "ActivityLog changelist query count scales with the number of rows: "
        f"{baseline} queries -> {after} queries after adding 95 more logs. "
        "list_select_related must name the nullable FKs explicitly."
    )


def test_changelist_query_count_does_not_scale_with_integration_count(
    admin_client, provider, organization, integration_type_er
):
    """The 'integration' sidebar filter builds a dropdown of every Integration.

    RelatedFieldListFilter renders ``str(obj)`` per option, and
    ``Integration.__str__`` dereferences owner and type without
    select_related, so drawing the sidebar costs 2 queries per integration
    on every changelist render.
    """
    url = reverse("admin:activity_log_activitylog_changelist")
    _bulk_logs(provider, 5)

    baseline = _changelist_query_count(admin_client, url)

    Integration.objects.bulk_create(
        [
            Integration(
                type=integration_type_er,
                owner=organization,
                name=f"Bulk Integration {i}",
                base_url=f"https://bulk-{i}.example.org",
            )
            for i in range(100)
        ]
    )

    after = _changelist_query_count(admin_client, url)

    assert after - baseline <= 2, (
        "ActivityLog changelist query count scales with the number of "
        f"integrations: {baseline} -> {after} after adding 100 integrations. "
        "The integration filter must select_related its choice queryset."
    )


def test_changelist_does_not_use_date_hierarchy(admin_client):
    """``date_hierarchy`` issues ``SELECT DISTINCT DATE_TRUNC(...)`` over the
    whole filtered queryset on every render. Postgres has no skip scan, so
    that is an unavoidable sequential scan of every partition -- measured at
    3,677 buffers / 131ms per 500k rows, and linear in table size.

    Timeframe filtering is provided by a date filter instead, which builds
    its links from the clock rather than from the table.
    """
    model_admin = django_admin.site._registry[ActivityLog]
    assert model_admin.date_hierarchy is None

    filter_targets = [
        spec[0] if isinstance(spec, (tuple, list)) else spec
        for spec in model_admin.list_filter
    ]
    assert "created_at" in filter_targets, (
        "Removing date_hierarchy must not remove the ability to filter by "
        "timeframe -- expected 'created_at' in list_filter."
    )


def test_changelist_does_not_render_json_blobs_per_row(admin_client):
    """``details`` and ``revert_data`` are JSONFields. Rendering them for
    every row turns the changelist HTML into megabytes of serialized JSON.
    They remain on the detail page.
    """
    model_admin = django_admin.site._registry[ActivityLog]
    assert "details" not in model_admin.list_display
    assert "revert_data" not in model_admin.list_display

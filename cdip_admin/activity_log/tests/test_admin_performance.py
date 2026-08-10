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


def test_integration_filter_does_not_render_an_option_per_integration(
    admin_client, provider, organization, integration_type_er
):
    """The sidebar must not enumerate the Integration table.

    Selecting every integration in one query (rather than two per option) is
    not enough: the filter still emits an ``<option>`` per integration, so the
    changelist HTML -- and the browser's parse cost -- grows without bound as
    integrations are added. Measured at ~168 bytes per integration, which is
    185 KB of markup at 1,200 integrations. The autocomplete widget renders
    only the currently selected option and fetches the rest over AJAX.
    """
    url = reverse("admin:activity_log_activitylog_changelist")
    _bulk_logs(provider, 5)

    baseline = len(admin_client.get(url).content)

    Integration.objects.bulk_create(
        [
            Integration(
                type=integration_type_er,
                owner=organization,
                name=f"Bulk Integration {i}",
                base_url=f"https://bulk-{i}.example.org",
            )
            for i in range(200)
        ]
    )

    after = len(admin_client.get(url).content)

    assert after - baseline < 2000, (
        "Changelist HTML grows with the number of integrations: "
        f"{baseline} bytes -> {after} bytes after adding 200 integrations. "
        "The integration filter must not render an option per integration."
    )


def test_integration_filter_renders_autocomplete_widget(admin_client, provider):
    """The filter renders Django's AutocompleteSelect, which is what makes the
    option list lazy. Asserting on the rendered markup rather than the filter
    class keeps this honest about what the browser actually receives.
    """
    url = reverse("admin:activity_log_activitylog_changelist")
    _bulk_logs(provider, 5)

    content = admin_client.get(url).content.decode()

    assert "admin-autocomplete" in content
    assert 'data-app-label="activity_log"' in content
    assert 'data-model-name="activitylog"' in content
    assert 'data-field-name="integration"' in content


def test_integration_filter_ships_the_select2_assets(admin_client, provider):
    """Django collects media from the admin and its forms but not from list
    filters, so the select2 assets have to be contributed by the ModelAdmin.
    Without them the widget renders as an inert <select> that still works but
    silently loses the type-ahead.
    """
    url = reverse("admin:activity_log_activitylog_changelist")
    _bulk_logs(provider, 5)

    content = admin_client.get(url).content.decode()

    assert "autocomplete.js" in content
    assert "select2" in content


def test_admin_autocomplete_endpoint_serves_the_integration_filter(
    admin_client, provider
):
    """The built-in /admin/autocomplete/ endpoint must answer for this filter.

    Django validates the request against the *source* field and the related
    model's admin (which needs search_fields); it does not require the field
    to appear in any ModelAdmin.autocomplete_fields. This test pins that,
    because the whole approach depends on it and a future Django release
    tightening the check would break the filter silently.
    """
    response = admin_client.get(
        reverse("admin:autocomplete"),
        {
            "app_label": "activity_log",
            "model_name": "activitylog",
            "field_name": "integration",
            "term": "Provider",
        },
    )

    assert response.status_code == 200, response.status_code
    results = response.json()["results"]
    assert str(provider.pk) in [r["id"] for r in results]


def test_integration_filter_preserves_other_active_filters(admin_client, provider):
    """The filter submits a GET form, so every other active parameter has to
    ride along as a hidden input or choosing an integration would silently
    drop the search term, the date filter and the ordering.
    """
    url = reverse("admin:activity_log_activitylog_changelist")
    _bulk_logs(provider, 5)

    content = admin_client.get(url, {"log_level__exact": "20", "q": "log"}).content.decode()

    assert '<input type="hidden" name="log_level__exact" value="20">' in content
    assert '<input type="hidden" name="q" value="log">' in content


def test_integration_filter_is_submittable_without_javascript(admin_client, provider):
    """Auto-submit-on-change depends on select2 re-dispatching the event, which
    cannot be verified without a browser. An explicit submit control keeps the
    filter usable regardless.
    """
    url = reverse("admin:activity_log_activitylog_changelist")
    _bulk_logs(provider, 5)

    content = admin_client.get(url).content.decode()

    assert '<form method="get" class="autocomplete-filter">' in content
    assert '<button type="submit">' in content


def test_integration_filter_offers_the_no_integration_option(admin_client, provider):
    """``ActivityLog.integration`` is nullable with ``on_delete=SET_NULL``, so
    orphaned logs really do accumulate. ``RelatedFieldListFilter`` offers an
    empty choice for exactly this case; replacing its ``choices()`` must not
    quietly drop the ability to find those rows.
    """
    url = reverse("admin:activity_log_activitylog_changelist")
    _bulk_logs(provider, 3)

    content = admin_client.get(url).content.decode()

    assert "integration__isnull=True" in content


def test_integration_filter_no_integration_option_selects_orphaned_logs(
    admin_client, provider
):
    """The empty choice must actually filter, not just render."""
    url = reverse("admin:activity_log_activitylog_changelist")
    _bulk_logs(provider, 3, title_prefix="has integration")
    ActivityLog.objects.create(
        log_level=ActivityLog.LogLevels.INFO,
        log_type=ActivityLog.LogTypes.EVENT,
        origin=ActivityLog.Origin.DISPATCHER,
        value="orphan",
        title="orphaned log",
        integration=None,
        details={},
        revert_data={},
    )

    content = admin_client.get(url, {"integration__isnull": "True"}).content.decode()

    assert "orphaned log" in content
    assert "has integration" not in content


def test_integration_filter_choices_offer_all_and_none(rf, admin_user):
    """Assert on the filter's own choices rather than the rendered page: every
    other sidebar filter also renders an "All" link, so a raw HTML search for
    one passes even when this filter offers nothing.
    """
    model_admin = django_admin.site._registry[ActivityLog]
    request = rf.get("/admin/")
    request.user = admin_user
    changelist = model_admin.get_changelist_instance(request)
    spec = next(
        s
        for s in changelist.filter_specs
        if getattr(s, "field", None) is not None and s.field.name == "integration"
    )

    links = list(spec.choices(changelist))[0]["links"]
    displays = [link["display"] for link in links]

    assert "All" in displays
    assert model_admin.get_empty_value_display() in displays

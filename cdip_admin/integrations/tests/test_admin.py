import pytest
from django.contrib import admin as django_admin
from django.contrib.admin.widgets import AutocompleteSelect, RelatedFieldWidgetWrapper
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from integrations.models import Integration

pytestmark = pytest.mark.django_db


def _render_query_count(admin_client, url):
    with CaptureQueriesContext(connection) as ctx:
        response = admin_client.get(url)
    assert response.status_code == 200, response.status_code
    return len(ctx.captured_queries)


def test_route_change_page_does_not_scale_with_integration_count(
    admin_client, route_1, organization, integration_type_er
):
    """The Route change page renders RouteProvider/RouteDestination inlines.

    Without autocomplete_fields, each inline renders a <select> of *every*
    Integration, and Integration.__str__ touches owner.name and type.name
    (neither select_related), so building the dropdowns is an N+1 storm whose
    cost grows with the number of integrations -- the cause of the timeout.
    The query count must stay flat as integrations are added.
    """
    url = reverse("admin:integrations_route_change", args=[route_1.pk])

    baseline = _render_query_count(admin_client, url)

    # bulk_create bypasses save hooks/dispatcher deployment -- we only need
    # rows that would populate the inline FK dropdowns.
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

    after = _render_query_count(admin_client, url)

    assert after - baseline <= 10, (
        "Route change page query count scales with integration count: "
        f"{baseline} queries -> {after} queries after adding 100 integrations. "
        "Inline FK fields should use autocomplete_fields."
    )


def test_route_change_page_owner_and_configuration_use_autocomplete(
    admin_client, route_2
):
    """owner/configuration must render as autocomplete widgets rather than
    dropdowns that eagerly load every Organization/RouteConfiguration."""
    url = reverse("admin:integrations_route_change", args=[route_2.pk])
    response = admin_client.get(url)
    assert response.status_code == 200

    form = response.context["adminform"].form

    def unwrap(widget):
        # Admin wraps FK widgets in RelatedFieldWidgetWrapper (the +/edit icons).
        return widget.widget if isinstance(widget, RelatedFieldWidgetWrapper) else widget

    assert isinstance(unwrap(form.fields["owner"].widget), AutocompleteSelect)
    assert isinstance(unwrap(form.fields["configuration"].widget), AutocompleteSelect)


def _changelist_query_count(admin_client, url):
    with CaptureQueriesContext(connection) as ctx:
        response = admin_client.get(url)
    assert response.status_code == 200, response.status_code
    return len(ctx.captured_queries)


@pytest.fixture
def trace_fixtures(organization, integration_type_er):
    from integrations.models import Source

    provider = Integration.objects.create(
        type=integration_type_er, owner=organization,
        name="Trace Provider", base_url="https://provider.example.org",
    )
    destination = Integration.objects.create(
        type=integration_type_er, owner=organization,
        name="Trace Destination", base_url="https://destination.example.org",
    )
    source = Source.objects.create(external_id="source-1", integration=provider)
    return provider, destination, source


def _bulk_traces(provider, destination, source, count):
    from integrations.models import GundiTrace

    GundiTrace.objects.bulk_create(
        [
            GundiTrace(
                object_type="ev", data_provider=provider,
                destination=destination, source=source,
                external_id=f"external-{i}",
            )
            for i in range(count)
        ]
    )


def test_gundi_trace_changelist_query_count_does_not_scale_with_row_count(
    admin_client, trace_fixtures
):
    """The GundiTrace changelist must not issue per-row queries.

    ``list_select_related = True`` follows only non-nullable FKs, so
    ``destination``, ``source`` and ``created_by`` are all dereferenced
    lazily -- and Integration/Source ``__str__`` then walk owner, type and
    integration. That was measured at ~7 queries per row.
    """
    provider, destination, source = trace_fixtures
    url = reverse("admin:integrations_gunditrace_changelist")

    _bulk_traces(provider, destination, source, 5)
    baseline = _changelist_query_count(admin_client, url)

    _bulk_traces(provider, destination, source, 95)
    after = _changelist_query_count(admin_client, url)

    assert after - baseline <= 2, (
        "GundiTrace changelist query count scales with the number of rows: "
        f"{baseline} queries -> {after} queries after adding 95 more traces."
    )


def test_gundi_trace_changelist_does_not_use_date_hierarchy(admin_client):
    """date_hierarchy runs ``SELECT DISTINCT DATE_TRUNC(...)`` over the whole
    queryset on every render -- a sequential scan of the largest table in the
    database. A date filter provides timeframe filtering without aggregating.
    """
    from integrations.models import GundiTrace

    model_admin = django_admin.site._registry[GundiTrace]
    assert model_admin.date_hierarchy is None

    filter_targets = [
        spec[0] if isinstance(spec, (tuple, list)) else spec
        for spec in model_admin.list_filter
    ]
    assert "created_at" in filter_targets, (
        "Removing date_hierarchy must not remove timeframe filtering -- "
        "expected 'created_at' in list_filter."
    )


def test_gundi_trace_changelist_does_not_render_error_text_per_row(admin_client):
    """``error`` holds up to 500 characters. Rendering it for every row bloats
    the changelist HTML; it stays on the detail page. ``has_error`` remains as
    the scannable indicator.
    """
    from integrations.models import GundiTrace

    model_admin = django_admin.site._registry[GundiTrace]
    assert "error" not in model_admin.list_display
    assert "has_error" in model_admin.list_display

import pytest
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

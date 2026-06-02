import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from integrations.models import Integration

pytestmark = pytest.mark.django_db


def _render_route_change(admin_client, route):
    url = reverse("admin:integrations_route_change", args=[route.pk])
    with CaptureQueriesContext(connection) as ctx:
        response = admin_client.get(url)
    assert response.status_code == 200
    return response, len(ctx.captured_queries)


def _queries_to_render_route_change(admin_client, route):
    return _render_route_change(admin_client, route)[1]


def test_route_change_page_uses_autocomplete_for_integration_inlines(
    admin_client, route_2
):
    """The inline integration field must render as an AJAX autocomplete widget,
    not an eager <select> of every Integration."""
    response, _ = _render_route_change(admin_client, route_2)
    html = response.content.decode()
    # Django renders autocomplete_fields with the ``admin-autocomplete`` class.
    assert "admin-autocomplete" in html


def test_route_change_page_query_count_does_not_scale_with_integrations(
    admin_client, route_2, integration_type_er, organization
):
    """Regression test for the Route admin change page timing out.

    The inline integration FK must not render an eager <select> of every
    Integration. Because ``Integration.__str__`` dereferences ``owner`` and
    ``type``, an eager dropdown triggers an N+1 query per option, per inline
    row, which made the page time out in production. The query count to render
    the page must therefore be constant with respect to the size of the
    Integration table.
    """
    baseline = _queries_to_render_route_change(admin_client, route_2)

    # Grow the Integration table substantially.
    for i in range(25):
        Integration.objects.create(
            type=integration_type_er,
            name=f"Extra ER Site {i}",
            owner=organization,
            base_url=f"extra-{i}.pamdas.org",
        )

    after = _queries_to_render_route_change(admin_client, route_2)

    assert after <= baseline, (
        "Route admin change page query count scaled with the Integration "
        f"table size ({baseline} -> {after} queries). The inline integration "
        "field is rendering an eager dropdown (N+1 via Integration.__str__)."
    )

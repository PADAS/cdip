import pytest
from django.contrib import admin as django_admin
from django.contrib.admin.widgets import AutocompleteSelect, RelatedFieldWidgetWrapper
from django.db import connection
from django.forms.models import inlineformset_factory
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from integrations.models import Integration, Route, RouteProvider, RouteDestination

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
    baseline = _render_query_count(admin_client, url)

    _bulk_traces(provider, destination, source, 95)
    after = _render_query_count(admin_client, url)

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


def test_gundi_trace_type_filters_have_distinguishable_titles(
    admin_client, trace_fixtures
):
    """``data_provider__type`` and ``destination__type`` both point at
    IntegrationType, so both inherit its verbose name and the sidebar renders
    two identical "By Integration Type" panels with no way to tell which one
    filters the provider and which the destination.

    Needs two IntegrationTypes: a related-field filter offering fewer than two
    choices is hidden, so with one type the duplication does not appear.
    """
    from integrations.models import IntegrationType

    IntegrationType.objects.create(name="Second Type", value="second_type")
    provider, destination, source = trace_fixtures
    _bulk_traces(provider, destination, source, 2)

    url = reverse("admin:integrations_gunditrace_changelist")
    content = admin_client.get(url).content.decode()

    assert content.count("By Integration Type") == 0, (
        "The sidebar renders duplicate 'By Integration Type' filters; the "
        "provider and destination type filters need distinct titles."
    )
    # Assert the replacements are present too: a bare "no duplicates" check
    # would also pass if both filters disappeared altogether.
    assert "By Provider type" in content
    assert "By Destination type" in content


# --- default route refusals ----------------------------------------------------

@pytest.fixture
def ambiguous_provider(organization, integration_type_lotek, integrations_list_er):
    provider = Integration.objects.create(
        type=integration_type_lotek, owner=organization, name="Ambiguous", base_url="https://api.test.lotek.com",
    )
    routes = []
    for name in ("R1", "R2", "R3"):
        route = Route.objects.create(owner=organization, name=name)
        RouteProvider.objects.bulk_create([RouteProvider(integration=provider, route=route)])
        RouteDestination.objects.bulk_create([RouteDestination(integration=integrations_list_er[0], route=route)])
        routes.append(route)
    Integration.objects.filter(pk=provider.pk).update(default_route=routes[0])
    provider.refresh_from_db()
    return provider, routes


def test_admin_delete_of_ambiguous_default_route_is_refused_with_message(admin_client, ambiguous_provider):
    provider, (r1, r2, r3) = ambiguous_provider
    url = reverse("admin:integrations_route_delete", args=[r1.pk])

    response = admin_client.post(url, {"post": "yes"}, follow=True)

    assert response.status_code == 200
    messages = [str(m) for m in response.context["messages"]]
    assert any("Cannot choose a default route" in m and r2.name in m and r3.name in m for m in messages), messages
    assert not any("deleted successfully" in m for m in messages), messages
    assert Route.objects.filter(pk=r1.pk).exists()
    provider.refresh_from_db()
    assert provider.default_route == r1


def test_admin_bulk_delete_of_ambiguous_default_route_deletes_nothing(admin_client, ambiguous_provider):
    """Bulk-deleting R1 alone leaves R2 and R3 as candidates → refused.
    (Selecting R1 *and* R2 would leave only R3 and legitimately succeed.)"""
    provider, (r1, r2, r3) = ambiguous_provider
    url = reverse("admin:integrations_route_changelist")

    response = admin_client.post(
        url,
        {"action": "delete_selected", "_selected_action": [str(r1.pk)], "post": "yes"},
        follow=True,
    )

    assert response.status_code == 200
    assert Route.objects.filter(pk=r1.pk).exists()
    messages = [str(m) for m in response.context["messages"]]
    assert any("Cannot choose a default route" in m for m in messages), messages
    assert not any("Successfully deleted" in m for m in messages), messages


def test_admin_delete_refused_from_pre_delete_path_deletes_nothing(admin_client, organization, integration_type_lotek, integrations_list_er):
    """default NULL, provider on R1, R2, R3 (all delivering): deleting R1 passes collection
    (default is not R1) and is refused from pre_delete(RouteProvider) → delete_model's savepoint."""
    provider = Integration.objects.create(type=integration_type_lotek, owner=organization, name="Null default", base_url="https://api.test.lotek.com")
    routes = []
    for name in ("R1", "R2", "R3"):
        r = Route.objects.create(owner=organization, name=name)
        RouteProvider.objects.bulk_create([RouteProvider(integration=provider, route=r)])
        RouteDestination.objects.bulk_create([RouteDestination(integration=integrations_list_er[0], route=r)])
        routes.append(r)
    url = reverse("admin:integrations_route_delete", args=[routes[0].pk])

    response = admin_client.post(url, {"post": "yes"}, follow=True)

    assert response.status_code == 200
    assert Route.objects.filter(pk=routes[0].pk).exists()
    messages = [str(m) for m in response.context["messages"]]
    assert any("Cannot choose a default route" in m for m in messages), messages
    assert not any("deleted successfully" in m for m in messages), messages


def test_provider_inline_formset_refuses_ambiguous_removal(ambiguous_provider):
    from integrations.admin import RouteProviderInlineFormSet
    provider, (r1, r2, r3) = ambiguous_provider
    link = RouteProvider.objects.get(integration=provider, route=r1)
    FormSet = inlineformset_factory(
        Route, RouteProvider, formset=RouteProviderInlineFormSet, fields=("integration",), extra=0, can_delete=True,
    )
    prefix = FormSet.get_default_prefix()
    data = {
        f"{prefix}-TOTAL_FORMS": "1", f"{prefix}-INITIAL_FORMS": "1",
        f"{prefix}-MIN_NUM_FORMS": "0", f"{prefix}-MAX_NUM_FORMS": "1000",
        f"{prefix}-0-id": str(link.pk), f"{prefix}-0-integration": str(provider.pk), f"{prefix}-0-DELETE": "on",
    }

    formset = FormSet(data, instance=r1)

    assert not formset.is_valid()
    assert any("Cannot choose a default route" in e for e in formset.non_form_errors())
    assert RouteProvider.objects.filter(pk=link.pk).exists()


def test_provider_inline_formset_allows_unambiguous_removal(organization, integration_type_lotek, integrations_list_er):
    from integrations.admin import RouteProviderInlineFormSet
    provider = Integration.objects.create(
        type=integration_type_lotek, owner=organization, name="Two routes", base_url="https://api.test.lotek.com",
    )
    r1, r2 = (Route.objects.create(owner=organization, name=n) for n in ("R1", "R2"))
    RouteProvider.objects.bulk_create([RouteProvider(integration=provider, route=r) for r in (r1, r2)])
    RouteDestination.objects.bulk_create([RouteDestination(integration=integrations_list_er[0], route=r) for r in (r1, r2)])
    Integration.objects.filter(pk=provider.pk).update(default_route=r1)
    link = RouteProvider.objects.get(integration=provider, route=r1)
    FormSet = inlineformset_factory(
        Route, RouteProvider, formset=RouteProviderInlineFormSet, fields=("integration",), extra=0, can_delete=True,
    )
    prefix = FormSet.get_default_prefix()
    data = {
        f"{prefix}-TOTAL_FORMS": "1", f"{prefix}-INITIAL_FORMS": "1",
        f"{prefix}-MIN_NUM_FORMS": "0", f"{prefix}-MAX_NUM_FORMS": "1000",
        f"{prefix}-0-id": str(link.pk), f"{prefix}-0-integration": str(provider.pk), f"{prefix}-0-DELETE": "on",
    }

    formset = FormSet(data, instance=r1)

    assert formset.is_valid(), formset.errors
    formset.save()
    provider.refresh_from_db()
    assert provider.default_route == r2


def test_integration_admin_form_refuses_ambiguous_default_route(organization, integration_type_lotek, integrations_list_er):
    from integrations.admin import IntegrationAdminForm
    provider = Integration.objects.create(type=integration_type_lotek, owner=organization, name="Two delivering", base_url="https://api.test.lotek.com")
    empty = Route.objects.create(owner=organization, name="Empty")
    for name in ("R1", "R2"):
        r = Route.objects.create(owner=organization, name=name)
        RouteProvider.objects.bulk_create([RouteProvider(integration=provider, route=r)])
        RouteDestination.objects.bulk_create([RouteDestination(integration=integrations_list_er[0], route=r)])

    form = IntegrationAdminForm(instance=provider, data={
        "type": str(provider.type_id), "owner": str(provider.owner_id), "name": provider.name,
        "base_url": provider.base_url, "enabled": "on", "default_route": str(empty.pk), "additional": "{}",
    })

    assert not form.is_valid()
    assert any("Cannot choose a default route" in e for e in form.errors["default_route"])


def test_provider_inline_formset_refuses_ambiguous_addition(organization, integration_type_lotek, integrations_list_er):
    from integrations.admin import RouteProviderInlineFormSet
    provider = Integration.objects.create(type=integration_type_lotek, owner=organization, name="Two delivering", base_url="https://api.test.lotek.com")
    placeholder = Route.objects.create(owner=organization, name="Placeholder")
    RouteProvider.objects.bulk_create([RouteProvider(integration=provider, route=placeholder)])
    for name in ("R1", "R2"):
        r = Route.objects.create(owner=organization, name=name)
        RouteProvider.objects.bulk_create([RouteProvider(integration=provider, route=r)])
        RouteDestination.objects.bulk_create([RouteDestination(integration=integrations_list_er[0], route=r)])
    Integration.objects.filter(pk=provider.pk).update(default_route=placeholder)
    new_empty = Route.objects.create(owner=organization, name="New empty")
    FormSet = inlineformset_factory(Route, RouteProvider, formset=RouteProviderInlineFormSet, fields=("integration",), extra=1, can_delete=True)
    prefix = FormSet.get_default_prefix()
    data = {
        f"{prefix}-TOTAL_FORMS": "1", f"{prefix}-INITIAL_FORMS": "0",
        f"{prefix}-MIN_NUM_FORMS": "0", f"{prefix}-MAX_NUM_FORMS": "1000",
        f"{prefix}-0-integration": str(provider.pk),
    }

    formset = FormSet(data, instance=new_empty)

    assert not formset.is_valid()
    assert any("Cannot choose a default route" in e for e in formset.non_form_errors())


# --- default route visibility: IntegrationAdmin ---------------------------------

@pytest.fixture
def mock_api_key_column(mocker, mock_get_api_key):
    """IntegrationAdmin.list_display renders ``api_key``, which calls Kong per row."""
    mocker.patch("integrations.models.v2.models.Integration.api_key", mock_get_api_key)


@pytest.fixture
def visibility_zoo(organization, integration_type_lotek, integrations_list_er):
    def provider(name):
        return Integration.objects.create(
            type=integration_type_lotek, owner=organization, name=name, base_url="https://api.test.lotek.com",
        )

    def route(name, providers=(), destinations=()):
        r = Route.objects.create(owner=organization, name=name)
        RouteProvider.objects.bulk_create([RouteProvider(integration=p, route=r) for p in providers])
        RouteDestination.objects.bulk_create([RouteDestination(integration=d, route=r) for d in destinations])
        return r

    er = integrations_list_er[0]
    valid = provider("Valid provider")
    valid_route = route("Valid route", providers=[valid], destinations=[er])
    Integration.objects.filter(pk=valid.pk).update(default_route=valid_route)

    missing = provider("Missing provider")
    route("Missing route", providers=[missing], destinations=[er])

    not_member = provider("Not-member provider")
    route("NM route", providers=[not_member], destinations=[er])
    Integration.objects.filter(pk=not_member.pk).update(default_route=route("Orphan route"))

    empty = provider("Empty-default provider")
    Integration.objects.filter(pk=empty.pk).update(default_route=route("Placeholder", providers=[empty]))
    route("Real route", providers=[empty], destinations=[er])

    return {"valid": valid, "valid_route": valid_route, "missing": missing, "not_member": not_member, "empty": empty, "er": er}


@pytest.mark.parametrize("state, key", [
    ("missing", "missing"), ("not_member", "not_member"), ("empty_default", "empty"),
])
def test_integration_changelist_default_route_filter_isolates_each_violation(admin_client, mock_api_key_column, visibility_zoo, state, key):
    url = reverse("admin:integrations_integration_changelist") + f"?default_route_state={state}"

    response = admin_client.get(url)

    assert response.status_code == 200
    assert {obj.pk for obj in response.context["cl"].queryset} == {visibility_zoo[key].pk}


def test_integration_changelist_default_route_filter_valid_excludes_violators(admin_client, mock_api_key_column, visibility_zoo):
    url = reverse("admin:integrations_integration_changelist") + "?default_route_state=valid"

    response = admin_client.get(url)

    pks = {obj.pk for obj in response.context["cl"].queryset}
    assert visibility_zoo["valid"].pk in pks
    assert not ({visibility_zoo["missing"].pk, visibility_zoo["not_member"].pk, visibility_zoo["empty"].pk} & pks)


def test_integration_changelist_shows_default_route_as_link(admin_client, mock_api_key_column, visibility_zoo):
    url = reverse("admin:integrations_integration_changelist") + f"?q={visibility_zoo['valid'].name}"

    content = admin_client.get(url).content.decode()

    assert reverse("admin:integrations_route_change", args=[visibility_zoo["valid_route"].pk]) in content
    assert "Valid route" in content


def test_integration_changelist_query_count_does_not_scale_with_rows(admin_client, mock_api_key_column, visibility_zoo, organization, integration_type_lotek):
    url = reverse("admin:integrations_integration_changelist")
    baseline = _render_query_count(admin_client, url)

    route = Route.objects.create(owner=organization, name="Shared default")
    Integration.objects.bulk_create([
        Integration(type=integration_type_lotek, owner=organization, name=f"Bulk {i}",
                    base_url="https://api.test.lotek.com", default_route=route)
        for i in range(60)
    ])

    after = _render_query_count(admin_client, url)
    assert after - baseline <= 2, f"{baseline} -> {after} queries after adding 60 integrations"


def test_integration_change_page_shows_route_panels(admin_client, visibility_zoo):
    url = reverse("admin:integrations_integration_change", args=[visibility_zoo["empty"].pk])

    content = admin_client.get(url).content.decode()

    assert "Routes as provider" in content
    assert "★" in content                                   # the default is marked
    assert "Placeholder" in content and "Real route" in content
    assert visibility_zoo["er"].name in content             # destinations listed under the real route


def test_integration_change_page_destination_panel_lists_providers(admin_client, visibility_zoo):
    url = reverse("admin:integrations_integration_change", args=[visibility_zoo["er"].pk])

    content = admin_client.get(url).content.decode()

    assert "Routes as destination" in content
    assert "Valid provider" in content


def test_integration_change_page_query_count_does_not_scale_with_route_count(admin_client, visibility_zoo, organization):
    provider = visibility_zoo["empty"]
    url = reverse("admin:integrations_integration_change", args=[provider.pk])
    baseline = _render_query_count(admin_client, url)

    routes = Route.objects.bulk_create([Route(owner=organization, name=f"Bulk route {i}") for i in range(20)])
    RouteProvider.objects.bulk_create([RouteProvider(integration=provider, route=r) for r in routes])
    RouteDestination.objects.bulk_create([RouteDestination(integration=visibility_zoo["er"], route=r) for r in routes])

    after = _render_query_count(admin_client, url)
    assert after - baseline <= 2, f"{baseline} -> {after} queries after adding 20 routes"


def test_integration_change_page_default_route_uses_autocomplete(admin_client, visibility_zoo):
    url = reverse("admin:integrations_integration_change", args=[visibility_zoo["valid"].pk])
    response = admin_client.get(url)
    form = response.context["adminform"].form

    widget = form.fields["default_route"].widget
    if isinstance(widget, RelatedFieldWidgetWrapper):
        widget = widget.widget
    assert isinstance(widget, AutocompleteSelect)


# --- default route visibility: RouteAdmin ---------------------------------------

def test_route_changelist_shows_owner_providers_destinations_and_default_for(admin_client, visibility_zoo):
    url = reverse("admin:integrations_route_changelist") + "?q=Valid+route"

    content = admin_client.get(url).content.decode()

    assert visibility_zoo["valid"].owner.name in content
    assert "Valid provider" in content
    assert visibility_zoo["er"].name in content
    assert "Default for" in content


def test_route_changelist_query_count_does_not_scale_with_rows(admin_client, visibility_zoo, organization, integration_type_lotek):
    """The three new columns must not add per-row queries.

    Each Route row already costs one query on this codebase: Route.__init__
    runs ChangeLogMixin, which resolves ``first_provider`` eagerly. That is
    pre-existing and allowed for here (+1 per added route); the prefetched
    columns themselves must add nothing per row.
    """
    added = 40
    url = reverse("admin:integrations_route_changelist")
    baseline = _render_query_count(admin_client, url)

    routes = Route.objects.bulk_create([Route(owner=organization, name=f"Bulk route {i}") for i in range(added)])
    RouteProvider.objects.bulk_create([RouteProvider(integration=visibility_zoo["valid"], route=r) for r in routes])
    RouteDestination.objects.bulk_create([RouteDestination(integration=visibility_zoo["er"], route=r) for r in routes])

    after = _render_query_count(admin_client, url)
    assert after - baseline <= added + 2, f"{baseline} -> {after} queries after adding {added} routes"


def test_route_change_page_shows_default_route_for_panel(admin_client, visibility_zoo):
    url = reverse("admin:integrations_route_change", args=[visibility_zoo["valid_route"].pk])

    content = admin_client.get(url).content.decode()

    assert "Default route for" in content
    assert "Valid provider" in content
    assert reverse("admin:integrations_integration_change", args=[visibility_zoo["valid"].pk]) in content

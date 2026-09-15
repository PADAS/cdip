import pytest
from django.urls import reverse
from rest_framework import status

from integrations.models import Source, SourceFilter

pytestmark = pytest.mark.django_db


def _list_url(route):
    return reverse("filters-list", kwargs={"route_pk": str(route.id)})


def _detail_url(route, source_filter):
    return reverse(
        "filters-detail",
        kwargs={"route_pk": str(route.id), "pk": str(source_filter.id)},
    )


def _payload(destination, sources, mode="whitelist", **overrides):
    payload = {
        "destination": str(destination.id),
        "mode": mode,
        "source_ids": [str(s.id) for s in sources],
    }
    payload.update(overrides)
    return payload


def _post(api_client, user, route, payload):
    api_client.force_authenticate(user)
    return api_client.post(_list_url(route), data=payload, format="json")


# ---- Reading --------------------------------------------------------------


@pytest.mark.parametrize("user_fixture", ["superuser", "org_admin_user", "org_viewer_user"])
def test_list_filters(
        request, api_client, organization, route_1, lotek_sources,
        provider_lotek_panthera, user_fixture
):
    user = request.getfixturevalue(user_fixture)
    api_client.force_authenticate(user)
    response = api_client.get(_list_url(route_1))

    assert response.status_code == status.HTTP_200_OK, response.content
    results = response.json()["results"]
    assert len(results) == 1
    rule = results[0]
    assert rule["mode"] == "whitelist"
    assert rule["type"] == "list"
    assert rule["enabled"] is True
    assert rule["updated_at"]
    # The destination is summarised, not expanded — the UI already knows the route's
    # destinations from the flow map and only needs to match the rule to an arrow.
    assert set(rule["destination"]) == {"id", "name"}
    # Sources are paged from their own endpoint, so only the count and the providers the
    # rule covers travel with the rule itself.
    assert "sources" not in rule
    assert rule["sources_count"] == len(lotek_sources)
    assert [p["id"] for p in rule["providers"]] == [str(provider_lotek_panthera.id)]


def test_cannot_list_filters_of_another_org_route(
        api_client, org_admin_user, organization, other_organization, route_2
):
    api_client.force_authenticate(org_admin_user)
    response = api_client.get(_list_url(route_2))
    assert response.status_code in (
        status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND
    ), response.content


# ---- Creating -------------------------------------------------------------


@pytest.mark.parametrize("user_fixture", ["superuser", "org_admin_user"])
def test_create_filter(
        request, api_client, organization, route_1, integrations_list_er, lotek_sources, user_fixture
):
    user = request.getfixturevalue(user_fixture)
    # route_1 already carries a filter on integrations_list_er[0]; use a free destination.
    destination = integrations_list_er[1]
    response = _post(api_client, user, route_1, _payload(destination, lotek_sources[:2]))

    assert response.status_code == status.HTTP_201_CREATED, response.content
    created = SourceFilter.objects.get(id=response.json()["id"])
    assert created.routing_rule_id == route_1.id
    assert created.destination_id == destination.id
    assert created.mode == SourceFilter.FilterModes.WHITELIST
    assert created.type == SourceFilter.SourceFilterTypes.SOURCE_LIST
    assert set(created.sources.values_list("id", flat=True)) == {s.id for s in lotek_sources[:2]}


def test_create_blacklist_filter(
        api_client, superuser, organization, route_1, integrations_list_er, lotek_sources
):
    response = _post(
        api_client, superuser, route_1,
        _payload(integrations_list_er[1], lotek_sources[:1], mode="blacklist"),
    )
    assert response.status_code == status.HTTP_201_CREATED, response.content
    assert response.json()["mode"] == "blacklist"


def test_cannot_create_filter_as_org_viewer(
        api_client, org_viewer_user, organization, route_1, integrations_list_er, lotek_sources
):
    response = _post(
        api_client, org_viewer_user, route_1, _payload(integrations_list_er[1], lotek_sources[:1])
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN, response.content


def test_cannot_create_filter_on_another_org_route(
        api_client, org_admin_user, organization, other_organization, route_2,
        integrations_list_er, movebank_sources
):
    response = _post(
        api_client, org_admin_user, route_2, _payload(integrations_list_er[5], movebank_sources[:1])
    )
    assert response.status_code in (
        status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND
    ), response.content


# ---- Validation -----------------------------------------------------------


def test_reject_empty_source_list(
        api_client, superuser, organization, route_1, integrations_list_er
):
    response = _post(api_client, superuser, route_1, _payload(integrations_list_er[1], []))
    assert response.status_code == status.HTTP_400_BAD_REQUEST, response.content
    assert "at least one source" in response.content.decode().lower()


def test_reject_destination_not_on_the_route(
        api_client, superuser, organization, route_1, provider_movebank_ewt, lotek_sources
):
    # provider_movebank_ewt is a real integration, just not a destination of this route.
    response = _post(
        api_client, superuser, route_1, _payload(provider_movebank_ewt, lotek_sources[:1])
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST, response.content
    assert "not one of the route" in response.content.decode()


def test_reject_sources_from_a_provider_not_on_the_route(
        api_client, superuser, organization, other_organization, route_1,
        integrations_list_er, movebank_sources
):
    response = _post(
        api_client, superuser, route_1, _payload(integrations_list_er[1], movebank_sources[:1])
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST, response.content
    assert "not on this route" in response.content.decode()


def test_reject_unknown_source(
        api_client, superuser, organization, route_1, integrations_list_er
):
    api_client.force_authenticate(superuser)
    response = api_client.post(
        _list_url(route_1),
        data={
            "destination": str(integrations_list_er[1].id),
            "mode": "whitelist",
            "source_ids": ["6b8f3c1e-0000-4000-8000-000000000000"],
        },
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST, response.content


def test_reject_more_sources_than_the_cap(
        api_client, superuser, settings, organization, route_1, integrations_list_er, lotek_sources
):
    settings.SOURCE_FILTER_MAX_SOURCES = 1
    response = _post(api_client, superuser, route_1, _payload(integrations_list_er[1], lotek_sources[:2]))
    assert response.status_code == status.HTTP_400_BAD_REQUEST, response.content
    assert "at most 1 sources" in response.content.decode()


def test_second_filter_for_the_same_destination_conflicts(
        api_client, superuser, organization, route_1, integrations_list_er, lotek_sources
):
    # route_1's fixture already has a list filter on integrations_list_er[0].
    response = _post(
        api_client, superuser, route_1, _payload(integrations_list_er[0], lotek_sources[:1])
    )
    assert response.status_code == status.HTTP_409_CONFLICT, response.content
    assert "already has a filter" in response.content.decode()


def test_mode_is_required(
        api_client, superuser, organization, route_1, integrations_list_er, lotek_sources
):
    api_client.force_authenticate(superuser)
    response = api_client.post(
        _list_url(route_1),
        data={
            "destination": str(integrations_list_er[1].id),
            "source_ids": [str(lotek_sources[0].id)],
        },
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST, response.content
    assert "mode" in response.json()


def test_malformed_route_id_does_not_error_in_permission_layer(
        api_client, org_admin_user, organization, route_1
):
    api_client.force_authenticate(org_admin_user)
    response = api_client.get(reverse("filters-list", kwargs={"route_pk": "not-a-uuid"}))
    assert response.status_code in (
        status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND
    ), response.content


# ---- Updating and deleting ------------------------------------------------


def test_update_replaces_the_source_list_wholesale(
        api_client, org_admin_user, organization, route_1, lotek_sources
):
    source_filter = route_1.source_filters.get()
    api_client.force_authenticate(org_admin_user)
    response = api_client.patch(
        _detail_url(route_1, source_filter),
        data={"source_ids": [str(lotek_sources[0].id)]},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK, response.content
    source_filter.refresh_from_db()
    assert set(source_filter.sources.values_list("id", flat=True)) == {lotek_sources[0].id}


def test_update_can_switch_mode(
        api_client, org_admin_user, organization, route_1
):
    source_filter = route_1.source_filters.get()
    api_client.force_authenticate(org_admin_user)
    response = api_client.patch(
        _detail_url(route_1, source_filter), data={"mode": "blacklist"}, format="json"
    )
    assert response.status_code == status.HTTP_200_OK, response.content
    source_filter.refresh_from_db()
    assert source_filter.mode == SourceFilter.FilterModes.BLACKLIST


def test_updating_a_filter_does_not_conflict_with_itself(
        api_client, superuser, organization, route_1, lotek_sources
):
    # The duplicate check must exclude the row being edited, or every update would 409.
    source_filter = route_1.source_filters.get()
    api_client.force_authenticate(superuser)
    response = api_client.patch(
        _detail_url(route_1, source_filter),
        data={"destination": str(source_filter.destination_id)},
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK, response.content


def test_delete_filter(api_client, org_admin_user, organization, route_1):
    source_filter = route_1.source_filters.get()
    api_client.force_authenticate(org_admin_user)
    response = api_client.delete(_detail_url(route_1, source_filter))

    assert response.status_code == status.HTTP_204_NO_CONTENT, response.content
    assert not SourceFilter.objects.filter(id=source_filter.id).exists()


def test_cannot_delete_filter_as_org_viewer(
        api_client, org_viewer_user, organization, route_1
):
    source_filter = route_1.source_filters.get()
    api_client.force_authenticate(org_viewer_user)
    response = api_client.delete(_detail_url(route_1, source_filter))

    assert response.status_code == status.HTTP_403_FORBIDDEN, response.content
    assert SourceFilter.objects.filter(id=source_filter.id).exists()


def test_removing_a_destination_from_the_route_removes_its_filters(
        organization, route_1, integrations_list_er
):
    # Cascade rather than a pruning signal — the reason the rules are relational.
    source_filter = route_1.source_filters.get()
    destination = source_filter.destination
    destination.delete()
    assert not SourceFilter.objects.filter(id=source_filter.id).exists()


def test_deleting_a_source_removes_it_from_the_filter(
        organization, route_1, lotek_sources
):
    source_filter = route_1.source_filters.get()
    removed = lotek_sources[0]
    removed.delete()

    source_filter.refresh_from_db()
    assert removed.id not in set(source_filter.sources.values_list("id", flat=True))
    assert SourceFilter.objects.filter(id=source_filter.id).exists()


# ---- Paged sources --------------------------------------------------------


def _sources_url(route, source_filter):
    return reverse(
        "filters-sources",
        kwargs={"route_pk": str(route.id), "pk": str(source_filter.id)},
    )


def test_filter_sources_are_paged(
        api_client, org_admin_user, organization, route_1, lotek_sources
):
    source_filter = route_1.source_filters.get()
    api_client.force_authenticate(org_admin_user)
    response = api_client.get(_sources_url(route_1, source_filter))

    assert response.status_code == status.HTTP_200_OK, response.content
    body = response.json()
    assert body["count"] == len(lotek_sources)
    assert {s["external_id"] for s in body["results"]} == {s.external_id for s in lotek_sources}
    assert "last_update" in body["results"][0]


def test_filter_sources_page_size_can_be_overridden(
        api_client, org_admin_user, organization, route_1, lotek_sources
):
    source_filter = route_1.source_filters.get()
    api_client.force_authenticate(org_admin_user)
    response = api_client.get(_sources_url(route_1, source_filter), {"limit": 2})

    assert response.status_code == status.HTTP_200_OK, response.content
    body = response.json()
    assert len(body["results"]) == 2
    assert body["count"] == len(lotek_sources)


def test_cannot_read_filter_sources_of_another_org_route(
        api_client, org_admin_user, organization, other_organization, route_2
):
    source_filter = route_2.source_filters.get()
    api_client.force_authenticate(org_admin_user)
    response = api_client.get(_sources_url(route_2, source_filter))
    assert response.status_code in (
        status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND
    ), response.content


# ---- default-source advisory ----------------------------------------------


def test_whitelist_omitting_default_source_is_flagged(
        api_client, superuser, organization, route_1, provider_lotek_panthera
):
    # Ingestion creates this row for any client that submits without a source. A whitelist
    # that leaves it out stops all of that provider's sourceless traffic.
    Source.objects.create(
        integration=provider_lotek_panthera, external_id="default-source"
    )
    api_client.force_authenticate(superuser)
    response = api_client.get(_list_url(route_1))

    assert response.status_code == status.HTTP_200_OK, response.content
    assert response.json()["results"][0]["excludes_default_source"] is True


def test_whitelist_including_default_source_is_not_flagged(
        api_client, superuser, organization, route_1, provider_lotek_panthera
):
    default_source = Source.objects.create(
        integration=provider_lotek_panthera, external_id="default-source"
    )
    source_filter = route_1.source_filters.get()
    source_filter.sources.add(default_source)

    api_client.force_authenticate(superuser)
    response = api_client.get(_list_url(route_1))
    assert response.json()["results"][0]["excludes_default_source"] is False


def test_blacklist_is_never_flagged_for_default_source(
        api_client, superuser, organization, route_1, provider_lotek_panthera
):
    Source.objects.create(integration=provider_lotek_panthera, external_id="default-source")
    source_filter = route_1.source_filters.get()
    source_filter.mode = SourceFilter.FilterModes.BLACKLIST
    source_filter.save()

    api_client.force_authenticate(superuser)
    response = api_client.get(_list_url(route_1))
    assert response.json()["results"][0]["excludes_default_source"] is False

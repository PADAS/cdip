import pytest
from django.urls import reverse
from rest_framework import status
from integrations.models import (
    Integration
)


pytestmark = pytest.mark.django_db


def _test_list_destinations(api_client, user, organization):
    api_client.force_authenticate(user)
    response = api_client.get(
        reverse("integrations-list"),
    )
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    destinations = response_data["results"]
    if user.is_superuser:
        # The superuser can see all the destinations
        destinations_qs = Integration.objects.all()
    else: # Only see destinations owned by the organization(s) where the user is a member
        destinations_qs = Integration.objects.filter(owner=organization)
    expected_destinations_ids = [str(uid) for uid in destinations_qs.values_list("id", flat=True)]
    assert len(destinations) == len(expected_destinations_ids)
    for dest in destinations:
        assert dest.get("id") in expected_destinations_ids
        assert "name" in dest
        assert "base_url" in dest
        assert "enabled" in dest
        assert "type" in dest
        owner = dest.get("owner")
        assert owner
        assert "id" in owner
        assert "name" in owner
        assert "description" in owner
        assert "configurations" in dest
        configurations = dest.get("configurations")
        for configuration in configurations:
            assert "site_name" in configuration
            assert "username" in configuration
            assert "password" in configuration
            assert "status" in dest
            # ToDo test status further once defined/implemented.


def test_list_destinations_as_superuser(api_client, superuser, organization, destinations_list):
    _test_list_destinations(
        api_client=api_client,
        user=superuser,
        organization=organization
    )


def test_list_destinations_as_org_admin(api_client, org_admin_user, organization, destinations_list):
    _test_list_destinations(
        api_client=api_client,
        user=org_admin_user,
        organization=organization
    )


def test_list_destinations_as_org_viewer(api_client, org_viewer_user, organization, destinations_list):
    _test_list_destinations(
        api_client=api_client,
        user=org_viewer_user,
        organization=organization
    )

#  ToDo: Refactor after integrations creation is supported
# def _test_create_destination(api_client, user, owner, destination_type, destination_name, configuration):
#     request_data = {
#       "name": destination_name,
#       "type": str(destination_type.id),
#       "owner": str(owner.id),
#       "base_url": "https://reservex.pamdas.org",
#       "configuration": configuration
#     }
#     api_client.force_authenticate(user)
#     response = api_client.post(
#         reverse("integrations-list"),
#         data=request_data,
#         format='json'
#     )
#     assert response.status_code == status.HTTP_201_CREATED
#     response_data = response.json()
#     assert "id" in response_data
#     # Check that the destination was created in the database
#     assert Integration.objects.filter(name=request_data["name"]).exists()
#
#
# def test_create_destination_as_superuser(api_client, superuser, organization, destination_type_er, get_random_id):
#     _test_create_destination(
#         api_client=api_client,
#         user=superuser,
#         owner=organization,
#         destination_type=destination_type_er,
#         destination_name=f"Reserve X {get_random_id()}",
#         configuration={
#             "site": "https://reservex.pamdas.org",
#             "username": "reservex@pamdas.org",
#             "password": "P4sSW0rD"
#         }
#     )
#
#
# def test_create_destination_as_org_admin(api_client, org_admin_user, organization, destination_type_er, get_random_id):
#     _test_create_destination(
#         api_client=api_client,
#         user=org_admin_user,
#         owner=organization,
#         destination_type=destination_type_er,
#         destination_name=f"Reserve Y {get_random_id()}",
#         configuration={
#             "site": "https://reservey.pamdas.org",
#             "username": "reservey@pamdas.org",
#             "password": "P4sSW0rD"
#         }
#     )
#
#
# def _test_cannot_create_destination(api_client, user, owner, destination_type, destination_name, configuration):
#     request_data = {
#       "name": destination_name,
#       "type": str(destination_type.id),
#       "owner": str(owner.id),
#       "base_url": "https://reservex.pamdas.org",
#       "configuration": configuration
#     }
#     api_client.force_authenticate(user)
#     response = api_client.post(
#         reverse("integrations-list"),
#         data=request_data,
#         format='json'
#     )
#     assert response.status_code == status.HTTP_403_FORBIDDEN
#
#
# def test_cannot_create_destination_as_org_viewer(api_client, org_viewer_user, organization, destination_type_er, get_random_id):
#     _test_cannot_create_destination(
#         api_client=api_client,
#         user=org_viewer_user,
#         owner=organization,
#         destination_type=destination_type_er,
#         destination_name=f"Reserve Z {get_random_id()}",
#         configuration={
#             "site": "https://reservez.pamdas.org",
#             "username": "reservez@pamdas.org",
#             "password": "P4sSW0rD"
#         }
#     )


def _test_filter_integrations(api_client, user, filters, expected_destinations):
    api_client.force_authenticate(user)
    response = api_client.get(
        reverse("integrations-list"),
        data=filters
    )
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    destinations = response_data["results"]
    # Check that the returned destinations are the expected ones
    expected_destinations_ids = [str(uid) for uid in expected_destinations.values_list("id", flat=True)]
    assert len(destinations) == len(expected_destinations_ids)
    for dest in destinations:
        assert dest.get("id") in expected_destinations_ids


def test_filter_integrations_exact_as_superuser(api_client, superuser, organization, destinations_list):
    destination = destinations_list[0]
    _test_filter_integrations(
        api_client=api_client,
        user=superuser,
        filters={
            "owner": str(destination.owner.id),
            "enabled": True,
            "type": str(destination.type.id),
            "base_url": str(destination.base_url)
        },
        expected_destinations=Integration.objects.filter(
            owner=destination.owner,
            enabled=True,
            type=destination.type,
            base_url=destination.base_url
        )
    )


def test_filter_integrations_iexact_as_superuser(api_client, superuser, organization, destinations_list):
    destination = destinations_list[0]
    _test_filter_integrations(
        api_client=api_client,
        user=superuser,
        filters={
            "base_url__iexact": str(destination.base_url).capitalize()
        },
        expected_destinations=Integration.objects.filter(
            owner=destination.owner,
            enabled=True,
            type=destination.type,
            base_url=destination.base_url
        )
    )


def test_filter_integrations_exact_as_org_admin(api_client, org_admin_user, organization, destinations_list):
    _test_filter_integrations(
        api_client=api_client,
        user=org_admin_user,
        filters={
            "owner": str(organization.id),
            "enabled": True
        },
        expected_destinations=Integration.objects.filter(
            owner=organization,
            enabled=True
        )
    )


def test_filter_integrations_exact_as_org_viewer(api_client, org_viewer_user, organization, destination_type_er, destinations_list):
    # Viewer belongs to organization which owns the first 5 destinations of type EarthRanger
    _test_filter_integrations(
        api_client=api_client,
        user=org_viewer_user,
        filters={
            "owner": str(organization.id),
            "type": str(destination_type_er.id)
        },
        expected_destinations=Integration.objects.filter(
            owner=organization,
            type=destination_type_er
        )
    )


def test_filter_integrations_multiselect_as_superuser(api_client, superuser, organization, other_organization, destinations_list):
    # Superuser can see destinations owned by any organizations
    owners = [organization, other_organization]
    base_urls = [d.base_url for d in destinations_list[1::2]]
    _test_filter_integrations(
        api_client=api_client,
        user=superuser,
        filters={  # Multiple owners and Multiple base_urls allowed
            "owner__in": ",".join([str(o.id) for o in owners]),
            "base_url__in": ",".join(base_urls)
        },
        expected_destinations=Integration.objects.filter(
            owner__in=owners,
            base_url__in=base_urls
        )
    )


def test_filter_integrations_multiselect_as_org_admin(api_client, org_admin_user, organization, other_organization, destinations_list):
    # Org Admins can see destinations owned by the organizations they belong to
    # This org admin belongs to "organization" owning the first 5 destinations of "destinations_list"
    owners = org_admin_user.accountprofile.organizations.all()
    base_urls = [d.base_url for d in destinations_list[:3]]  # Select three out of five possible base_urls
    _test_filter_integrations(
        api_client=api_client,
        user=org_admin_user,
        filters={  # Multiple owners and Multiple base_urls allowed
            "owner__in": ",".join([str(o.id) for o in owners]),
            "base_url__in": ",".join(base_urls)
        },
        expected_destinations=Integration.objects.filter(
            owner__in=owners,
            base_url__in=base_urls
        )
    )


def test_filter_integrations_multiselect_as_org_viewer(api_client, org_viewer_user, organization, other_organization, destinations_list):
    # Org Viewer can see destinations owned by the organizations they belong to
    # This org viewer belongs to "organization" owning the first 5 destinations of "destinations_list"
    owners = org_viewer_user.accountprofile.organizations.all()
    base_urls = [d.base_url for d in destinations_list[:2]]  # Select two out of five possible base_urls
    _test_filter_integrations(
        api_client=api_client,
        user=org_viewer_user,
        filters={  # Multiple owners and Multiple base_urls allowed
            "owner__in": ",".join([str(o.id) for o in owners]),
            "base_url__in": ",".join(base_urls)
        },
        expected_destinations=Integration.objects.filter(
            owner__in=owners,
            base_url__in=base_urls
        )
    )

import pytest
from django.urls import reverse
from rest_framework import status
from integrations.models import (
    Integration, IntegrationAction, IntegrationType
)


pytestmark = pytest.mark.django_db


def _test_list_integrations(api_client, user, organization):
    api_client.force_authenticate(user)
    response = api_client.get(
        reverse("integrations-list"),
    )
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    integrations = response_data["results"]
    if user.is_superuser:
        # The superuser can see all the integrations
        integrations_qs = Integration.objects.all()
    else: # Only see integrations owned by the organization(s) where the user is a member
        integrations_qs = Integration.objects.filter(owner=organization)
    expected_integrations_ids = [str(uid) for uid in integrations_qs.values_list("id", flat=True)]
    assert len(integrations) == len(expected_integrations_ids)
    for integration in integrations:
        assert integration.get("id") in expected_integrations_ids
        assert "name" in integration
        assert "base_url" in integration
        assert "enabled" in integration
        assert "type" in integration
        owner = integration.get("owner")
        assert owner
        assert "id" in owner
        assert "name" in owner
        assert "description" in owner
        # Check the action configurations
        assert "configurations" in integration
        configurations = integration.get("configurations")
        for configuration in configurations:
            assert "integration" in configuration
            assert "action" in configuration
            assert "data" in configuration


def test_list_integrations_as_superuser(api_client, superuser, organization, integrations_list):
    _test_list_integrations(
        api_client=api_client,
        user=superuser,
        organization=organization
    )


def test_list_integrations_as_org_admin(api_client, org_admin_user, organization, integrations_list):
    _test_list_integrations(
        api_client=api_client,
        user=org_admin_user,
        organization=organization
    )


def test_list_integrations_as_org_viewer(api_client, org_viewer_user, organization, integrations_list):
    _test_list_integrations(
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


def _test_filter_integrations(api_client, user, filters, expected_integrations):
    api_client.force_authenticate(user)
    response = api_client.get(
        reverse("integrations-list"),
        data=filters
    )
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    integrations = response_data["results"]
    # Check that the returned integrations are the expected ones
    expected_integrations_ids = [str(uid) for uid in expected_integrations.values_list("id", flat=True)]
    assert len(integrations) == len(expected_integrations_ids)
    for dest in integrations:
        assert dest.get("id") in expected_integrations_ids


def test_filter_integrations_exact_as_superuser(api_client, superuser, organization, integrations_list):
    destination = integrations_list[0]
    _test_filter_integrations(
        api_client=api_client,
        user=superuser,
        filters={
            "owner": str(destination.owner.id),
            "enabled": True,
            "type": str(destination.type.id),
            "base_url": str(destination.base_url)
        },
        expected_integrations=Integration.objects.filter(
            owner=destination.owner,
            enabled=True,
            type=destination.type,
            base_url=destination.base_url
        )
    )


def test_filter_integrations_iexact_as_superuser(api_client, superuser, organization, integrations_list):
    destination = integrations_list[0]
    _test_filter_integrations(
        api_client=api_client,
        user=superuser,
        filters={
            "base_url__iexact": str(destination.base_url).capitalize()
        },
        expected_integrations=Integration.objects.filter(
            owner=destination.owner,
            enabled=True,
            type=destination.type,
            base_url=destination.base_url
        )
    )


def test_filter_integrations_exact_as_org_admin(api_client, org_admin_user, organization, integrations_list):
    _test_filter_integrations(
        api_client=api_client,
        user=org_admin_user,
        filters={
            "owner": str(organization.id),
            "enabled": True
        },
        expected_integrations=Integration.objects.filter(
            owner=organization,
            enabled=True
        )
    )


def test_filter_integrations_exact_as_org_viewer(api_client, org_viewer_user, organization, integration_type_er, integrations_list):
    # Viewer belongs to organization which owns the first 5 integrations of type EarthRanger
    _test_filter_integrations(
        api_client=api_client,
        user=org_viewer_user,
        filters={
            "owner": str(organization.id),
            "type": str(integration_type_er.id)
        },
        expected_integrations=Integration.objects.filter(
            owner=organization,
            type=integration_type_er
        )
    )


def test_filter_integrations_multiselect_as_superuser(api_client, superuser, organization, other_organization, integrations_list):
    # Superuser can see integrations owned by any organizations
    owners = [organization, other_organization]
    base_urls = [d.base_url for d in integrations_list[1::2]]
    _test_filter_integrations(
        api_client=api_client,
        user=superuser,
        filters={  # Multiple owners and Multiple base_urls allowed
            "owner__in": ",".join([str(o.id) for o in owners]),
            "base_url__in": ",".join(base_urls)
        },
        expected_integrations=Integration.objects.filter(
            owner__in=owners,
            base_url__in=base_urls
        )
    )


def test_filter_integrations_multiselect_as_org_admin(api_client, org_admin_user, organization, other_organization, integrations_list):
    # Org Admins can see integrations owned by the organizations they belong to
    # This org admin belongs to "organization" owning the first 5 integrations of "integrations_list"
    owners = org_admin_user.accountprofile.organizations.all()
    base_urls = [d.base_url for d in integrations_list[:3]]  # Select three out of five possible base_urls
    _test_filter_integrations(
        api_client=api_client,
        user=org_admin_user,
        filters={  # Multiple owners and Multiple base_urls allowed
            "owner__in": ",".join([str(o.id) for o in owners]),
            "base_url__in": ",".join(base_urls)
        },
        expected_integrations=Integration.objects.filter(
            owner__in=owners,
            base_url__in=base_urls
        )
    )


def test_filter_integrations_multiselect_as_org_viewer(api_client, org_viewer_user, organization, other_organization, integrations_list):
    # Org Viewer can see integrations owned by the organizations they belong to
    # This org viewer belongs to "organization" owning the first 5 integrations of "integrations_list"
    owners = org_viewer_user.accountprofile.organizations.all()
    base_urls = [d.base_url for d in integrations_list[:2]]  # Select two out of five possible base_urls
    _test_filter_integrations(
        api_client=api_client,
        user=org_viewer_user,
        filters={  # Multiple owners and Multiple base_urls allowed
            "owner__in": ",".join([str(o.id) for o in owners]),
            "base_url__in": ",".join(base_urls)
        },
        expected_integrations=Integration.objects.filter(
            owner__in=owners,
            base_url__in=base_urls
        )
    )


def test_filter_integrations_by_action_type_as_superuser(api_client, superuser, organization, other_organization, integrations_list):
    _test_filter_integrations(
        api_client=api_client,
        user=superuser,
        filters={  # Integrations which can be used as destination
            "action_type": IntegrationAction.ActionTypes.PUSH_DATA.value
        },
        expected_integrations=Integration.objects.filter(
            type__actions__type=IntegrationAction.ActionTypes.PUSH_DATA.value
        )
    )


def test_filter_integrations_by_action_type_as_org_admin(api_client, org_admin_user, organization, other_organization, integrations_list):
    # Org Admins can see integrations owned by the organizations they belong to
    # This org admin belongs to "organization" owning the first 5 integrations of "integrations_list"
    owners = org_admin_user.accountprofile.organizations.all()
    _test_filter_integrations(
        api_client=api_client,
        user=org_admin_user,
        filters={  # Integrations which can be used as data provider
            "action_type": IntegrationAction.ActionTypes.PULL_DATA.value
        },
        expected_integrations=Integration.objects.filter(
            owner__in=owners,
            type__actions__type=IntegrationAction.ActionTypes.PULL_DATA.value
        )
    )


def test_filter_integrations_by_action_type_as_org_viewer(api_client, org_viewer_user, organization, other_organization, integrations_list):
    # Org Viewer can see integrations owned by the organizations they belong to
    # This org viewer belongs to "organization" owning the first 5 integrations of "integrations_list"
    owners = org_viewer_user.accountprofile.organizations.all()
    _test_filter_integrations(
        api_client=api_client,
        user=org_viewer_user,
        filters={  # Integrations which can be used as data provider
            "action_type": IntegrationAction.ActionTypes.AUTHENTICATION.value
        },
        expected_integrations=Integration.objects.filter(
            owner__in=owners,
            type__actions__type=IntegrationAction.ActionTypes.AUTHENTICATION.value
        )
    )


def _test_filter_integration_types(api_client, user, filters, expected_integration_types):
    api_client.force_authenticate(user)
    response = api_client.get(
        reverse("integration-types-list"),
        data=filters
    )
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    integration_types = response_data["results"]
    # Check that the returned integrations are the expected ones
    expected_type_ids = [str(t.id) for t in expected_integration_types]
    assert len(integration_types) == len(expected_type_ids)
    for type in integration_types:
        assert type.get("id") in expected_type_ids


def test_filter_integrations_types_by_action_type_as_superuser(
        api_client, superuser, organization, other_organization,
        integration_type_er, integration_type_movebank, provider_type_lotek,
        integrations_list, provider_movebank_ewt, provider_lotek_panthera
):
    _test_filter_integration_types(
        api_client=api_client,
        user=superuser,
        filters={  # Integrations which can be used as destination
            "action_type": IntegrationAction.ActionTypes.PUSH_DATA.value
        },
        expected_integration_types=[integration_type_er]
    )


def test_filter_integrations_types_by_action_type_as_org_admin(
        api_client, org_admin_user, organization, other_organization,
        integration_type_er, integration_type_movebank, provider_type_lotek,
        integrations_list, provider_movebank_ewt, provider_lotek_panthera
):
    _test_filter_integration_types(
        api_client=api_client,
        user=org_admin_user,
        filters={  # Integrations supporting the authentication action
            "action_type": IntegrationAction.ActionTypes.AUTHENTICATION.value
        },
        expected_integration_types=[integration_type_er, integration_type_movebank, provider_type_lotek]
    )


def test_filter_integrations_types_type_as_org_viewer(
        api_client, org_viewer_user, organization, other_organization,
        integration_type_er, integration_type_movebank, provider_type_lotek,
        integrations_list, provider_movebank_ewt, provider_lotek_panthera
):
    _test_filter_integration_types(
        api_client=api_client,
        user=org_viewer_user,
        filters={  # Integrations which can be used as data provider
            "action_type": IntegrationAction.ActionTypes.PULL_DATA.value
        },
        expected_integration_types=[integration_type_er,  integration_type_movebank, provider_type_lotek]
    )

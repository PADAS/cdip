import base64
import time
import uuid
from typing import NamedTuple, Any

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse
from rest_framework.utils import json

from accounts.models import AccountProfile, AccountProfileOrganization
from core.enums import DjangoGroups, RoleChoices
from integrations.models import InboundIntegrationType, InboundIntegrationConfiguration
from organizations.models import Organization


def test_get_integration_type_list(client, global_admin_user):

    client.force_login(global_admin_user.user)

    response = client.get(reverse("inboundintegrationtype_list"), HTTP_X_USERINFO=global_admin_user.user_info)

    assert response.status_code == 200

    response = response.json()

    assert len(response) == InboundIntegrationType.objects.count()


def test_get_integration_configuration_list_global_admin(client, global_admin_user):

    client.force_login(global_admin_user.user)

    response = client.get(reverse("inbound_integration_configuration_list"), HTTP_X_USERINFO=global_admin_user.user_info)

    assert response.status_code == 200

    # confirm result set is unfiltered
    assert list(response.context['inboundintegrationconfiguration_list']) == list(InboundIntegrationConfiguration.objects.all())


def test_get_integration_configuration_list_organization_member_viewer(client, organization_member_user, setup_data):
    org1 = setup_data["org1"]

    ap = AccountProfile.objects.create(
        user_id=organization_member_user.user.username
    )

    apo = AccountProfileOrganization.objects.create(
        accountprofile=ap,
        organization=org1,
        role=RoleChoices.VIEWER
    )

    # Sanity check on the test data relationships.
    assert AccountProfile.objects.filter(user_id=organization_member_user.user.username).exists()
    assert AccountProfileOrganization.objects.filter(accountprofile=ap).exists()

    client.force_login(organization_member_user.user)

    response = client.get(reverse("inbound_integration_configuration_list"), follow=True, HTTP_X_USERINFO=organization_member_user.user_info)

    assert response.status_code == 200

    # confirm result set is filtered queryset based on organization profile
    assert list(response.context['inboundintegrationconfiguration_list']) == list(InboundIntegrationConfiguration.objects.filter(owner=org1))


def test_add_outbound_integration_configuration_organization_member_hybrid(client, organization_member_user, setup_data):
    org1 = setup_data["org1"]
    org2 = setup_data["org2"]

    ap = AccountProfile.objects.create(
        user_id=organization_member_user.user.username
    )

    apo1 = AccountProfileOrganization.objects.create(
        accountprofile=ap,
        organization=org1,
        role=RoleChoices.VIEWER
    )

    apo2 = AccountProfileOrganization.objects.create(
        accountprofile=ap,
        organization=org2,
        role=RoleChoices.ADMIN
    )

    # Sanity check on the test data relationships.
    assert Organization.objects.filter(id=org1.id).exists()
    assert Organization.objects.filter(id=org2.id).exists()
    assert AccountProfile.objects.filter(user_id=organization_member_user.user.username).exists()
    assert AccountProfileOrganization.objects.filter(accountprofile=ap).exists()

    client.force_login(organization_member_user.user)

    response = client.get(reverse("outbound_integration_configuration_add"), follow=True, HTTP_X_USERINFO=organization_member_user.user_info)

    assert response.status_code == 200

    # confirm result set is filtered queryset based on organization profile
    # assert list(response.context['inboundintegrationconfiguration_list']) == list(InboundIntegrationConfiguration.objects.filter(owner=org1))
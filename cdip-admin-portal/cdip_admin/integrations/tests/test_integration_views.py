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
    iit = InboundIntegrationType.objects.create(
        name='Some integration type',
        slug='some-integration-type',
        description='Some integration type.'

    )

    client.force_login(global_admin_user.user)

    response = client.get(reverse("inboundintegrationtype_list"), HTTP_X_USERINFO=global_admin_user.user_info)

    assert response.status_code == 200

    response = response.json()

    assert InboundIntegrationType.objects.count() == len(response)


def test_get_integration_configuration_list_global_admin(client, global_admin_user):
    iit = InboundIntegrationType.objects.create(
        name='Some integration type',
        slug='some-integration-type',
        description='Some integration type.'

    )

    org = Organization.objects.create(
        name='Some org.'
    )

    ii = InboundIntegrationConfiguration.objects.create(
        type=iit,
        name='some ii',
        owner=org
    )

    client.force_login(global_admin_user.user)

    response = client.get(reverse("inbound_integration_configuration_list"), HTTP_X_USERINFO=global_admin_user.user_info)

    assert response.status_code == 200

    # confirm result set is unfiltered
    assert list(response.context['inboundintegrationconfiguration_list']) == list(InboundIntegrationConfiguration.objects.all())


def test_get_integration_configuration_list_organization_member_viewer(client, organization_member_user):
    iit = InboundIntegrationType.objects.create(
        name='Some integration type',
        slug='some-integration-type',
        description='Some integration type.'
    )

    org1 = Organization.objects.create(
        name='Some org.'
    )

    org2 = Organization.objects.create(
        name='Some org2'
    )

    ii = InboundIntegrationConfiguration.objects.create(
        type=iit,
        name='some ii',
        owner=org1,
    )

    o_iit = InboundIntegrationType.objects.create(
        name='Some other integration type',
        slug='some-other-integration-type',
        description='Some other integration type.'
    )

    o_ii = InboundIntegrationConfiguration.objects.create(
        type=o_iit,
        name='some other ii',
        owner=org2,
    )

    ap = AccountProfile.objects.create(
        user_id=organization_member_user.user.username
    )

    apo = AccountProfileOrganization.objects.create(
        accountprofile=ap,
        organization=org1,
        role=RoleChoices.VIEWER
    )

    # Sanity check on the test data relationships.
    assert Organization.objects.filter(id=org1.id).exists()
    assert Organization.objects.filter(id=org2.id).exists()
    assert AccountProfile.objects.filter(user_id=organization_member_user.user.username).exists()
    assert AccountProfileOrganization.objects.filter(accountprofile=ap).exists()

    client.force_login(organization_member_user.user)

    response = client.get(reverse("inbound_integration_configuration_list"), follow=True, HTTP_X_USERINFO=organization_member_user.user_info)

    assert response.status_code == 200

    # confirm result set is filtered queryset based on organization profile
    assert list(response.context['inboundintegrationconfiguration_list']) == list(InboundIntegrationConfiguration.objects.filter(owner=org1))

class User(NamedTuple):
    user: Any = None
    user_info: bytes = None


@pytest.fixture
def organization_member_user(db, django_user_model):
    password = django_user_model.objects.make_random_password()
    user_const = dict(last_name='Owen', first_name='Harry')
    user_id = str(uuid.uuid4())
    username = 'harry.owen@vulcan.com'
    user = django_user_model.objects.create_superuser(
        user_id, username, password,
        **user_const)
    user_info = {'sub': user_id,
                 'username': username}

    x_user_info = base64.b64encode(json.dumps(user_info).encode("utf-8"))

    group_name = DjangoGroups.ORGANIZATION_MEMBER.value
    group = Group.objects.create(name=group_name)
    user.groups.add(group)
    user.save()

    u = User(user_info=x_user_info,
             user=user)

    return u

'''
Provisions a django user that is enrolled in the django group "Global Admin"
'''
@pytest.fixture
def global_admin_user(db, django_user_model):
    password = django_user_model.objects.make_random_password()
    user_const = dict(last_name='Owen', first_name='Harry')
    user_id = str(uuid.uuid4())
    username = 'harry.owen@vulcan.com'
    user = django_user_model.objects.create_superuser(
        user_id, username, password,
        **user_const)
    user_info = {'sub': user_id,
                 'username': username}

    x_user_info = base64.b64encode(json.dumps(user_info).encode("utf-8"))

    group_name = DjangoGroups.GLOBAL_ADMIN.value
    group = Group.objects.create(name=group_name)
    user.groups.add(group)
    user.save()

    u = User(user_info=x_user_info,
             user=user)

    return u
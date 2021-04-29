import base64
import uuid
from typing import NamedTuple, Any

import pytest
from django.contrib.auth.models import Group
from rest_framework.utils import json

from core.enums import DjangoGroups
from integrations.models import InboundIntegrationType, OutboundIntegrationType, InboundIntegrationConfiguration, \
    OutboundIntegrationConfiguration, DeviceGroup, Device, DeviceState
from organizations.models import Organization


class User(NamedTuple):
    user: Any = None
    user_info: bytes = None


class User(NamedTuple):
    user: Any = None
    user_info: bytes = None


'''
Provisions a django user that is enrolled in the django group "Global Admin"
'''
@pytest.fixture
def global_admin_user(db, django_user_model):
    password = django_user_model.objects.make_random_password()
    user_const = dict(last_name='Owen', first_name='Harry')
    user_id = str(uuid.uuid4())
    email = 'harry.owen@vulcan.com'
    user = django_user_model.objects.create_superuser(
        user_id, email, password,
        **user_const)
    user_info = {'sub': user_id,
                 'username': user_id,
                 'email': email}

    x_user_info = base64.b64encode(json.dumps(user_info).encode("utf-8"))

    group_name = DjangoGroups.GLOBAL_ADMIN.value
    group = Group.objects.create(name=group_name)
    user.groups.add(group)
    user.save()

    u = User(user_info=x_user_info,
             user=user)

    return u


'''
Provisions a django user that is enrolled in the django group "Organization Member"
'''
@pytest.fixture
def organization_member_user(db, django_user_model):
    password = django_user_model.objects.make_random_password()
    user_const = dict(last_name='Owen', first_name='Harry')
    user_id = str(uuid.uuid4())
    email = 'harry.owen@vulcan.com'
    user = django_user_model.objects.create_superuser(
        user_id, email, password,
        **user_const)
    user_info = {'sub': user_id,
                 'username': user_id,
                 'email': email}


    x_user_info = base64.b64encode(json.dumps(user_info).encode("utf-8"))

    group_name = DjangoGroups.ORGANIZATION_MEMBER.value
    group = Group.objects.create(name=group_name)
    user.groups.add(group)
    user.save()

    u = User(user_info=x_user_info,
             user=user)

    return u


'''
Provisions a django user that simulates a service account or "client". Proper user info is added so that requests can be
made with header "HTTP_X_USERINFO" so that our middleware and backend appropriately add the client_id to the requests 
session, allowing the permissions checks to pass for IsServiceAccount. The associated client profile and 
dependent objects related to that client are also created here. 
'''
@pytest.fixture
def client_user(db, django_user_model):
    password = django_user_model.objects.make_random_password()
    user_const = dict(last_name='Owen', first_name='Harry')
    username = 'service-account-test-function'
    user_id = str(uuid.uuid4())
    client_id = 'test-function'

    user_info = {'sub': user_id,
                 'client_id': client_id,
                 'username': username}

    x_user_info = base64.b64encode(json.dumps(user_info).encode("utf-8"))

    user = django_user_model.objects.create_superuser(
        user_id, username, password,
        **user_const)

    u = User(user_info=x_user_info,
              user=user)

    return u


@pytest.fixture
def setup_data(db, django_user_model):

    org1 = Organization.objects.create(
        name='Org 1'
    )

    org2 = Organization.objects.create(
        name='Org 2'
    )

    iit1 = InboundIntegrationType.objects.create(
        name='Inbound Type 1',
        slug='inbound-type-one',
        description='Some integration type.'

    )

    iit2 = InboundIntegrationType.objects.create(
        name='Inbound Type 2',
        slug='inbound-type-two',
        description='Some integration type.'

    )

    oit1 = OutboundIntegrationType.objects.create(
        name='Outbound Type 1',
        slug='outbound-type-one',
        description='Some integration type.'
    )

    oit2 = OutboundIntegrationType.objects.create(
        name='Outbound Type 2',
        slug='outbound-type-two',
        description='Some integration type.'
    )

    ii1 = InboundIntegrationConfiguration.objects.create(
        type=iit1,
        name='Inbound Configuration 1',
        owner=org1
    )

    ii2 = InboundIntegrationConfiguration.objects.create(
        type=iit2,
        name='Inbound Configuration 2',
        owner=org2
    )

    oi1 = OutboundIntegrationConfiguration.objects.create(
        type=oit1,
        name='Outbound Configuration 1',
        owner=org1
    )

    oi2 = OutboundIntegrationConfiguration.objects.create(
        type=oit2,
        name='Outbound Configuration 2',
        owner=org2
    )

    dg1 = DeviceGroup.objects.create(
        name='device group 1',
        owner=org1,
    )
    dg1.destinations.add(oi1)

    dg2 = DeviceGroup.objects.create(
        name='device group 2',
        owner=org2,
    )
    dg2.destinations.add(oi2)


    d1 = Device.objects.create(
        external_id='device-1',
        inbound_configuration=ii1
    )
    dg1.devices.add(d1)

    d2 = Device.objects.create(
        external_id='device-2',
        inbound_configuration=ii2
    )
    dg2.devices.add(d2)


    ds1 = DeviceState.objects.create(
        device=d1,
    )

    ds2 = DeviceState.objects.create(
        device=d2,
    )

    objects = {"org1": org1,
               "org2": org2,
               "iit1": iit1,
               "iit2": iit2,
               "oit1": oit1,
               "ii1": ii1,
               "ii2": ii2,
               "oi1": oi1,
               "oi2": oi2,
               "dg1": dg1,
               "dg2": dg2,
               "d1": d1,
               "d2": d2,
               "ds1": ds1,
               "ds2": ds2}

    return objects

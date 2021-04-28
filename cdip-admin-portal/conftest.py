import base64
import uuid
from typing import NamedTuple, Any

import pytest
from django.contrib.auth.models import Group
from rest_framework.utils import json

from core.enums import DjangoGroups


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


'''
Provisions a django user that is enrolled in the django group "Organization Member"
'''
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
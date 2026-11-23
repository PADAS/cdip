from django.test import RequestFactory
from rest_framework.request import Request

from core.permissions import IsServiceAccount


def test_service_account_permission_reads_client_id_from_request():
    """The auth backend sets client_id on the Django request on every API call."""
    req = RequestFactory().post("/api/v1.0/observations")
    req.client_id = "svc-client"

    assert IsServiceAccount().has_permission(req, view=None) is True
    assert IsServiceAccount.get_client_id(req) == "svc-client"


def test_service_account_permission_reads_through_a_drf_request():
    django_request = RequestFactory().post("/api/v1.0/observations")
    django_request.client_id = "svc-client"

    assert IsServiceAccount.get_client_id(Request(django_request)) == "svc-client"


def test_service_account_permission_denies_without_client_id():
    req = RequestFactory().get("/")
    req.session = {"client_id": "stale-from-an-old-login"}

    assert not IsServiceAccount().has_permission(req, view=None)
    assert IsServiceAccount.get_client_id(req) is None


# --- IsMetricsViewer -------------------------------------------------------

import importlib

import pytest
from django.contrib.auth.models import AnonymousUser, Group, User

from core.enums import DjangoGroups
from core.permissions import IsMetricsViewer


def _request_as(user):
    req = RequestFactory().get("/v2/stats/throughput/")
    req.user = user
    return req


@pytest.mark.django_db
def test_metrics_viewer_group_is_created_by_migration():
    assert Group.objects.filter(name=DjangoGroups.METRICS_VIEWER.value).exists()


@pytest.mark.django_db
def test_metrics_viewer_permission_allows_group_member():
    user = User.objects.create_user(username="metrics-member")
    user.groups.add(Group.objects.get(name=DjangoGroups.METRICS_VIEWER.value))

    assert IsMetricsViewer().has_permission(_request_as(user), view=None) is True


@pytest.mark.django_db
def test_metrics_viewer_permission_denies_user_outside_group():
    user = User.objects.create_user(username="not-a-metrics-member")
    # Membership of another access group must not be enough.
    user.groups.add(Group.objects.get(name=DjangoGroups.GLOBAL_ADMIN.value))

    assert IsMetricsViewer().has_permission(_request_as(user), view=None) is False


def test_metrics_viewer_permission_denies_anonymous():
    assert IsMetricsViewer().has_permission(_request_as(AnonymousUser()), view=None) is False


@pytest.mark.django_db
def test_metrics_viewer_group_migration_is_idempotent_and_reversible():
    from django.apps import apps as django_apps

    migration = importlib.import_module("core.migrations.0008_create_metrics_viewer_group")
    name = DjangoGroups.METRICS_VIEWER.value
    assert migration.GROUP_NAME == name

    # Running forward again when the group already exists must not fail or duplicate.
    migration.create_metrics_viewer_group(django_apps, None)
    assert Group.objects.filter(name=name).count() == 1

    # The reverse is a no-op: it must not delete a group that has members.
    run_python = migration.Migration.operations[0]
    assert run_python.reversible
    run_python.reverse_code(django_apps, None)
    assert Group.objects.filter(name=name).count() == 1

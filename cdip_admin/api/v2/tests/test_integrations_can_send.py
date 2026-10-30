import uuid

import pytest
from django.urls import reverse
from rest_framework import status

from integrations.models import Integration, IntegrationAction, IntegrationType


pytestmark = pytest.mark.django_db


@pytest.fixture
def pull_capable_type():
    integration_type = IntegrationType.objects.create(name="Pull Capable", value="pull_capable")
    IntegrationAction.objects.create(
        type=IntegrationAction.ActionTypes.PULL_DATA,
        name="Pull observations",
        value="pull_observations",
        integration_type=integration_type,
    )
    return integration_type


@pytest.fixture
def push_capable_type():
    integration_type = IntegrationType.objects.create(name="Push Capable", value="push_capable")
    IntegrationAction.objects.create(
        type=IntegrationAction.ActionTypes.PUSH_DATA,
        name="Push observations",
        value="push_observations",
        integration_type=integration_type,
    )
    return integration_type


@pytest.fixture
def no_actions_type():
    return IntegrationType.objects.create(name="No Actions", value="no_actions")


def _make_integration(organization, integration_type, name):
    return Integration.objects.create(
        type=integration_type, name=name, owner=organization,
        base_url="https://api.test.example.com",
    )


def test_can_send_true_when_provider_pulls_and_target_accepts_push(
    api_client, superuser, organization, pull_capable_type, push_capable_type,
):
    provider = _make_integration(organization, pull_capable_type, "Provider")
    target = _make_integration(organization, push_capable_type, "Target")
    api_client.force_authenticate(superuser)

    response = api_client.get(reverse("integrations-list"), {"can_send_to": target.id})

    assert response.status_code == status.HTTP_200_OK, response.content
    row = next(r for r in response.json()["results"] if r["id"] == str(provider.id))
    assert row["can_send"] is True
    assert row["reasons"] == []


def test_can_send_false_when_row_has_no_pull_action(
    api_client, superuser, organization, no_actions_type, push_capable_type,
):
    cannot_provide = _make_integration(organization, no_actions_type, "Cannot Provide")
    target = _make_integration(organization, push_capable_type, "Target")
    api_client.force_authenticate(superuser)

    response = api_client.get(reverse("integrations-list"), {"can_send_to": target.id})

    assert response.status_code == status.HTTP_200_OK, response.content
    row = next(r for r in response.json()["results"] if r["id"] == str(cannot_provide.id))
    assert row["can_send"] is False
    assert row["reasons"][0]["code"] == "no_pull_action"


def test_can_send_false_when_target_has_no_push_action(
    api_client, superuser, organization, pull_capable_type, no_actions_type,
):
    provider = _make_integration(organization, pull_capable_type, "Provider")
    cannot_receive = _make_integration(organization, no_actions_type, "Cannot Receive")
    api_client.force_authenticate(superuser)

    response = api_client.get(reverse("integrations-list"), {"can_send_to": cannot_receive.id})

    assert response.status_code == status.HTTP_200_OK, response.content
    row = next(r for r in response.json()["results"] if r["id"] == str(provider.id))
    assert row["can_send"] is False
    assert row["reasons"][0]["code"] == "no_push_action"


def test_can_send_omitted_without_query_param(api_client, superuser, organization, pull_capable_type):
    provider = _make_integration(organization, pull_capable_type, "Provider")
    api_client.force_authenticate(superuser)

    response = api_client.get(reverse("integrations-list"))

    assert response.status_code == status.HTTP_200_OK, response.content
    row = next(r for r in response.json()["results"] if r["id"] == str(provider.id))
    assert row["can_send"] is None
    assert row["reasons"] is None


def test_can_send_to_an_unknown_integration_does_not_error(
    api_client, superuser, organization, pull_capable_type,
):
    provider = _make_integration(organization, pull_capable_type, "Provider")
    api_client.force_authenticate(superuser)

    response = api_client.get(reverse("integrations-list"), {"can_send_to": str(uuid.uuid4())})

    assert response.status_code == status.HTTP_200_OK, response.content
    row = next(r for r in response.json()["results"] if r["id"] == str(provider.id))
    assert row["can_send"] is None

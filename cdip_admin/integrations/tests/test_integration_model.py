import pytest
from django.conf import settings
from ..models import Integration, OutboundIntegrationConfiguration


pytestmark = pytest.mark.django_db


def test_create_movebank_destination_v1_with_default_settings(other_organization, legacy_integration_type_movebank):
    integration = OutboundIntegrationConfiguration.objects.create(
        type=legacy_integration_type_movebank,
        name=f"Movebank Site",
        owner=other_organization,
        endpoint=f"https://api.test.movebank.com",
        # additional  # Not set, let it use defaults
    )
    assert integration.additional.get("broker") == "gcp_pubsub"
    assert integration.additional.get("topic") == settings.MOVEBANK_DISPATCHER_DEFAULT_TOPIC


def test_create_movebank_destination_v2_with_default_settings(other_organization, integration_type_movebank):
    integration = Integration.objects.create(
        type=integration_type_movebank,
        name=f"Movebank Site",
        owner=other_organization,
        base_url=f"https://api.test.movebank.com",
        # additional  # Not set, let it use defaults
    )
    assert integration.additional.get("broker") == "gcp_pubsub"
    assert integration.additional.get("topic") == settings.MOVEBANK_DISPATCHER_DEFAULT_TOPIC

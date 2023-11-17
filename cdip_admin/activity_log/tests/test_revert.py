import pytest

from integrations.models import Integration
from ..models import ActivityLog
from ..core import ActivityActions


pytestmark = pytest.mark.django_db


def test_revert_an_update(provider_lotek_panthera):
    # Rename an integration
    original_name = str(provider_lotek_panthera.name)
    original_settings = dict(**provider_lotek_panthera.additional)
    provider_lotek_panthera.name = "Lotek New Name"
    provider_lotek_panthera.additional = {"new_field": "new_value"}
    provider_lotek_panthera.save()
    # Get the related Activity Log
    activity_log = ActivityLog.objects.filter(integration=provider_lotek_panthera, value="integration_updated").first()
    assert activity_log
    assert activity_log.details.get("action") == ActivityActions.UPDATED.value
    assert activity_log.is_reversible
    assert activity_log.details.get("changes").get("name") == "Lotek New Name"
    assert activity_log.details.get("changes").get("additional") == {"new_field": "new_value"}
    # Revert the change
    activity_log.revert()
    provider_lotek_panthera.refresh_from_db()
    # Check that the integration name is back to the original value
    assert provider_lotek_panthera.name == original_name
    assert provider_lotek_panthera.additional == original_settings


def test_revert_a_create(integration_type_er, organization):
    # Create an integration
    integration = Integration.objects.create(
        type=integration_type_er,
        name=f"ER Site X",
        owner=organization,
        base_url=f"https://er-site-x.test.pamdas.org",
    )
    integration_id = str(integration.id)
    # Get the related Activity Log
    activity_log = ActivityLog.objects.filter(integration=integration, value="integration_created").first()
    assert activity_log
    assert activity_log.details.get("action") == ActivityActions.CREATED.value
    assert activity_log.is_reversible
    # Revert the creation
    activity_log.revert()
    # Check that the integration was deleted
    with pytest.raises(Integration.DoesNotExist):
        Integration.objects.get(id=integration_id)

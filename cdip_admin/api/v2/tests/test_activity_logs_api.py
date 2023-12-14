import pytest
from django.urls import reverse
from rest_framework import status
from activity_log.models import (
    ActivityLog
)
from integrations.models import get_user_integrations_qs

pytestmark = pytest.mark.django_db


def _test_list_activity_logs(api_client, user, expected_logs, params=None):
    api_client.force_authenticate(user)
    params = params or {}
    response = api_client.get(
        reverse("logs-list"),
        params
    )
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    logs = response_data["results"]
    assert len(logs) == len(expected_logs)
    for log, expected in zip(logs, expected_logs):
        assert log.get("created_at") == expected.created_at.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        assert log.get("log_level") == expected.log_level
        assert log.get("log_type") == str(expected.log_type)
        assert log.get("origin") == str(expected.origin)
        integration = log.get("integration", {})
        if integration:
            assert integration.get("id") == str(expected.integration.id)
        assert log.get("value") == expected.value
        assert log.get("title") == expected.title
        assert log.get("created_by") == (expected.created_by.username if expected.created_by else None)


def test_list_logs_as_superuser(
        api_client, superuser, provider_lotek_panthera, provider_movebank_ewt,
        integrations_list, observation_delivery_succeeded_event
):
    _test_list_activity_logs(
        api_client=api_client,
        user=superuser,
        expected_logs=ActivityLog.objects.order_by(
            "-created_at"  # Expect the most recent ones first by default
        )[:20]  # Expect paginated response
    )


def test_list_logs_in_reverse_order_as_superuser(
        api_client, superuser, provider_lotek_panthera, provider_movebank_ewt
):
    _test_list_activity_logs(
        api_client=api_client,
        user=superuser,
        params={
            "ordering": "created_at"
        },
        expected_logs=ActivityLog.objects.order_by(
            "created_at"  # Expect the oldest ones first
        )[:20]  # Expect paginated response
    )


def test_list_logs_as_org_admin(
        api_client, org_admin_user, provider_lotek_panthera, provider_movebank_ewt
):
    _test_list_activity_logs(
        api_client=api_client,
        user=org_admin_user,
        expected_logs=ActivityLog.objects.filter(integration=provider_lotek_panthera)[:20]  # Expect paginated response
    )


def test_filter_logs_by_integration_as_superuser(
        api_client, superuser, provider_lotek_panthera, provider_movebank_ewt
):
    integration_id = str(provider_movebank_ewt.id)
    _test_list_activity_logs(
        api_client=api_client,
        user=superuser,
        params={
            "integration": integration_id,
        },
        expected_logs=ActivityLog.objects.filter(integration=integration_id)[:20]  # Expect paginated response
    )


def test_filter_logs_by_integration_as_org_admin(
        api_client, org_admin_user, provider_lotek_panthera, provider_movebank_ewt,
        destination_movebank, smart_integration, integrations_list,
):
    integration_id = str(provider_lotek_panthera.id)
    _test_list_activity_logs(
        api_client=api_client,
        user=org_admin_user,
        params={
            "integration": integration_id,
        },
        expected_logs=ActivityLog.objects.filter(integration=integration_id)[:20]  # Expect paginated response
    )


def test_filter_logs_by_type_data_change_as_superuser(
        api_client, superuser, provider_lotek_panthera, provider_movebank_ewt,
        destination_movebank, smart_integration, integrations_list,
        observation_delivery_succeeded_event, observation_delivery_succeeded_event_2,
):
    _test_list_activity_logs(
        api_client=api_client,
        user=superuser,
        params={
            "log_type": ActivityLog.LogTypes.DATA_CHANGE.value,
        },
        expected_logs=ActivityLog.objects.filter(
            log_type=ActivityLog.LogTypes.DATA_CHANGE.value
        )[:20]  # Expect paginated response
    )


def test_filter_logs_by_type_data_change_as_org_admin(
        api_client, org_admin_user, provider_lotek_panthera, provider_movebank_ewt,
        destination_movebank, smart_integration, integrations_list,
        observation_delivery_succeeded_event, observation_delivery_succeeded_event_2,
):
    user_integrations = get_user_integrations_qs(user=org_admin_user)
    _test_list_activity_logs(
        api_client=api_client,
        user=org_admin_user,
        params={
            "log_type": ActivityLog.LogTypes.DATA_CHANGE.value,
        },
        expected_logs=ActivityLog.objects.filter(
            integration__in=user_integrations,
            log_type=ActivityLog.LogTypes.DATA_CHANGE.value
        )[:20]  # Expect paginated response
    )


def test_filter_logs_by_type_event_as_org_admin(
        api_client, org_admin_user_2, provider_lotek_panthera, provider_movebank_ewt,
        destination_movebank, smart_integration, integrations_list,
        observation_delivery_succeeded_event, observation_delivery_succeeded_event_2,
):
    integration_id = str(destination_movebank.id)
    user_integrations = get_user_integrations_qs(user=org_admin_user_2)
    _test_list_activity_logs(
        api_client=api_client,
        user=org_admin_user_2,
        params={
            "log_type": ActivityLog.LogTypes.EVENT.value,
        },
        expected_logs=ActivityLog.objects.filter(
            integration__in=user_integrations,
            log_type=ActivityLog.LogTypes.EVENT.value
        )
    )


def test_filter_logs_by_origin_portal_as_superuser(
        api_client, superuser, provider_lotek_panthera, provider_movebank_ewt,
        destination_movebank, smart_integration, integrations_list,
        observation_delivery_succeeded_event, observation_delivery_succeeded_event_2,
):
    _test_list_activity_logs(
        api_client=api_client,
        user=superuser,
        params={
            "origin": ActivityLog.Origin.PORTAL.value,
        },
        expected_logs=ActivityLog.objects.filter(
            origin=ActivityLog.Origin.PORTAL.value
        )[:20]  # Expect paginated response
    )


def test_filter_logs_by_origin_portal_as_org_admin(
        api_client, org_admin_user, provider_lotek_panthera, provider_movebank_ewt,
        destination_movebank, smart_integration, integrations_list,
        observation_delivery_succeeded_event, observation_delivery_succeeded_event_2,
):
    user_integrations = get_user_integrations_qs(user=org_admin_user)
    _test_list_activity_logs(
        api_client=api_client,
        user=org_admin_user,
        params={
            "origin": ActivityLog.Origin.PORTAL.value,
        },
        expected_logs=ActivityLog.objects.filter(
            integration__in=user_integrations,
            origin=ActivityLog.Origin.PORTAL.value
        )[:20]  # Expect paginated response
    )


def test_filter_logs_by_origin_dispatcher_as_org_admin(
        api_client, org_admin_user, provider_lotek_panthera, provider_movebank_ewt,
        destination_movebank, smart_integration,
        observation_delivery_succeeded_event, observation_delivery_succeeded_event_2,
):
    user_integrations = get_user_integrations_qs(user=org_admin_user)
    _test_list_activity_logs(
        api_client=api_client,
        user=org_admin_user,
        params={
            "origin": ActivityLog.Origin.PORTAL.value,
        },
        expected_logs=ActivityLog.objects.filter(
            integration__in=user_integrations,
            origin=ActivityLog.Origin.PORTAL.value
        )[:20]  # Expect paginated response
    )


def test_filter_logs_by_log_level_as_superuser(
        api_client, superuser, provider_lotek_panthera, provider_movebank_ewt,
        destination_movebank, smart_integration, integrations_list,
        observation_delivery_succeeded_event, observation_delivery_succeeded_event_2,
):
    _test_list_activity_logs(
        api_client=api_client,
        user=superuser,
        params={
            "log_level": ActivityLog.LogLevels.INFO.value,
        },
        expected_logs=ActivityLog.objects.filter(
            log_level__gte=ActivityLog.LogLevels.INFO.value
        )[:20]  # Expect paginated response
    )


def test_filter_logs_by_log_level_as_org_admin(
        api_client, org_admin_user, provider_lotek_panthera, provider_movebank_ewt,
        destination_movebank, smart_integration, integrations_list,
        observation_delivery_succeeded_event, observation_delivery_succeeded_event_2, observation_delivery_failed_event,
):
    user_integrations = get_user_integrations_qs(user=org_admin_user)
    _test_list_activity_logs(
        api_client=api_client,
        user=org_admin_user,
        params={
            "log_level": ActivityLog.LogLevels.ERROR.value,
        },
        expected_logs=ActivityLog.objects.filter(
            integration__in=user_integrations,
            log_level__gte=ActivityLog.LogLevels.ERROR.value
        )[:20]  # Expect paginated response
    )


def test_filter_logs_in_date_range_as_superuser(
        api_client, superuser, provider_lotek_panthera, provider_movebank_ewt,
        destination_movebank, smart_integration, integrations_list,
        observation_delivery_succeeded_event, observation_delivery_succeeded_event_2,
):
    selected_events = ActivityLog.objects.all()[2:4]
    start_datetime = selected_events[1].created_at.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    end_datetime = selected_events[0].created_at.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    _test_list_activity_logs(
        api_client=api_client,
        user=superuser,
        params={
            "from_date": start_datetime,
            "to_date": end_datetime,
        },
        expected_logs=selected_events
    )


def test_get_logs_with_multiple_filters_as_org_admin(
        api_client, org_admin_user, provider_lotek_panthera, provider_movebank_ewt,
        destination_movebank, smart_integration, integrations_list,
        observation_delivery_succeeded_event, observation_delivery_succeeded_event_2,
        observation_delivery_failed_event, observation_delivery_failed_event_2
):
    _test_list_activity_logs(
        api_client=api_client,
        user=org_admin_user,
        params={  # Get events of log level info or higher for a single connection from lotek to an ER site
            "from_date": observation_delivery_succeeded_event.created_at.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "integration__in": ",".join([str(provider_lotek_panthera.id), str(integrations_list[1].id)]),
            "log_level": ActivityLog.LogLevels.INFO.value,
            "log_type": ActivityLog.LogTypes.EVENT.value,
        },
        expected_logs=[observation_delivery_failed_event_2]  # Expect only this event matching the filtering criteria
    )


def test_search_logs_by_value_as_org_admin(
        api_client, org_admin_user, provider_lotek_panthera, provider_movebank_ewt,
        destination_movebank, smart_integration, integrations_list,
        observation_delivery_succeeded_event, observation_delivery_succeeded_event_2,
        observation_delivery_failed_event, observation_delivery_failed_event_2
):
    _test_list_activity_logs(
        api_client=api_client,
        user=org_admin_user,
        params={
            "search": "observation_delivery_failed"
        },
        expected_logs=[observation_delivery_failed_event_2]
    )


def test_search_logs_by_value_as_superuser(
        api_client, superuser, provider_lotek_panthera, provider_movebank_ewt,
        destination_movebank, smart_integration, integrations_list,
        observation_delivery_succeeded_event, observation_delivery_succeeded_event_2,
        observation_delivery_failed_event, observation_delivery_failed_event_2
):
    _test_list_activity_logs(
        api_client=api_client,
        user=superuser,
        params={
            "search": "observation_delivery_failed"
        },
        expected_logs=[observation_delivery_failed_event_2, observation_delivery_failed_event]
    )


def test_search_logs_and_filter_as_superuser(
        api_client, superuser, provider_lotek_panthera, provider_movebank_ewt,
        destination_movebank, smart_integration, integrations_list,
        observation_delivery_succeeded_event, observation_delivery_succeeded_event_2,
        observation_delivery_failed_event, observation_delivery_failed_event_2
):
    _test_list_activity_logs(
        api_client=api_client,
        user=superuser,
        params={
            "integration": str(destination_movebank.id),
            "log_type": ActivityLog.LogTypes.EVENT.value,
            "search": "movebank.com"
        },
        expected_logs=[observation_delivery_failed_event, observation_delivery_succeeded_event]
    )

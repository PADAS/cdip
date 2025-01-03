import pytest
from django_celery_beat.models import PeriodicTask
from django.conf import settings

from integrations.tasks import send_unhealthy_connections_email, calculate_integration_statuses
from integrations.models.v2 import Integration, ConnectionStatus, filter_connections_by_status

pytestmark = pytest.mark.django_db


def test_status_email_schedule_exists():
    assert PeriodicTask.objects.filter(task="integrations.tasks.send_unhealthy_connections_email").exists()


def test_send_unhealthy_connections_email_task(
        mocker, connection_with_healthy_provider_and_destination,
        connection_with_unhealthy_provider, connection_with_unhealthy_destination,
        connection_with_disabled_destination, connection_with_disabled_provider_and_unhealthy_destination
):
    mock_email_backend = mocker.MagicMock()
    mocker.patch("integrations.tasks.EmailMultiAlternatives", mock_email_backend)
    mock_email_render = mocker.MagicMock()
    mocker.patch("integrations.tasks.render_to_string", mock_email_render)

    calculate_integration_statuses(
        [
            connection_with_healthy_provider_and_destination.id,
            connection_with_unhealthy_provider.id,
            connection_with_unhealthy_destination.id,
            connection_with_disabled_destination.id,
            connection_with_disabled_provider_and_unhealthy_destination.id
        ]
    )

    send_unhealthy_connections_email()

    providers = Integration.providers.all()
    unhealthy_connections = filter_connections_by_status(queryset=providers, status=ConnectionStatus.UNHEALTHY.value)
    review_connections = filter_connections_by_status(queryset=providers, status=ConnectionStatus.NEEDS_REVIEW.value)
    disabled_connections = filter_connections_by_status(queryset=providers, status=ConnectionStatus.DISABLED.value)
    mock_email_render.assert_called_once()
    render_call = mock_email_render.mock_calls[0]
    assert render_call.args[0] == "unhealthy_connections_email.html"
    context = render_call.args[1]
    assert list(context["unhealthy_connections"]) == list(unhealthy_connections)
    assert list(context["review_connections"]) == list(review_connections)
    assert list(context["disabled_connections"]) == list(disabled_connections)

    mock_email = mock_email_backend.return_value
    mock_email.send.assert_called_once()
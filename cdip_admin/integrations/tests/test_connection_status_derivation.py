import pytest

from api.v2.serializers import ConnectionRetrieveSerializer
from integrations.models import Integration, ConnectionStatus
from integrations.models.v2 import filter_connections_by_status

pytestmark = pytest.mark.django_db


# A destination integration is shared across every connection that routes to it. Its health
# must therefore not drag a connection into the "unhealthy" bucket; an unhealthy or disabled
# destination is surfaced as "needs review" instead. These tests pin that derivation both for
# the queryset filter (filter_connections_by_status) and the live serializer (get_status).


def test_filter_unhealthy_excludes_connections_with_only_an_unhealthy_destination(
        connection_with_unhealthy_provider,
        connection_with_unhealthy_destination,
):
    providers = Integration.providers.all()
    unhealthy = filter_connections_by_status(providers, ConnectionStatus.UNHEALTHY.value)
    review = filter_connections_by_status(providers, ConnectionStatus.NEEDS_REVIEW.value)

    # Provider with its own errors -> unhealthy
    assert connection_with_unhealthy_provider in unhealthy
    # Healthy provider but unhealthy shared destination -> NOT unhealthy, needs review
    assert connection_with_unhealthy_destination not in unhealthy
    assert connection_with_unhealthy_destination in review


def test_filter_needs_review_includes_unhealthy_and_disabled_destinations(
        connection_with_unhealthy_destination,
        connection_with_disabled_destination,
):
    providers = Integration.providers.all()
    review = filter_connections_by_status(providers, ConnectionStatus.NEEDS_REVIEW.value)

    assert connection_with_unhealthy_destination in review
    assert connection_with_disabled_destination in review


def test_get_status_unhealthy_destination_resolves_to_needs_review(
        connection_with_unhealthy_provider,
        connection_with_unhealthy_destination,
):
    serializer = ConnectionRetrieveSerializer()

    assert serializer.get_status(connection_with_unhealthy_provider) == ConnectionStatus.UNHEALTHY.value
    assert serializer.get_status(connection_with_unhealthy_destination) == ConnectionStatus.NEEDS_REVIEW.value


def test_get_status_disabled_destination_resolves_to_needs_review(
        connection_with_disabled_destination,
):
    serializer = ConnectionRetrieveSerializer()

    assert serializer.get_status(connection_with_disabled_destination) == ConnectionStatus.NEEDS_REVIEW.value

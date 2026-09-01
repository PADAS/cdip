import pytest

from integrations.models import Integration, Route, RouteProvider, ensure_default_route


pytestmark = pytest.mark.django_db


# These use a provider type (Lotek) rather than an ER site on purpose:
# Integration._post_save deploys a dispatcher for ER/SMART/WPSWatch/TrapTagger
# sites whenever GCP_ENVIRONMENT_ENABLED is on, which reaches for GCP Secret
# Manager. A provider is also what ensure_default_route actually attaches.
def _make_integration(organization, integration_type, name):
    return Integration.objects.create(
        type=integration_type,
        name=name,
        owner=organization,
        base_url="https://api.test.lotek.com",
    )


def test_default_route_name_matches_integration_name(organization, integration_type_lotek):
    integration = _make_integration(organization, integration_type_lotek, "Kruger GPS")

    ensure_default_route(integration=integration)

    # The name the user typed, verbatim -- no " - Default Route" suffix.
    assert integration.default_route.name == "Kruger GPS"


def test_default_route_name_disambiguated_on_collision(organization, integration_type_lotek):
    existing_route = Route.objects.create(owner=organization, name="Kruger GPS")
    integration = _make_integration(organization, integration_type_lotek, "Kruger GPS")

    ensure_default_route(integration=integration)

    # A brand new route, not the owner's pre-existing one.
    assert integration.default_route.id != existing_route.id
    assert integration.default_route.name == "Kruger GPS (2)"
    # The pre-existing route must not have picked up the integration as a
    # provider -- that would leak data to whatever destinations it already has.
    assert not existing_route.data_providers.filter(id=integration.id).exists()
    assert integration.default_route.data_providers.filter(id=integration.id).exists()


def test_default_route_name_disambiguates_past_second_collision(organization, integration_type_lotek):
    Route.objects.create(owner=organization, name="Kruger GPS")
    Route.objects.create(owner=organization, name="Kruger GPS (2)")
    integration = _make_integration(organization, integration_type_lotek, "Kruger GPS")

    ensure_default_route(integration=integration)

    assert integration.default_route.name == "Kruger GPS (3)"


def test_default_route_name_ignores_same_name_route_of_another_owner(
        organization, other_organization, integration_type_lotek
):
    # Disambiguation is scoped to the owner, so another org's route of the same
    # name must not push this one to "(2)".
    Route.objects.create(owner=other_organization, name="Kruger GPS")
    integration = _make_integration(organization, integration_type_lotek, "Kruger GPS")

    ensure_default_route(integration=integration)

    assert integration.default_route.name == "Kruger GPS"


def test_default_route_name_falls_back_to_type_when_integration_name_blank(
        organization, integration_type_lotek
):
    # Integration.name is blank=True but Route.name is not, so a blank name must
    # not produce a route named "".
    integration = _make_integration(organization, integration_type_lotek, "")

    ensure_default_route(integration=integration)

    assert integration.default_route.name == f"{integration_type_lotek.name} Route"


def test_default_route_name_falls_back_when_name_is_whitespace_only(
        organization, integration_type_lotek
):
    # Route.name is validated with allow_blank=False, so "   " is rejected on a
    # later PATCH exactly like "" is. It has to take the same fallback.
    integration = _make_integration(organization, integration_type_lotek, "   ")

    ensure_default_route(integration=integration)

    assert integration.default_route.name == f"{integration_type_lotek.name} Route"


def test_default_route_name_is_stripped(organization, integration_type_lotek):
    integration = _make_integration(organization, integration_type_lotek, "  Kruger GPS  ")

    ensure_default_route(integration=integration)

    assert integration.default_route.name == "Kruger GPS"


def test_default_route_name_is_truncated_to_fit_the_field(organization, integration_type_lotek):
    long_name = "K" * 200  # Integration.name and Route.name are both max_length=200
    integration = _make_integration(organization, integration_type_lotek, long_name)

    ensure_default_route(integration=integration)

    # Truncated with room to spare for a disambiguation suffix.
    assert integration.default_route.name == "K" * 190


def test_long_name_still_fits_the_column_once_disambiguated(organization, integration_type_lotek):
    # This is what the truncation above is actually for: without it, the
    # collision suffix pushes the name past Route.name's 200 characters and
    # Postgres raises DataError.
    long_name = "K" * 200
    first = _make_integration(organization, integration_type_lotek, long_name)
    ensure_default_route(integration=first)

    second = Integration.objects.create(
        type=integration_type_lotek,
        name=long_name,
        owner=organization,
        base_url="https://api2.test.lotek.com",
    )
    ensure_default_route(integration=second)

    assert second.default_route.name == "K" * 190 + " (2)"
    assert len(second.default_route.name) <= 200


def test_ensure_default_route_uses_explicit_route_name(organization, integration_type_lotek):
    integration = _make_integration(organization, integration_type_lotek, "Kruger Connection")

    ensure_default_route(integration=integration, route_name="Kruger GPS")

    # An explicit route name wins over the connection's name, so the portal can
    # later name the Route independently of the Connection.
    assert integration.default_route.name == "Kruger GPS"
    assert integration.name == "Kruger Connection"


def test_whitespace_only_route_name_falls_back_to_the_integration_name(
        organization, integration_type_lotek
):
    # A blank route_name is not authoritative -- it means "derive it", so the
    # cascade has to reach integration.name and not jump to the type fallback.
    integration = _make_integration(organization, integration_type_lotek, "Kruger GPS")

    ensure_default_route(integration=integration, route_name="   ")

    assert integration.default_route.name == "Kruger GPS"


def test_route_name_is_stripped_when_given_explicitly(organization, integration_type_lotek):
    integration = _make_integration(organization, integration_type_lotek, "Kruger Connection")

    ensure_default_route(integration=integration, route_name="  Kruger GPS  ")

    assert integration.default_route.name == "Kruger GPS"


def test_blank_route_name_and_blank_integration_name_fall_back_to_type(
        organization, integration_type_lotek
):
    integration = _make_integration(organization, integration_type_lotek, "   ")

    ensure_default_route(integration=integration, route_name="   ")

    assert integration.default_route.name == f"{integration_type_lotek.name} Route"


def test_ensure_default_route_is_idempotent(organization, integration_type_lotek):
    integration = _make_integration(organization, integration_type_lotek, "Kruger GPS")

    ensure_default_route(integration=integration)
    route_id = integration.default_route.id

    ensure_default_route(integration=integration)

    assert integration.default_route.id == route_id
    assert Route.objects.filter(owner=organization, name="Kruger GPS").count() == 1
    assert RouteProvider.objects.filter(integration=integration, route_id=route_id).count() == 1

# Default Route Invariant Implementation Plan

> **Status (2026-09-21): delivered.** PR 1 → #475, PR 2 → #477 (+ admin follow-up #481), PR 3 → #478, PR 4 → #479, all merged to `main`. The checkboxes below are left as written; this document is kept as the record of how the work was sequenced. Where the shipped code departs from the steps here, the spec's §8a is authoritative.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `Integration.default_route` a real invariant — enforced on every code path that changes the provider↔route relationship, detected by the status pipeline and an audit command, and visible in Django admin — closing GUNDI-5731.

**Architecture:** One pure decision function (`decide_default_route`) computes the correct default for an integration given what is joining or leaving; everything else is plumbing that calls it. Signal receivers and a custom FK `on_delete` callable call it at write time (enforce); one annotated queryset defines "violation" for the status pipeline, an admin filter and a management command (detect); admin columns, a filter and change-page panels render the provider→route→destination graph (see). Delivered as four stacked PRs, each independently shippable; PR 1 closes the ticket.

**Tech Stack:** Django 4.2.24 (signals, `Collector.add_field_update`, `Exists`/`OuterRef`, admin `SimpleListFilter`), DRF, pytest-django, `ActivityLog`.

**Spec:** `docs/superpowers/specs/2026-09-18-default-route-invariant-design.md` — read it first; section numbers below (§4, §5.1 …) refer to it.

## Global Constraints

- Python 3.10+, Django 4.2.x, DRF. No new dependencies.
- Nothing is ever routed somewhere nobody chose: self-heal only when exactly one candidate exists; otherwise raise `AmbiguousDefaultRouteError` naming the candidates (§4.1).
- Every self-heal writes exactly one `ActivityLog` row: `origin=PORTAL`, `log_level=WARNING`, `log_type=EVENT`, `value="default_route_auto_assigned"`, `title=f"Default route set to '{route.name}'"`, `details={"route_id", "via", "previous_default_route_id"}`, `is_reversible=False` (§5.1).
- Destination-only integrations (provider on no route) are exempt from every check (§4).
- `PROTECT` is not used; deleting a provider's only route correctly leaves `default_route` NULL (§4.1).
- Receivers skip when `raw=True`.
- No data migration. Existing violations are repaired by an operator running `check_default_routes`, reading the output, then `--fix` (§7).
- All work is test-first. Tests live beside the app code (`integrations/tests/`, `api/v2/tests/`).
- Commit messages end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. PR bodies end with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

### Two reconciliations with the spec (decided while planning; both keep the spec's intent)

1. **Placeholder = "no destinations".** §4.1 describes a placeholder as "no destinations, no configuration", while §4 clause 3 defines the violation as "default has no destinations while another route does" regardless of configuration. The detector (§5.2) and the resolver must agree on what is broken, or `--fix` could never repair something the status pipeline flags. The resolver therefore uses "no destinations" only. A configured-but-empty default delivers nothing either way, and the switch is logged.
2. **A destination-side entry point (1b).** DRF's `ModelSerializer.create()` writes `data_providers` **before** `destinations`, so when the provider-join receiver fires for `POST /v2/routes/`, the new route has no destinations yet and looks like a placeholder itself; the switch in §4.1 row 2 would never happen and the §2.3 shape would persist. Two extra receivers — `post_save(RouteDestination)` and `m2m_changed(post_add)` on `Route.destinations.through` — re-run the decision for each provider on a route when destinations are added. Same helper, same idempotency, same log.

### Where the code lives (and why it differs slightly from §5.1's "in signals.py")

`reassign_default_route` is the FK's `on_delete` callable, so `models.py` must import it. `signals.py` imports `models`, so nothing `models.py` needs can live in `signals.py`. All default-route logic therefore lives in a new module `integrations/models/v2/default_route.py` (no model imports at module level; `apps.get_model` inside functions), and `signals.py` only wires receivers to it. The detection queryset lives in `services.py` as the spec says.

---

## Environment setup (once, before Task 1)

Work in a fresh worktree cut from `origin/main`. Run every command from the worktree root unless a step says otherwise.

```bash
cd /Users/chrisdo/padas/cdip
git fetch origin main
git worktree add .worktrees/default-route-invariant -b feature/default-route-invariant-enforce origin/main
cp cdip_admin/cdip_admin/local_settings.py .worktrees/default-route-invariant/cdip_admin/cdip_admin/local_settings.py
cd .worktrees/default-route-invariant
```

Test command (Postgres runs in the `cdip-postgres` docker container on 5432; a Redis broker must be listening on 30091 — start one with `docker run -d --rm --name tmp-redis-30091 -p 30091:6379 redis:7-alpine` if `docker ps` does not show it):

```bash
cd cdip_admin
export DB_HOST=localhost DB_PORT=5432 DB_USER=cdip_dbuser DB_PASSWORD=cdip_dbpassword DB_NAME=cdip_default_route
PY=/Users/chrisdo/padas/cdip/.venv/bin/python
$PY -m pytest integrations/tests/test_calc_integration_status.py -q --create-db   # first run only: builds test_cdip_default_route
# afterwards:
$PY -m pytest <path> -q
```

`pytest.ini` already sets `--reuse-db`; pass `--create-db` again only after adding a migration (Task 9). Pre-existing environmental failures exist in the suite (external-network `gaierror`, queryset-ordering flakes); confirm any suspicious failure in isolation before attributing it to your change.

## File structure

| File | Responsibility |
|---|---|
| `cdip_admin/integrations/models/v2/default_route.py` (new) | `AmbiguousDefaultRouteError`, `DefaultRouteDecision`, `route_has_destinations`, `decide_default_route`, `resolve_default_route`, `reassign_default_route` (on_delete), the ActivityLog writer. Pure logic, no receivers. |
| `cdip_admin/integrations/models/v2/__init__.py` | Re-export the above so `from integrations.models import …` works. |
| `cdip_admin/integrations/models/v2/models.py` | `Integration.default_route.on_delete = reassign_default_route` (PR 2). |
| `cdip_admin/integrations/migrations/0118_integration_default_route_on_delete.py` (new, PR 2) | State-only `AlterField`. |
| `cdip_admin/integrations/signals.py` | Receivers for entry points 1, 1b, 2, 4. |
| `cdip_admin/integrations/models/v2/services.py` | `DefaultRouteState`, `DEFAULT_ROUTE_STATUS_DETAILS`, `annotate_default_route_state`, `filter_by_default_route_state`, `providers_without_valid_default_route`, `get_default_route_state`; new branch in `calculate_integration_status` (PR 3). |
| `cdip_admin/integrations/management/commands/check_default_routes.py` (new, PR 3) | Audit / `--fix` / `--integration` / `--json`. |
| `cdip_admin/api/v2/serializers.py` | `AmbiguousDefaultRouteConflict(APIException)` (PR 2). |
| `cdip_admin/api/v2/views.py` | `RoutesView.handle_exception`, atomic `perform_update` (PR 2). |
| `cdip_admin/integrations/admin.py` | Refusal surfacing on `RouteAdmin` + inline formset (PR 2); visibility (PR 4). |
| Tests | `integrations/tests/test_default_route_invariant.py` (new: helper + signals + on_delete), `integrations/tests/test_default_route_detection.py` (new: queryset), `api/v2/tests/test_routes_api.py`, `integrations/tests/test_calc_integration_status.py`, `integrations/tests/test_commands.py`, `integrations/tests/test_admin.py`. |

### Test-building conventions used throughout

Signals are the thing under test, so **fixtures that set up a state must bypass signals**, otherwise the setup itself gets "repaired". Use these bypasses (they issue raw SQL and fire no signals):

```python
RouteProvider.objects.bulk_create([RouteProvider(integration=p, route=r)])       # link provider, no signals
RouteDestination.objects.bulk_create([RouteDestination(integration=d, route=r)]) # link destination, no signals
Integration.objects.filter(pk=p.pk).update(default_route=r)                      # set default, no signals
p.refresh_from_db()
```

When a test exercises a signal path, call the real API: `route.data_providers.add(p)`, `RouteProvider.objects.create(...)`, `route.data_providers.remove(p)`, `route.delete()`.

Existing fixtures used: `organization`, `other_organization`, `integration_type_lotek`, `integration_type_er`, `provider_lotek_panthera` (has a placeholder default via `ensure_default_route`), `integrations_list_er` (10 ER integrations, each with its own placeholder default), `destination_movebank` (no default route), `api_client`, `superuser`, `org_admin_user`, `admin_client` (pytest-django), `pull_observations_action_failed_activity_log{,_2,_3}`.

`local_settings.py` sets `GCP_ENVIRONMENT_ENABLED = False`, so `Integration.objects.create(type=integration_type_er, …)` does not try to deploy a dispatcher. (CI has no test job; the suite only runs locally with these settings.)

`IntegrationAdmin.list_display` includes `api_key`, a `cached_property` that calls Kong over HTTP for every row. Any test that renders the Integration **changelist** must patch it:

```python
@pytest.fixture
def mock_api_key_column(mocker, mock_get_api_key):
    mocker.patch("integrations.models.v2.models.Integration.api_key", mock_get_api_key)
```

(`mock_get_api_key` is an existing conftest fixture returning a `PropertyMock`.)

---

# PR 1 — Enforce on join; close GUNDI-5731

Branch: `feature/default-route-invariant-enforce` (from `origin/main`).

### Task 1: The decision helper and the ActivityLog writer

**Files:**
- Create: `cdip_admin/integrations/models/v2/default_route.py`
- Modify: `cdip_admin/integrations/models/v2/__init__.py`
- Test: `cdip_admin/integrations/tests/test_default_route_invariant.py` (new)

**Interfaces:**
- Produces:
  - `class AmbiguousDefaultRouteError(Exception)` with attributes `integration`, `candidates: list[Route]`.
  - `class DefaultRouteDecision(NamedTuple)`: `route: Route | None`, `changed: bool`.
  - `route_has_destinations(route) -> bool`
  - `decide_default_route(integration, *, leaving_route=None, joining_route=None, exclude_route_ids=()) -> DefaultRouteDecision` (raises `AmbiguousDefaultRouteError`).
  - `resolve_default_route(integration, *, leaving_route=None, joining_route=None, exclude_route_ids=(), via="") -> Route | None` — applies the decision (`save(update_fields=["default_route"])`) and logs when it changed to a non-NULL route.
  - `DEFAULT_ROUTE_AUTO_ASSIGNED = "default_route_auto_assigned"` (the `ActivityLog.value`).

- [ ] **Step 1: Write the failing tests**

Create `cdip_admin/integrations/tests/test_default_route_invariant.py`:

```python
"""Tests for the default-route invariant (spec: docs/superpowers/specs/2026-09-18-default-route-invariant-design.md).

Setup helpers bypass signals (bulk_create / QuerySet.update) so a test's
starting state is exactly what it says, even once the receivers exist.
"""
import uuid

import pytest

from activity_log.models import ActivityLog
from integrations.models import (
    Integration,
    Route,
    RouteDestination,
    RouteProvider,
    AmbiguousDefaultRouteError,
    decide_default_route,
    resolve_default_route,
    DEFAULT_ROUTE_AUTO_ASSIGNED,
)

pytestmark = pytest.mark.django_db


# --- helpers -----------------------------------------------------------------

@pytest.fixture
def make_provider(organization, integration_type_lotek):
    def _make(name="Provider"):
        return Integration.objects.create(
            type=integration_type_lotek,
            owner=organization,
            name=f"{name} {uuid.uuid4().hex[:6]}",
            base_url="https://api.test.lotek.com",
        )
    return _make


@pytest.fixture
def make_destination(organization, integration_type_er):
    def _make(name="ER Site"):
        return Integration.objects.create(
            type=integration_type_er,
            owner=organization,
            name=f"{name} {uuid.uuid4().hex[:6]}",
            base_url=f"https://{uuid.uuid4().hex[:8]}.pamdas.org",
        )
    return _make


@pytest.fixture
def make_route(organization):
    """Create a route and link providers/destinations WITHOUT firing signals."""
    def _make(name="Route", providers=(), destinations=()):
        route = Route.objects.create(owner=organization, name=f"{name} {uuid.uuid4().hex[:6]}")
        RouteProvider.objects.bulk_create([RouteProvider(integration=p, route=route) for p in providers])
        RouteDestination.objects.bulk_create([RouteDestination(integration=d, route=route) for d in destinations])
        return route
    return _make


def set_default(integration, route):
    """Set default_route without firing signals, then refresh the instance."""
    Integration.objects.filter(pk=integration.pk).update(default_route=route)
    integration.refresh_from_db()


def auto_assign_logs(integration):
    return ActivityLog.objects.filter(integration=integration, value=DEFAULT_ROUTE_AUTO_ASSIGNED)


# --- decide_default_route ----------------------------------------------------

def test_decide_no_routes_means_null(make_provider, make_route):
    provider = make_provider()
    orphan_default = make_route("Orphan")          # provider is NOT on it
    set_default(provider, orphan_default)

    decision = decide_default_route(provider)

    assert decision.route is None
    assert decision.changed is True


def test_decide_null_default_with_one_route_picks_it(make_provider, make_route):
    provider = make_provider()
    route = make_route("Only", providers=[provider])

    decision = decide_default_route(provider)

    assert decision.route == route
    assert decision.changed is True


def test_decide_keeps_valid_default(make_provider, make_destination, make_route):
    provider, er = make_provider(), make_destination()
    default = make_route("Default", providers=[provider], destinations=[er])
    make_route("Other", providers=[provider], destinations=[er])
    set_default(provider, default)

    decision = decide_default_route(provider)

    assert decision.route == default
    assert decision.changed is False


def test_decide_keeps_empty_default_when_no_other_route_delivers(make_provider, make_route):
    provider = make_provider()
    empty_default = make_route("Empty", providers=[provider])
    make_route("Also empty", providers=[provider])
    set_default(provider, empty_default)

    decision = decide_default_route(provider)

    assert decision.route == empty_default
    assert decision.changed is False


def test_decide_switches_empty_default_to_the_one_route_that_delivers(make_provider, make_destination, make_route):
    provider, er = make_provider(), make_destination()
    empty_default = make_route("Empty", providers=[provider])
    real = make_route("Real", providers=[provider], destinations=[er])
    set_default(provider, empty_default)

    decision = decide_default_route(provider)

    assert decision.route == real
    assert decision.changed is True


def test_decide_prefers_joining_route_when_default_is_null(make_provider, make_destination, make_route):
    provider, er = make_provider(), make_destination()
    make_route("A", providers=[provider], destinations=[er])
    joining = make_route("B", providers=[provider], destinations=[er])

    decision = decide_default_route(provider, joining_route=joining)

    assert decision.route == joining


def test_decide_does_not_prefer_an_empty_joining_route_over_a_delivering_one(make_provider, make_destination, make_route):
    provider, er = make_provider(), make_destination()
    empty_default = make_route("Empty default", providers=[provider])
    real = make_route("Real", providers=[provider], destinations=[er])
    joining_empty = make_route("Joining empty", providers=[provider])
    set_default(provider, empty_default)

    decision = decide_default_route(provider, joining_route=joining_empty)

    assert decision.route == real


def test_decide_raises_when_several_candidates(make_provider, make_destination, make_route):
    provider, er = make_provider(), make_destination()
    a = make_route("A", providers=[provider], destinations=[er])
    b = make_route("B", providers=[provider], destinations=[er])

    with pytest.raises(AmbiguousDefaultRouteError) as excinfo:
        decide_default_route(provider)

    assert excinfo.value.integration == provider
    assert {r.pk for r in excinfo.value.candidates} == {a.pk, b.pk}
    assert a.name in str(excinfo.value) and b.name in str(excinfo.value)


def test_decide_excludes_leaving_and_excluded_routes(make_provider, make_destination, make_route):
    provider, er = make_provider(), make_destination()
    default = make_route("Default", providers=[provider], destinations=[er])
    doomed = make_route("Doomed", providers=[provider], destinations=[er])
    survivor = make_route("Survivor", providers=[provider], destinations=[er])
    set_default(provider, default)

    decision = decide_default_route(provider, leaving_route=default, exclude_route_ids=[doomed.pk])

    assert decision.route == survivor
    assert decision.changed is True


# --- resolve_default_route ---------------------------------------------------

def test_resolve_assigns_and_logs_once(make_provider, make_route):
    provider = make_provider()
    route = make_route("Only", providers=[provider])

    assigned = resolve_default_route(provider, via="unit_test")

    provider.refresh_from_db()
    assert assigned == route
    assert provider.default_route == route
    log = auto_assign_logs(provider).get()
    assert log.origin == ActivityLog.Origin.PORTAL
    assert log.log_level == ActivityLog.LogLevels.WARNING
    assert log.log_type == ActivityLog.LogTypes.EVENT
    assert log.title == f"Default route set to '{route.name}'"
    assert log.details == {"route_id": str(route.pk), "via": "unit_test", "previous_default_route_id": None}
    assert log.is_reversible is False


def test_resolve_is_idempotent(make_provider, make_route):
    provider = make_provider()
    make_route("Only", providers=[provider])

    resolve_default_route(provider, via="unit_test")
    resolve_default_route(provider, via="unit_test")

    assert auto_assign_logs(provider).count() == 1


def test_resolve_records_previous_default(make_provider, make_destination, make_route):
    provider, er = make_provider(), make_destination()
    empty_default = make_route("Empty", providers=[provider])
    real = make_route("Real", providers=[provider], destinations=[er])
    set_default(provider, empty_default)

    resolve_default_route(provider, via="unit_test")

    log = auto_assign_logs(provider).get()
    assert log.details["previous_default_route_id"] == str(empty_default.pk)
    assert log.details["route_id"] == str(real.pk)


def test_resolve_to_null_does_not_log(make_provider, make_route):
    provider = make_provider()
    orphan = make_route("Orphan")
    set_default(provider, orphan)

    assert resolve_default_route(provider, via="unit_test") is None
    provider.refresh_from_db()
    assert provider.default_route is None
    assert auto_assign_logs(provider).count() == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `$PY -m pytest integrations/tests/test_default_route_invariant.py -q`
Expected: FAIL at import — `ImportError: cannot import name 'AmbiguousDefaultRouteError' from 'integrations.models'`.

- [ ] **Step 3: Write the module**

Create `cdip_admin/integrations/models/v2/default_route.py`:

```python
"""Keep ``Integration.default_route`` a real invariant.

Spec: docs/superpowers/specs/2026-09-18-default-route-invariant-design.md (§4, §5.1).

The routing service resolves a provider's destinations through
``Integration.default_route`` only, so for every integration that is a provider
on at least one route the default must (1) be set, (2) be one of its routes and
(3) not be an empty route while another of its routes has destinations.

This module holds the *decision* (``decide_default_route``) and the *apply +
log* step (``resolve_default_route``). ``integrations/signals.py`` calls them
from receivers; ``reassign_default_route`` is the FK's ``on_delete`` callable.
It lives beside ``models.py`` (not in ``signals.py``) because ``models.py`` has
to import the ``on_delete`` callable, and ``signals.py`` imports ``models``.
Model classes are looked up lazily for the same reason.
"""
import logging
from typing import NamedTuple, Optional

from django.apps import apps

logger = logging.getLogger(__name__)

DEFAULT_ROUTE_AUTO_ASSIGNED = "default_route_auto_assigned"


class AmbiguousDefaultRouteError(Exception):
    """Raised when an integration needs a new default route and more than one
    of its routes could be it. Nothing is routed somewhere nobody chose; a human
    has to pick (Admin → Integration → Default Routing Rule)."""

    def __init__(self, integration, candidates):
        self.integration = integration
        self.candidates = list(candidates)
        names = ", ".join(f"'{route.name}' ({route.pk})" for route in self.candidates)
        super().__init__(
            f"Cannot choose a default route for integration '{integration.name}' "
            f"({integration.pk}): it is a provider on several routes: {names}. "
            "Set its default route explicitly and retry."
        )


class DefaultRouteDecision(NamedTuple):
    route: Optional[object]  # a Route, or None when the integration is a provider on no route
    changed: bool            # True when ``route`` differs from the stored default


def route_has_destinations(route) -> bool:
    RouteDestination = apps.get_model("integrations", "RouteDestination")
    return RouteDestination.objects.filter(route_id=route.pk).exists()


def decide_default_route(integration, *, leaving_route=None, joining_route=None, exclude_route_ids=()):
    """Return the default route ``integration`` should have.

    ``leaving_route`` / ``exclude_route_ids``: routes the integration is about to
    stop being a provider on (or that are being deleted) — never candidates.
    ``joining_route``: a route it is joining (may not be in the DB relation yet);
    when a choice has to be made and this route is among the candidates, it wins
    (§4.1 rows 1–2: "provider joins a route" → that route).

    Raises ``AmbiguousDefaultRouteError`` when several routes could be the new
    default and ``joining_route`` does not disambiguate.
    """
    Route = apps.get_model("integrations", "Route")
    excluded = set(exclude_route_ids)
    if leaving_route is not None:
        excluded.add(leaving_route.pk)

    routes = {
        route.pk: route
        for route in Route.objects.filter(data_providers=integration.pk).exclude(pk__in=excluded)
    }
    if joining_route is not None and joining_route.pk not in excluded:
        routes.setdefault(joining_route.pk, joining_route)

    current_id = integration.default_route_id
    if not routes:
        # Not (or no longer) a provider: NULL is the correct value (§4.1 row 3).
        return DefaultRouteDecision(None, current_id is not None)

    current = routes.get(current_id)  # None when NULL, not a member, or leaving/excluded
    if current is not None:
        others_that_deliver = [
            route for route in routes.values()
            if route.pk != current.pk and route_has_destinations(route)
        ]
        if not others_that_deliver or route_has_destinations(current):
            return DefaultRouteDecision(current, False)  # §4 holds
        candidates = others_that_deliver  # §4 clause 3: empty default beside a delivering route
    else:
        candidates = list(routes.values())

    if joining_route is not None and any(c.pk == joining_route.pk for c in candidates):
        candidates = [c for c in candidates if c.pk == joining_route.pk]

    if len(candidates) == 1:
        chosen = candidates[0]
        return DefaultRouteDecision(chosen, chosen.pk != current_id)
    raise AmbiguousDefaultRouteError(integration, candidates)


def resolve_default_route(integration, *, leaving_route=None, joining_route=None, exclude_route_ids=(), via=""):
    """Apply ``decide_default_route`` to the database and log the change.

    Idempotent: a second call for the same state changes nothing and logs
    nothing, so entry points that fire more than once for one logical operation
    converge. ``via`` names the entry point in the ActivityLog row.
    """
    decision = decide_default_route(
        integration,
        leaving_route=leaving_route,
        joining_route=joining_route,
        exclude_route_ids=exclude_route_ids,
    )
    if not decision.changed:
        return decision.route
    previous_id = integration.default_route_id
    integration.default_route = decision.route
    integration.save(update_fields=["default_route"])
    if decision.route is not None:
        _log_auto_assignment(integration, decision.route, previous_id, via)
    return decision.route


def _log_auto_assignment(integration, route, previous_id, via):
    ActivityLog = apps.get_model("activity_log", "ActivityLog")
    try:
        ActivityLog.objects.create(
            log_level=ActivityLog.LogLevels.WARNING,
            log_type=ActivityLog.LogTypes.EVENT,
            origin=ActivityLog.Origin.PORTAL,
            integration=integration,
            value=DEFAULT_ROUTE_AUTO_ASSIGNED,
            title=f"Default route set to '{route.name}'"[:200],
            details={
                "route_id": str(route.pk),
                "via": via,
                "previous_default_route_id": str(previous_id) if previous_id else None,
            },
            is_reversible=False,
        )
    except Exception:  # logging must never undo a repair
        logger.exception(
            "Could not log default route auto-assignment",
            extra={"integration_id": str(integration.pk), "route_id": str(route.pk), "via": via},
        )
```

Then in `cdip_admin/integrations/models/v2/__init__.py`, add after the `.models` import block:

```python
from .default_route import (
    AmbiguousDefaultRouteError,
    DefaultRouteDecision,
    DEFAULT_ROUTE_AUTO_ASSIGNED,
    decide_default_route,
    resolve_default_route,
    route_has_destinations,
)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `$PY -m pytest integrations/tests/test_default_route_invariant.py -q`
Expected: 13 passed.

- [ ] **Step 5: Commit**

```bash
git add cdip_admin/integrations/models/v2/default_route.py cdip_admin/integrations/models/v2/__init__.py cdip_admin/integrations/tests/test_default_route_invariant.py
git commit -m "Add default route decision helper and auto-assignment log

decide_default_route() computes the default an integration should have
(spec §4/§4.1); resolve_default_route() applies it and writes one
ActivityLog row per change. Pure logic, no receivers yet.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Entry point 1 (+1b) — a provider joins a route, a route gains destinations

**Files:**
- Modify: `cdip_admin/integrations/signals.py`
- Test: `cdip_admin/integrations/tests/test_default_route_invariant.py`

**Interfaces:**
- Consumes: `resolve_default_route(integration, *, joining_route, via)` from Task 1.
- Produces receivers `on_route_provider_saved`, `on_route_providers_m2m_changed`, `on_route_destination_saved`, `on_route_destinations_m2m_changed` and helper `_provider_route_pairs(instance, reverse, pk_set)`. `via` values: `"route_provider_added"`, `"route_destination_added"`.

- [ ] **Step 1: Write the failing tests**

Append to `test_default_route_invariant.py`:

```python
# --- entry point 1: a provider joins a route ---------------------------------

def test_route_provider_create_sets_null_default(make_provider, make_route):
    provider = make_provider()
    route = make_route("New")

    RouteProvider.objects.create(integration=provider, route=route)

    provider.refresh_from_db()
    assert provider.default_route == route
    assert auto_assign_logs(provider).get().details["via"] == "route_provider_added"


def test_data_providers_add_sets_null_default(make_provider, make_route):
    provider = make_provider()
    route = make_route("New")

    route.data_providers.add(provider)

    provider.refresh_from_db()
    assert provider.default_route == route
    assert auto_assign_logs(provider).count() == 1


def test_data_providers_set_sets_null_default(make_provider, make_route):
    provider = make_provider()
    route = make_route("New")

    route.data_providers.set([provider])

    provider.refresh_from_db()
    assert provider.default_route == route


def test_reverse_add_sets_null_default(make_provider, make_route):
    provider = make_provider()
    route = make_route("New")

    provider.routing_rules_by_provider.add(route)

    provider.refresh_from_db()
    assert provider.default_route == route


def test_join_switches_empty_default_to_route_that_already_delivers(make_provider, make_destination, make_route):
    provider, er = make_provider(), make_destination()
    placeholder = make_route("Placeholder", providers=[provider])
    set_default(provider, placeholder)
    real = make_route("Real", destinations=[er])

    real.data_providers.add(provider)

    provider.refresh_from_db()
    assert provider.default_route == real
    log = auto_assign_logs(provider).get()
    assert log.details["via"] == "route_provider_added"
    assert log.details["previous_default_route_id"] == str(placeholder.pk)


def test_join_keeps_default_that_delivers(make_provider, make_destination, make_route):
    provider, er = make_provider(), make_destination()
    default = make_route("Default", providers=[provider], destinations=[er])
    set_default(provider, default)
    other = make_route("Other", destinations=[er])

    other.data_providers.add(provider)

    provider.refresh_from_db()
    assert provider.default_route == default
    assert auto_assign_logs(provider).count() == 0


# --- entry point 1b: a route gains destinations (DRF adds providers first) ----

def test_adding_destinations_after_providers_switches_empty_default(make_provider, make_destination, make_route):
    """Mirrors POST /v2/routes/: ModelSerializer writes data_providers, then destinations."""
    provider, er = make_provider(), make_destination()
    placeholder = make_route("Placeholder", providers=[provider])
    set_default(provider, placeholder)
    new_route = make_route("New")

    new_route.data_providers.add(provider)      # new_route is still empty → default stays
    provider.refresh_from_db()
    assert provider.default_route == placeholder

    new_route.destinations.add(er)              # now it delivers → switch

    provider.refresh_from_db()
    assert provider.default_route == new_route
    assert auto_assign_logs(provider).get().details["via"] == "route_destination_added"


def test_route_destination_create_switches_empty_default(make_provider, make_destination, make_route):
    provider, er = make_provider(), make_destination()
    placeholder = make_route("Placeholder", providers=[provider])
    set_default(provider, placeholder)
    new_route = make_route("New", providers=[provider])

    RouteDestination.objects.create(integration=er, route=new_route)

    provider.refresh_from_db()
    assert provider.default_route == new_route


def test_adding_destination_to_default_route_itself_changes_nothing(make_provider, make_destination, make_route):
    provider, er = make_provider(), make_destination()
    default = make_route("Default", providers=[provider])
    set_default(provider, default)

    default.destinations.add(er)

    provider.refresh_from_db()
    assert provider.default_route == default
    assert auto_assign_logs(provider).count() == 0


# --- raw / convergence ---------------------------------------------------------

def test_raw_save_is_skipped(make_provider, make_route):
    provider = make_provider()
    route = make_route("Fixture-loaded")

    RouteProvider(integration=provider, route=route).save_base(raw=True)

    provider.refresh_from_db()
    assert provider.default_route is None


def test_ensure_default_route_converges_without_auto_assign_log(make_provider):
    from integrations.models import ensure_default_route
    provider = make_provider()

    ensure_default_route(integration=provider)

    provider.refresh_from_db()
    assert provider.default_route is not None
    assert provider.default_route.data_providers.filter(pk=provider.pk).exists()
    assert auto_assign_logs(provider).count() == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `$PY -m pytest integrations/tests/test_default_route_invariant.py -q -k "route_provider_create or data_providers or reverse_add or join_ or destination or raw_save or converges"`
Expected: FAIL — `assert provider.default_route == route` (default is still None). `test_raw_save_is_skipped`, `test_join_keeps_default_that_delivers`, `test_adding_destination_to_default_route_itself_changes_nothing` and `test_ensure_default_route_converges…` pass already (nothing fires yet); that is fine.

- [ ] **Step 3: Add the receivers**

In `cdip_admin/integrations/signals.py`, replace the import lines at the top with:

```python
import logging

from django.db.models import QuerySet
from django.db.models.signals import m2m_changed, post_delete, post_save, pre_delete
from django.dispatch import receiver

from .models.v2 import (
    Integration,
    IntegrationConfiguration,
    Route,
    RouteDestination,
    RouteProvider,
    resolve_default_route,
)
```

and append at the end of the file:

```python
# ---------------------------------------------------------------------------
# Default route invariant (spec: docs/superpowers/specs/2026-09-18-default-route-invariant-design.md §5.1)
#
# Django splits "a provider joined a route" in two: RouteProvider.objects.create()
# fires post_save on the through model, while route.data_providers.add()/.set()
# bulk-insert and fire only m2m_changed. Both are handled; the helper is
# idempotent so double-firing converges.
# ---------------------------------------------------------------------------

def _provider_route_pairs(instance, reverse, pk_set):
    """(integration, route) pairs for an m2m_changed event on Route.data_providers.

    reverse=False: ``instance`` is the Route and ``pk_set`` holds Integration ids.
    reverse=True: ``instance`` is the Integration and ``pk_set`` holds Route ids.
    Fresh instances are fetched so cached ``default_route`` values are not stale.
    """
    if not pk_set:
        return []
    if reverse:
        return [(instance, route) for route in Route.objects.filter(pk__in=pk_set)]
    return [(integration, instance) for integration in Integration.objects.filter(pk__in=pk_set)]


@receiver(post_save, sender=RouteProvider)
def on_route_provider_saved(sender, instance, created, raw=False, **kwargs):
    """Entry point 1 (RouteProvider.objects.create / .save)."""
    if raw or not created:
        return
    integration = Integration.objects.get(pk=instance.integration_id)
    resolve_default_route(integration, joining_route=instance.route, via="route_provider_added")


@receiver(m2m_changed, sender=RouteProvider)
def on_route_providers_m2m_changed(sender, instance, action, reverse, pk_set, **kwargs):
    """Entry point 1 (route.data_providers.add/.set, integration.routing_rules_by_provider.add)."""
    if action == "post_add":
        for integration, route in _provider_route_pairs(instance, reverse, pk_set):
            resolve_default_route(integration, joining_route=route, via="route_provider_added")


def _reconsider_providers_of(route):
    """Entry point 1b: a route gained destinations. Any provider on it whose
    default is an empty route should now switch to this one (§4 clause 3)."""
    for integration in Integration.objects.filter(routing_rules_by_provider=route):
        resolve_default_route(integration, joining_route=route, via="route_destination_added")


@receiver(post_save, sender=RouteDestination)
def on_route_destination_saved(sender, instance, created, raw=False, **kwargs):
    if raw or not created:
        return
    _reconsider_providers_of(instance.route)


@receiver(m2m_changed, sender=RouteDestination)
def on_route_destinations_m2m_changed(sender, instance, action, reverse, pk_set, **kwargs):
    if action != "post_add":
        return
    routes = Route.objects.filter(pk__in=pk_set) if reverse else [instance]
    for route in routes:
        _reconsider_providers_of(route)
```

(`QuerySet` and `pre_delete` imports are used in Task 5; keeping them now avoids churn. `Route` is needed here.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `$PY -m pytest integrations/tests/test_default_route_invariant.py -q`
Expected: 24 passed.

- [ ] **Step 5: Run the neighbouring suites for regressions**

Run: `$PY -m pytest integrations/tests/test_signals.py integrations/tests/test_actions_scheduling.py integrations/tests/test_convert_bridge_integration.py api/v2/tests/test_routes_api.py api/v2/tests/test_connections_api.py api/v2/tests/test_integrations_api.py -q`
Expected: all pass. Fixtures like `route_1`/`route_2` now legitimately switch `provider_lotek_panthera`/`provider_movebank_ewt` defaults from their placeholders to the route with destinations; existing tests only use `provider.default_route` as "a route the provider is on", which still holds. If a test asserts the placeholder *is* the default after joining a delivering route, that assertion encodes the bug — update it and say so in the commit.

- [ ] **Step 6: Commit**

```bash
git add cdip_admin/integrations/signals.py cdip_admin/integrations/tests/test_default_route_invariant.py
git commit -m "Set default_route when a provider joins a route or a route gains destinations

post_save(RouteProvider) and m2m_changed(post_add) catch every way a
provider joins a route (create, .add, .set, reverse add). Because DRF
writes data_providers before destinations, post_save(RouteDestination)
and m2m_changed on destinations re-run the decision so an empty
placeholder default switches to the route that actually delivers.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Entry point 4 — `default_route` set directly

**Files:**
- Modify: `cdip_admin/integrations/signals.py`
- Test: `cdip_admin/integrations/tests/test_default_route_invariant.py`

**Interfaces:**
- Produces receiver `on_integration_saved_ensure_membership` (post_save Integration).

- [ ] **Step 1: Write the failing tests**

Append:

```python
# --- entry point 4: default_route set directly --------------------------------

def test_setting_default_route_directly_adds_provider_membership(make_provider, make_route):
    provider = make_provider()
    route = make_route("Chosen")

    provider.default_route = route
    provider.save()

    assert RouteProvider.objects.filter(integration=provider, route=route).exists()
    provider.refresh_from_db()
    assert provider.default_route == route
    assert auto_assign_logs(provider).count() == 0   # a human chose it; nothing was auto-assigned


def test_setting_default_route_via_update_fields_adds_membership(make_provider, make_route):
    provider = make_provider()
    route = make_route("Chosen")

    provider.default_route = route
    provider.save(update_fields=["default_route"])

    assert RouteProvider.objects.filter(integration=provider, route=route).exists()


def test_saving_unrelated_fields_does_not_touch_membership(make_provider, make_route):
    provider = make_provider()
    orphan = make_route("Orphan")
    set_default(provider, orphan)                     # broken state, set without signals

    provider.name = "renamed"
    provider.save(update_fields=["name"])

    assert not RouteProvider.objects.filter(integration=provider, route=orphan).exists()


def test_raw_integration_save_is_skipped(make_provider, make_route):
    provider = make_provider()
    route = make_route("Chosen")
    provider.default_route = route

    provider.save_base(raw=True)

    assert not RouteProvider.objects.filter(integration=provider, route=route).exists()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `$PY -m pytest integrations/tests/test_default_route_invariant.py -q -k "directly or update_fields_adds or unrelated_fields or raw_integration"`
Expected: 2 FAIL (`…directly…`, `…update_fields_adds…`: RouteProvider does not exist), 2 pass.

- [ ] **Step 3: Add the receiver**

Append to `signals.py`:

```python
@receiver(post_save, sender=Integration)
def on_integration_saved_ensure_membership(sender, instance, raw=False, update_fields=None, **kwargs):
    """Entry point 4: ``default_route`` set directly (admin, ORM, ensure_default_route).

    An integration must be a provider on its default route (§4 clause 2), so
    add the RouteProvider row if it is missing — what ensure_default_route()
    already does for the API path. post_save (not pre_save) because the
    through-row needs the integration's PK.
    """
    if raw or instance.default_route_id is None:
        return
    if update_fields is not None and "default_route" not in update_fields:
        return
    if not RouteProvider.objects.filter(integration_id=instance.pk, route_id=instance.default_route_id).exists():
        RouteProvider.objects.create(integration=instance, route_id=instance.default_route_id)
```

`RouteProvider.objects.create` fires entry point 1, which finds the default already valid and does nothing — convergence, not recursion.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `$PY -m pytest integrations/tests/test_default_route_invariant.py -q`
Expected: 28 passed.

- [ ] **Step 5: Commit**

```bash
git add cdip_admin/integrations/signals.py cdip_admin/integrations/tests/test_default_route_invariant.py
git commit -m "Make an integration a provider on any default_route set directly

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: GUNDI-5731 end-to-end tests, full regression run, open PR 1

**Files:**
- Test: `cdip_admin/api/v2/tests/test_routes_api.py`

**Interfaces:**
- Consumes: the receivers from Task 2 (no new code expected — these tests prove the ticket is closed).

- [ ] **Step 1: Write the tests**

Append to `cdip_admin/api/v2/tests/test_routes_api.py` (add `from integrations.models import Integration, ensure_default_route` to the existing import from `integrations.models`):

```python
# --- GUNDI-5731: POST /v2/routes/ must maintain Integration.default_route -----

def _post_route(api_client, user, owner, providers, destinations, name="Route"):
    api_client.force_authenticate(user)
    response = api_client.post(
        reverse("routes-list"),
        data={
            "name": name,
            "owner": str(owner.id),
            "data_providers": [str(p.id) for p in providers],
            "destinations": [str(d.id) for d in destinations],
            "additional": {},
        },
        format="json",
    )
    assert response.status_code == status.HTTP_201_CREATED, response.content
    return Route.objects.get(id=response.json()["id"])


def test_create_route_sets_default_for_provider_without_one(
    api_client, superuser, organization, integration_type_lotek, integrations_list_er
):
    """GUNDI-5731 scenario 1: a connection created without a default route,
    then 'Create Route' with a destination → that route becomes the default."""
    provider = Integration.objects.create(
        type=integration_type_lotek, owner=organization,
        name="Lotek without default", base_url="https://api.test.lotek.com",
    )
    assert provider.default_route is None

    route = _post_route(api_client, superuser, organization, [provider], [integrations_list_er[0]])

    provider.refresh_from_db()
    assert provider.default_route == route


def test_create_route_switches_empty_placeholder_default_to_new_route(
    api_client, superuser, organization, integration_type_lotek, integrations_list_er
):
    """GUNDI-5731 scenario 2 (spec §2.3): connection created WITH an empty
    default route, then 'Create Route + destination' → the default must move to
    the route carrying the destinations, not stay on the empty one."""
    provider = Integration.objects.create(
        type=integration_type_lotek, owner=organization,
        name="Lotek with placeholder", base_url="https://api.test.lotek.com",
    )
    ensure_default_route(integration=provider)
    placeholder = provider.default_route
    assert not placeholder.destinations.exists()

    route = _post_route(api_client, superuser, organization, [provider], [integrations_list_er[0]])

    provider.refresh_from_db()
    assert provider.default_route == route
    assert Route.objects.filter(pk=placeholder.pk).exists()  # the placeholder is left alone


def test_create_reverse_flow_route_sets_default_for_destination_site(
    api_client, superuser, organization, integration_type_er, provider_lotek_panthera
):
    """GUNDI-5731 entry point 2 (handleEnableReverseFlow): an ER site that so far
    was destination-only becomes a provider on a new route → that route is its default."""
    er_site = Integration.objects.create(
        type=integration_type_er, owner=organization,
        name="ER site enabling reverse flow", base_url="https://reverse.pamdas.org",
    )
    assert er_site.default_route is None

    route = _post_route(api_client, superuser, organization, [er_site], [provider_lotek_panthera], name="Reverse")

    er_site.refresh_from_db()
    assert er_site.default_route == route
```

- [ ] **Step 2: Run them**

Run: `$PY -m pytest api/v2/tests/test_routes_api.py -q -k "GUNDI or default_for_provider or placeholder_default or reverse_flow"`
Expected: 3 passed (they pass against Task 2's receivers; if any fails, the receivers are wrong — fix the receiver, not the test).

- [ ] **Step 3: Full regression run**

Run: `$PY -m pytest integrations api/v2 activity_log -q -x --ignore=integrations/tests/test_metrics.py 2>&1 | tail -20`
Expected: pass, apart from known environmental failures (confirm each in isolation).

- [ ] **Step 4: Commit and open PR 1**

```bash
git add cdip_admin/api/v2/tests/test_routes_api.py
git commit -m "Reproduce GUNDI-5731 end to end through POST /v2/routes/

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
git push -u origin feature/default-route-invariant-enforce
gh pr create --base main --title "Keep Integration.default_route set when a provider joins a route (GUNDI-5731)" --body-file - <<'EOF'
## What

PR 1 of 4 for the default route invariant (spec: `docs/superpowers/specs/2026-09-18-default-route-invariant-design.md`, plan: `docs/superpowers/plans/2026-09-18-default-route-invariant.md`).

`Integration.default_route` is the only route the routing service consults for a provider, and only the v2 integration-create API maintained it. This PR adds the decision helper and the "join" entry points:

- `decide_default_route()` / `resolve_default_route()` in `integrations/models/v2/default_route.py` — self-heal when exactly one candidate, raise `AmbiguousDefaultRouteError` otherwise; every self-heal is one `ActivityLog` row (`default_route_auto_assigned`).
- `post_save(RouteProvider)` + `m2m_changed(post_add)` — a provider joining a route (create, `.add`, `.set`, reverse add) gets a default if it has none, or switches from an empty placeholder to the route that delivers.
- `post_save(RouteDestination)` + `m2m_changed(post_add)` on destinations — DRF writes providers before destinations, so the switch has to be re-evaluated when destinations land.
- `post_save(Integration)` — a default set directly makes the integration a provider on it.

Closes GUNDI-5731 (both entry points in the ticket reproduced in `api/v2/tests/test_routes_api.py`).

## Next PRs

2: leave/delete entry points (custom `on_delete`), refusal surfacing in admin and API · 3: detection (status pipeline, `check_default_routes`) · 4: admin visibility.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
```

---

# PR 2 — Enforce on leave and delete; surface refusals

Branch: `feature/default-route-invariant-delete` cut from `feature/default-route-invariant-enforce` (retarget to `main` after PR 1 merges).

```bash
git checkout -b feature/default-route-invariant-delete
```

### Task 5: Entry point 2 — a provider leaves a route

**Files:**
- Modify: `cdip_admin/integrations/signals.py`
- Test: `cdip_admin/integrations/tests/test_default_route_invariant.py`

**Interfaces:**
- Consumes: `resolve_default_route(integration, *, leaving_route, exclude_route_ids, via)`.
- Produces: receiver `on_route_provider_pre_delete` (pre_delete RouteProvider), `pre_remove`/`pre_clear` branches in `on_route_providers_m2m_changed`, helper `_origin_model(origin)`. `via` values: `"route_provider_removed"`, `"route_deleted"`.

- [ ] **Step 1: Write the failing tests**

Append:

```python
# --- entry point 2: a provider leaves a route ----------------------------------

@pytest.fixture
def provider_on_three_delivering_routes(make_provider, make_destination, make_route):
    """default=R1; also on R2 and R3; all three deliver. Removing from R1 is ambiguous."""
    provider, er = make_provider(), make_destination()
    r1 = make_route("R1", providers=[provider], destinations=[er])
    r2 = make_route("R2", providers=[provider], destinations=[er])
    r3 = make_route("R3", providers=[provider], destinations=[er])
    set_default(provider, r1)
    return provider, r1, r2, r3


def test_remove_from_default_route_with_one_other_reassigns(make_provider, make_destination, make_route):
    provider, er = make_provider(), make_destination()
    r1 = make_route("R1", providers=[provider], destinations=[er])
    r2 = make_route("R2", providers=[provider], destinations=[er])
    set_default(provider, r1)

    r1.data_providers.remove(provider)

    provider.refresh_from_db()
    assert provider.default_route == r2
    log = auto_assign_logs(provider).get()
    assert log.details["via"] == "route_provider_removed"
    assert log.details["previous_default_route_id"] == str(r1.pk)


def test_remove_from_default_route_with_several_others_refuses(provider_on_three_delivering_routes):
    provider, r1, r2, r3 = provider_on_three_delivering_routes

    with pytest.raises(AmbiguousDefaultRouteError) as excinfo:
        r1.data_providers.remove(provider)

    assert {r.pk for r in excinfo.value.candidates} == {r2.pk, r3.pk}
    provider.refresh_from_db()
    assert provider.default_route == r1
    assert RouteProvider.objects.filter(integration=provider, route=r1).exists()


def test_remove_from_only_route_nulls_default(make_provider, make_route):
    provider = make_provider()
    only = make_route("Only", providers=[provider])
    set_default(provider, only)

    only.data_providers.remove(provider)

    provider.refresh_from_db()
    assert provider.default_route is None
    assert auto_assign_logs(provider).count() == 0


def test_remove_from_non_default_route_keeps_default(make_provider, make_destination, make_route):
    provider, er = make_provider(), make_destination()
    default = make_route("Default", providers=[provider], destinations=[er])
    other = make_route("Other", providers=[provider], destinations=[er])
    set_default(provider, default)

    other.data_providers.remove(provider)

    provider.refresh_from_db()
    assert provider.default_route == default
    assert auto_assign_logs(provider).count() == 0


def test_clear_providers_nulls_default_of_single_route_provider(make_provider, make_route):
    provider = make_provider()
    only = make_route("Only", providers=[provider])
    set_default(provider, only)

    only.data_providers.clear()

    provider.refresh_from_db()
    assert provider.default_route is None


def test_reverse_clear_nulls_default(make_provider, make_destination, make_route):
    provider, er = make_provider(), make_destination()
    r1 = make_route("R1", providers=[provider], destinations=[er])
    make_route("R2", providers=[provider], destinations=[er])
    set_default(provider, r1)

    provider.routing_rules_by_provider.clear()

    provider.refresh_from_db()
    assert provider.default_route is None


def test_set_replacing_provider_reassigns_the_leaver(make_provider, make_destination, make_route):
    leaver, newcomer, er = make_provider("Leaver"), make_provider("Newcomer"), make_destination()
    r1 = make_route("R1", providers=[leaver], destinations=[er])
    r2 = make_route("R2", providers=[leaver], destinations=[er])
    set_default(leaver, r1)

    r1.data_providers.set([newcomer])

    leaver.refresh_from_db(); newcomer.refresh_from_db()
    assert leaver.default_route == r2
    assert newcomer.default_route == r1


def test_route_provider_queryset_delete_reassigns(make_provider, make_destination, make_route):
    provider, er = make_provider(), make_destination()
    r1 = make_route("R1", providers=[provider], destinations=[er])
    r2 = make_route("R2", providers=[provider], destinations=[er])
    set_default(provider, r1)

    RouteProvider.objects.filter(integration=provider, route=r1).delete()

    provider.refresh_from_db()
    assert provider.default_route == r2
    assert auto_assign_logs(provider).count() == 1


def test_deleting_the_integration_itself_is_not_blocked(provider_on_three_delivering_routes):
    provider, *_ = provider_on_three_delivering_routes
    provider_id = provider.pk

    provider.delete()

    assert not Integration.objects.filter(pk=provider_id).exists()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `$PY -m pytest integrations/tests/test_default_route_invariant.py -q -k "remove_from or clear or set_replacing or queryset_delete_reassigns or integration_itself"`
Expected: FAIL for reassign/refuse/null cases (default unchanged); `test_deleting_the_integration_itself_is_not_blocked` passes.

- [ ] **Step 3: Add the receivers**

In `signals.py`, extend `on_route_providers_m2m_changed`:

```python
@receiver(m2m_changed, sender=RouteProvider)
def on_route_providers_m2m_changed(sender, instance, action, reverse, pk_set, **kwargs):
    """Entry points 1 and 2 for route.data_providers.add/.set/.remove/.clear and the reverse accessor.

    ``pre_remove``/``pre_clear`` (not post_*) so the relationship still exists
    and "other routes" is computable; a raised AmbiguousDefaultRouteError aborts
    the operation inside the caller's transaction.
    """
    if action == "post_add":
        for integration, route in _provider_route_pairs(instance, reverse, pk_set):
            resolve_default_route(integration, joining_route=route, via="route_provider_added")
    elif action == "pre_remove":
        for integration, route in _provider_route_pairs(instance, reverse, pk_set):
            resolve_default_route(integration, leaving_route=route, via="route_provider_removed")
    elif action == "pre_clear":
        if reverse:  # instance is the Integration: it leaves every route
            route_ids = list(instance.routing_rules_by_provider.values_list("pk", flat=True))
            resolve_default_route(instance, exclude_route_ids=route_ids, via="route_provider_removed")
        else:        # instance is the Route: every provider leaves it
            for integration in Integration.objects.filter(routing_rules_by_provider=instance):
                resolve_default_route(integration, leaving_route=instance, via="route_provider_removed")
```

and append:

```python
def _origin_model(origin):
    """Model class behind ``pre_delete``'s ``origin`` (the instance or queryset
    whose .delete() started the cascade), or None."""
    if origin is None:
        return None
    if isinstance(origin, QuerySet):
        return origin.model
    return type(origin)


@receiver(pre_delete, sender=RouteProvider)
def on_route_provider_pre_delete(sender, instance, **kwargs):
    """Entry point 2 for RouteProvider rows deleted directly or cascaded from a Route delete.

    Only runs when the delete started at a Route or a RouteProvider. When it
    started at the Integration (or anything that cascades to it, e.g. an
    Organization) the provider itself is going away and reassigning its default
    would be pointless — and could refuse a legitimate delete.
    """
    origin_model = _origin_model(kwargs.get("origin"))
    if origin_model is Route or (origin_model is not None and issubclass(origin_model, Route)):
        via = "route_deleted"
    elif origin_model is None or issubclass(origin_model, RouteProvider):
        via = "route_provider_removed"
    else:
        return
    try:
        integration = Integration.objects.get(pk=instance.integration_id)
    except Integration.DoesNotExist:
        return
    resolve_default_route(integration, leaving_route=instance.route, via=via)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `$PY -m pytest integrations/tests/test_default_route_invariant.py -q`
Expected: 37 passed. (`.remove()` fires `pre_remove` **and** `pre_delete` on the through rows; the second call finds the default already valid, so there is still exactly one log.)

- [ ] **Step 5: Commit**

```bash
git add cdip_admin/integrations/signals.py cdip_admin/integrations/tests/test_default_route_invariant.py
git commit -m "Reassign or refuse when a provider leaves its default route

pre_remove/pre_clear on Route.data_providers and pre_delete(RouteProvider)
run before the relationship is gone, so the remaining routes are known:
one → assign and log; several → AmbiguousDefaultRouteError aborts the
operation. Cascades that start at the Integration are left alone.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: Entry point 3 — custom `on_delete` for route deletion, plus migration

**Files:**
- Modify: `cdip_admin/integrations/models/v2/default_route.py`
- Modify: `cdip_admin/integrations/models/v2/models.py:296-303`
- Modify: `cdip_admin/integrations/models/v2/__init__.py`
- Create: `cdip_admin/integrations/migrations/0118_integration_default_route_on_delete.py` (generated)
- Test: `cdip_admin/integrations/tests/test_default_route_invariant.py`

**Interfaces:**
- Produces `reassign_default_route(collector, field, sub_objs, using)` — Django `on_delete` signature.

- [ ] **Step 1: Write the failing tests**

Append:

```python
# --- entry point 3: a route is deleted (custom on_delete) -----------------------

def test_reassignment_survives_deleting_the_default_route(make_provider, make_destination, make_route):
    """A pre_delete(Route) receiver would be undone by the collector's SET_NULL;
    the custom on_delete must not be."""
    provider, er = make_provider(), make_destination()
    r1 = make_route("R1", providers=[provider], destinations=[er])
    r2 = make_route("R2", providers=[provider], destinations=[er])
    set_default(provider, r1)

    r1.delete()

    provider.refresh_from_db()
    assert provider.default_route == r2
    log = auto_assign_logs(provider).get()
    assert log.details["via"] == "route_deleted"


def test_deleting_the_only_route_nulls_default(make_provider, make_route):
    provider = make_provider()
    only = make_route("Only", providers=[provider])
    set_default(provider, only)

    only.delete()

    provider.refresh_from_db()
    assert provider.default_route is None
    assert auto_assign_logs(provider).count() == 0


def test_deleting_default_route_with_several_others_refuses(provider_on_three_delivering_routes):
    provider, r1, r2, r3 = provider_on_three_delivering_routes

    with pytest.raises(AmbiguousDefaultRouteError) as excinfo:
        r1.delete()

    assert {r.pk for r in excinfo.value.candidates} == {r2.pk, r3.pk}
    assert Route.objects.filter(pk=r1.pk).exists()
    provider.refresh_from_db()
    assert provider.default_route == r1


def test_queryset_delete_spanning_routes_excludes_doomed_from_candidates(provider_on_three_delivering_routes):
    provider, r1, r2, r3 = provider_on_three_delivering_routes

    Route.objects.filter(pk__in=[r1.pk, r2.pk]).delete()

    provider.refresh_from_db()
    assert provider.default_route == r3
    assert auto_assign_logs(provider).count() == 1


def test_deleting_a_non_default_route_keeps_default(make_provider, make_destination, make_route):
    provider, er = make_provider(), make_destination()
    default = make_route("Default", providers=[provider], destinations=[er])
    other = make_route("Other", providers=[provider], destinations=[er])
    set_default(provider, default)

    other.delete()

    provider.refresh_from_db()
    assert provider.default_route == default


def test_deleting_the_organization_cascades_without_refusal(provider_on_three_delivering_routes, organization):
    """Routes and integrations go together; nothing to reassign, nothing to refuse."""
    provider, *_ = provider_on_three_delivering_routes
    assert provider.owner_id == organization.pk

    organization.delete()

    assert not Integration.objects.filter(pk=provider.pk).exists()


def test_default_route_fk_uses_the_custom_on_delete():
    from integrations.models.v2.default_route import reassign_default_route
    field = Integration._meta.get_field("default_route")
    assert field.remote_field.on_delete is reassign_default_route
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `$PY -m pytest integrations/tests/test_default_route_invariant.py -q -k "survives_deleting or only_route_nulls or several_others_refuses or spanning_routes or non_default_route_keeps or organization_cascades or custom_on_delete"`
Expected: `test_default_route_fk_uses_the_custom_on_delete` FAILS (ImportError); `test_reassignment_survives_deleting_the_default_route` — read its result carefully: with Task 5 in place `pre_delete(RouteProvider)` already assigns r2, then the collector's `SET_NULL` overwrites it with NULL → `assert provider.default_route == r2` FAILS. That failure is the collector race the spec describes. `test_deleting_default_route_with_several_others_refuses` passes already via the pre_delete receiver.

- [ ] **Step 3: Implement the on_delete callable**

Append to `default_route.py`:

```python
def reassign_default_route(collector, field, sub_objs, using):
    """``on_delete`` for ``Integration.default_route`` (replaces ``SET_NULL``).

    Runs at *collection* time, before anything is deleted. ``sub_objs`` are the
    integrations whose default is one of the routes being deleted. For each,
    decide the new default among the routes that will survive and schedule the
    update through ``collector.add_field_update`` — the same mechanism
    ``SET_NULL``/``SET()`` use, so the collector applies it instead of racing it.
    (A ``pre_delete(Route)`` receiver that saved the integration would be
    overwritten: the collector records the SET_NULL update at collection time
    and applies it after pre_delete has run.)

    Integrations that are themselves being deleted in the same cascade (an
    Organization delete takes its routes and its integrations together) just get
    NULL, exactly as before. The collector may reach this field before it has
    collected the organization's integrations, so ownership is checked too.

    Raises ``AmbiguousDefaultRouteError`` (aborting the whole delete) when a
    surviving default cannot be chosen.
    """
    Route = apps.get_model("integrations", "Route")
    Integration = apps.get_model("integrations", "Integration")
    Organization = apps.get_model("organizations", "Organization")
    doomed_routes = {route.pk for route in collector.data.get(Route, ())}
    doomed_integrations = {integration.pk for integration in collector.data.get(Integration, ())}
    doomed_owners = {organization.pk for organization in collector.data.get(Organization, ())}
    for integration in sub_objs:
        if integration.pk in doomed_integrations or integration.owner_id in doomed_owners:
            collector.add_field_update(field, None, [integration])
            continue
        decision = decide_default_route(integration, exclude_route_ids=doomed_routes)
        collector.add_field_update(field, decision.route, [integration])
```

Logging is deliberately **not** done here: the cascaded `pre_delete(RouteProvider)` receiver (Task 5) fires for the same rows inside the collector's delete, computes the same answer, saves it and logs it with `via="route_deleted"`; the scheduled field update then writes the same value. Logging in both places would produce two rows. Accepted gap: when an Organization is deleted and a provider owned by *another* organization was on one of its routes, the callable reassigns that provider's default but the `pre_delete` receiver skips (origin is an Organization), so that one reassignment goes unlogged.

Export it: in `models/v2/__init__.py` add `reassign_default_route,` to the `from .default_route import (...)` list.

In `models.py`, add near the other imports at the top:

```python
from .default_route import reassign_default_route
```

and change the FK (lines ~296-303):

```python
    default_route = models.ForeignKey(
        "integrations.Route",
        blank=True,
        null=True,
        on_delete=reassign_default_route,
        related_name="integrations_by_rule",
        verbose_name="Default Routing Rule",
    )
```

- [ ] **Step 4: Generate the migration**

Run (from `cdip_admin/`, with the `DB_*` env exported):

```bash
$PY manage.py makemigrations integrations -n integration_default_route_on_delete
cat integrations/migrations/0118_integration_default_route_on_delete.py
```

Expected: one `AlterField` on `integration.default_route` with `on_delete=integrations.models.v2.default_route.reassign_default_route` and `dependencies = [("integrations", "0117_alter_integrationaction_type")]`. If the dependency is a later number, another migration has landed on `main` — that is fine, keep what was generated. Then:

```bash
$PY manage.py makemigrations --check --dry-run
```

Expected: `No changes detected`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `$PY -m pytest integrations/tests/test_default_route_invariant.py -q --create-db`
Expected: 44 passed.

- [ ] **Step 6: Commit**

```bash
git add cdip_admin/integrations/models/v2/default_route.py cdip_admin/integrations/models/v2/models.py cdip_admin/integrations/models/v2/__init__.py cdip_admin/integrations/migrations/0118_integration_default_route_on_delete.py cdip_admin/integrations/tests/test_default_route_invariant.py
git commit -m "Reassign default_route through a custom on_delete when a route is deleted

SET_NULL silently orphaned providers that remained on other routes, and a
pre_delete(Route) receiver cannot fix it: the deletion Collector records
the SET_NULL update at collection time and applies it afterwards. The
on_delete callable schedules the reassignment through the same
add_field_update() mechanism, so the collector applies it. State-only
migration; no schema change.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: Surface refusals in the Routes API as `409 Conflict`

**Files:**
- Modify: `cdip_admin/api/v2/serializers.py` (beside `DuplicateIntegrationError`, ~line 31)
- Modify: `cdip_admin/api/v2/views.py` (`RoutesView`, ~line 386)
- Test: `cdip_admin/api/v2/tests/test_routes_api.py`

**Interfaces:**
- Consumes: `AmbiguousDefaultRouteError` (attrs `candidates`, `str(exc)`).
- Produces: `AmbiguousDefaultRouteConflict(drf_exceptions.APIException)` — `status_code=409`, `default_code="ambiguous_default_route"`, `detail={"detail": str, "candidates": [{"id", "name"}]}`; `RoutesView.handle_exception`, `RoutesView.perform_update` (atomic).

- [ ] **Step 1: Write the failing tests**

Append to `test_routes_api.py`:

```python
# --- refusals surface as 409 --------------------------------------------------

@pytest.fixture
def ambiguous_provider(organization, integration_type_lotek, integrations_list_er):
    """default=R1, also on R2 and R3, all delivering. Deleting R1 or removing
    the provider from it has two candidates → refused."""
    from integrations.models import RouteProvider, RouteDestination
    provider = Integration.objects.create(
        type=integration_type_lotek, owner=organization, name="Ambiguous", base_url="https://api.test.lotek.com",
    )
    routes = []
    for name in ("R1", "R2", "R3"):
        route = Route.objects.create(owner=organization, name=name)
        RouteProvider.objects.bulk_create([RouteProvider(integration=provider, route=route)])
        RouteDestination.objects.bulk_create([RouteDestination(integration=integrations_list_er[0], route=route)])
        routes.append(route)
    Integration.objects.filter(pk=provider.pk).update(default_route=routes[0])
    provider.refresh_from_db()
    return provider, routes


def test_delete_route_with_ambiguous_default_returns_409_with_candidates(api_client, superuser, ambiguous_provider):
    provider, (r1, r2, r3) = ambiguous_provider
    api_client.force_authenticate(superuser)

    response = api_client.delete(reverse("routes-detail", kwargs={"pk": r1.id}))

    assert response.status_code == status.HTTP_409_CONFLICT
    body = response.json()
    assert "Cannot choose a default route" in body["detail"]
    assert {c["id"] for c in body["candidates"]} == {str(r2.id), str(r3.id)}
    assert all(set(c) == {"id", "name"} for c in body["candidates"])
    assert Route.objects.filter(pk=r1.pk).exists()
    provider.refresh_from_db()
    assert provider.default_route == r1


def test_patch_route_removing_provider_with_ambiguous_default_returns_409(api_client, superuser, ambiguous_provider):
    provider, (r1, r2, r3) = ambiguous_provider
    api_client.force_authenticate(superuser)

    response = api_client.patch(
        reverse("routes-detail", kwargs={"pk": r1.id}),
        data={"name": "renamed", "data_providers": []},
        format="json",
    )

    assert response.status_code == status.HTTP_409_CONFLICT
    r1.refresh_from_db()
    assert r1.name == "R1"                       # the whole update rolled back
    assert r1.data_providers.filter(pk=provider.pk).exists()


def test_delete_route_with_one_other_route_reassigns_and_succeeds(api_client, superuser, organization, integration_type_lotek, integrations_list_er):
    from integrations.models import RouteProvider, RouteDestination
    provider = Integration.objects.create(
        type=integration_type_lotek, owner=organization, name="Two routes", base_url="https://api.test.lotek.com",
    )
    r1, r2 = (Route.objects.create(owner=organization, name=n) for n in ("R1", "R2"))
    RouteProvider.objects.bulk_create([RouteProvider(integration=provider, route=r) for r in (r1, r2)])
    RouteDestination.objects.bulk_create([RouteDestination(integration=integrations_list_er[0], route=r) for r in (r1, r2)])
    Integration.objects.filter(pk=provider.pk).update(default_route=r1)
    api_client.force_authenticate(superuser)

    response = api_client.delete(reverse("routes-detail", kwargs={"pk": r1.id}))

    assert response.status_code == status.HTTP_204_NO_CONTENT
    provider.refresh_from_db()
    assert provider.default_route == r2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `$PY -m pytest api/v2/tests/test_routes_api.py -q -k "ambiguous or one_other_route"`
Expected: the two 409 tests FAIL with an unhandled `AmbiguousDefaultRouteError` (500 / exception raised in the test client); the reassign test passes.

- [ ] **Step 3: Implement**

In `serializers.py`, add `AmbiguousDefaultRouteError` to the `from integrations.models import (...)` line, and directly below `DuplicateIntegrationError`:

```python
class AmbiguousDefaultRouteConflict(drf_exceptions.APIException):
    """409 for a route change that would leave a provider without a clear default
    route (spec §5.1). Body: {"detail": ..., "candidates": [{"id", "name"}]}."""
    status_code = status.HTTP_409_CONFLICT
    default_code = "ambiguous_default_route"

    def __init__(self, error: AmbiguousDefaultRouteError):
        super().__init__(detail={
            "detail": str(error),
            "candidates": [{"id": str(route.pk), "name": route.name} for route in error.candidates],
        })
```

In `views.py`, add `AmbiguousDefaultRouteError` to the `from integrations.models import Route, ...` import and add to `RoutesView`:

```python
    def perform_update(self, serializer):
        # Receivers may refuse an m2m change (AmbiguousDefaultRouteError). ATOMIC_REQUESTS
        # is off, so without this the scalar fields would already be committed.
        with transaction.atomic():
            serializer.save()

    def handle_exception(self, exc):
        if isinstance(exc, AmbiguousDefaultRouteError):
            exc = v2_serializers.AmbiguousDefaultRouteConflict(exc)
        return super().handle_exception(exc)
```

(`transaction` is already imported in `views.py`.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `$PY -m pytest api/v2/tests/test_routes_api.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add cdip_admin/api/v2/serializers.py cdip_admin/api/v2/views.py cdip_admin/api/v2/tests/test_routes_api.py
git commit -m "Return 409 with candidate routes when a route change leaves a default ambiguous

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: Surface refusals in Django admin

**Files:**
- Modify: `cdip_admin/integrations/admin.py` (`RouteProviderInline` ~line 440, `RouteAdmin` ~line 454)
- Test: `cdip_admin/integrations/tests/test_admin.py`

**Interfaces:**
- Consumes: `AmbiguousDefaultRouteError`, `decide_default_route(integration, *, leaving_route)`.
- Produces: `RouteProviderInlineFormSet(BaseInlineFormSet)` with `clean()`; `RouteAdmin.delete_model`, `delete_queryset`, `response_delete`.

- [ ] **Step 1: Write the failing tests**

Append to `integrations/tests/test_admin.py` (add `from django.forms.models import inlineformset_factory`, `from integrations.models import Route, RouteProvider, RouteDestination` to imports; `Integration` is already imported):

```python
# --- default route refusals ----------------------------------------------------

@pytest.fixture
def ambiguous_provider(organization, integration_type_lotek, integrations_list_er):
    provider = Integration.objects.create(
        type=integration_type_lotek, owner=organization, name="Ambiguous", base_url="https://api.test.lotek.com",
    )
    routes = []
    for name in ("R1", "R2", "R3"):
        route = Route.objects.create(owner=organization, name=name)
        RouteProvider.objects.bulk_create([RouteProvider(integration=provider, route=route)])
        RouteDestination.objects.bulk_create([RouteDestination(integration=integrations_list_er[0], route=route)])
        routes.append(route)
    Integration.objects.filter(pk=provider.pk).update(default_route=routes[0])
    provider.refresh_from_db()
    return provider, routes


def test_admin_delete_of_ambiguous_default_route_is_refused_with_message(admin_client, ambiguous_provider):
    provider, (r1, r2, r3) = ambiguous_provider
    url = reverse("admin:integrations_route_delete", args=[r1.pk])

    response = admin_client.post(url, {"post": "yes"}, follow=True)

    assert response.status_code == 200
    messages = [str(m) for m in response.context["messages"]]
    assert any("Cannot choose a default route" in m and r2.name in m and r3.name in m for m in messages), messages
    assert not any("deleted successfully" in m for m in messages), messages
    assert Route.objects.filter(pk=r1.pk).exists()
    provider.refresh_from_db()
    assert provider.default_route == r1


def test_admin_bulk_delete_of_ambiguous_default_route_deletes_nothing(admin_client, ambiguous_provider):
    """Bulk-deleting R1 alone leaves R2 and R3 as candidates → refused.
    (Selecting R1 *and* R2 would leave only R3 and legitimately succeed.)"""
    provider, (r1, r2, r3) = ambiguous_provider
    url = reverse("admin:integrations_route_changelist")

    response = admin_client.post(
        url,
        {"action": "delete_selected", "_selected_action": [str(r1.pk)], "post": "yes"},
        follow=True,
    )

    assert response.status_code == 200
    assert Route.objects.filter(pk=r1.pk).exists()
    messages = [str(m) for m in response.context["messages"]]
    assert any("Cannot choose a default route" in m for m in messages), messages


def test_provider_inline_formset_refuses_ambiguous_removal(ambiguous_provider):
    from integrations.admin import RouteProviderInlineFormSet
    provider, (r1, r2, r3) = ambiguous_provider
    link = RouteProvider.objects.get(integration=provider, route=r1)
    FormSet = inlineformset_factory(
        Route, RouteProvider, formset=RouteProviderInlineFormSet, fields=("integration",), extra=0, can_delete=True,
    )
    prefix = FormSet.get_default_prefix()
    data = {
        f"{prefix}-TOTAL_FORMS": "1", f"{prefix}-INITIAL_FORMS": "1",
        f"{prefix}-MIN_NUM_FORMS": "0", f"{prefix}-MAX_NUM_FORMS": "1000",
        f"{prefix}-0-id": str(link.pk), f"{prefix}-0-integration": str(provider.pk), f"{prefix}-0-DELETE": "on",
    }

    formset = FormSet(data, instance=r1)

    assert not formset.is_valid()
    assert any("Cannot choose a default route" in e for e in formset.non_form_errors())
    assert RouteProvider.objects.filter(pk=link.pk).exists()


def test_provider_inline_formset_allows_unambiguous_removal(organization, integration_type_lotek, integrations_list_er):
    from integrations.admin import RouteProviderInlineFormSet
    provider = Integration.objects.create(
        type=integration_type_lotek, owner=organization, name="Two routes", base_url="https://api.test.lotek.com",
    )
    r1, r2 = (Route.objects.create(owner=organization, name=n) for n in ("R1", "R2"))
    RouteProvider.objects.bulk_create([RouteProvider(integration=provider, route=r) for r in (r1, r2)])
    RouteDestination.objects.bulk_create([RouteDestination(integration=integrations_list_er[0], route=r) for r in (r1, r2)])
    Integration.objects.filter(pk=provider.pk).update(default_route=r1)
    link = RouteProvider.objects.get(integration=provider, route=r1)
    FormSet = inlineformset_factory(
        Route, RouteProvider, formset=RouteProviderInlineFormSet, fields=("integration",), extra=0, can_delete=True,
    )
    prefix = FormSet.get_default_prefix()
    data = {
        f"{prefix}-TOTAL_FORMS": "1", f"{prefix}-INITIAL_FORMS": "1",
        f"{prefix}-MIN_NUM_FORMS": "0", f"{prefix}-MAX_NUM_FORMS": "1000",
        f"{prefix}-0-id": str(link.pk), f"{prefix}-0-integration": str(provider.pk), f"{prefix}-0-DELETE": "on",
    }

    formset = FormSet(data, instance=r1)

    assert formset.is_valid(), formset.errors
    formset.save()
    provider.refresh_from_db()
    assert provider.default_route == r2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `$PY -m pytest integrations/tests/test_admin.py -q -k "ambiguous or inline_formset"`
Expected: FAIL — `ImportError: cannot import name 'RouteProviderInlineFormSet'` for the formset tests; the delete tests fail with an unhandled `AmbiguousDefaultRouteError` (the admin view raises).

- [ ] **Step 3: Implement**

In `admin.py`, add imports:

```python
from django.core.exceptions import ValidationError
from django.db import transaction
from django.forms.models import BaseInlineFormSet
from django.http import HttpResponseRedirect
```

add `AmbiguousDefaultRouteError, decide_default_route` to the `from .models import (...)` block, and replace `RouteProviderInline` / `RouteAdmin` with:

```python
class RouteProviderInlineFormSet(BaseInlineFormSet):
    """Refuse (as a form error, before anything is saved) removing a provider
    from a route when that would leave its default route ambiguous (spec §5.1).
    Raising from the pre_delete receiver instead would poison the admin's
    surrounding transaction."""

    def clean(self):
        super().clean()
        route = self.instance
        if route.pk is None:
            return
        for form in self.deleted_forms:
            link = form.instance
            if link.pk is None:
                continue
            try:
                decide_default_route(link.integration, leaving_route=route)
            except AmbiguousDefaultRouteError as error:
                raise ValidationError(str(error))


class RouteProviderInline(admin.TabularInline):
    model = Route.data_providers.through
    formset = RouteProviderInlineFormSet
    # Without this, every inline row renders a <select> of *every* Integration,
    # and Integration.__str__ touches owner.name/type.name (not select_related),
    # making the Route change page an N+1 storm that times out in production.
    autocomplete_fields = ("integration",)


class RouteDestinationInline(admin.TabularInline):
    model = Route.destinations.through
    autocomplete_fields = ("integration",)


@admin.register(Route)
class RouteAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
    )
    list_filter = (
        "owner",
    )
    # Render owner/configuration as AJAX search boxes instead of dropdowns that
    # eagerly load every Organization/RouteConfiguration on the change page.
    autocomplete_fields = (
        "owner",
        "configuration",
    )
    inlines = (
        RouteProviderInline,
        RouteDestinationInline,
    )

    # -- default route refusals (spec §5.1) ---------------------------------
    # Deleting a route that is a provider's default is refused by the FK's
    # on_delete when the provider is on several other routes. Turn that into an
    # admin message instead of a 500. The savepoint keeps the admin's outer
    # transaction usable after the aborted delete.

    def delete_model(self, request, obj):
        try:
            with transaction.atomic():
                super().delete_model(request, obj)
        except AmbiguousDefaultRouteError as error:
            messages.error(request, str(error))

    def delete_queryset(self, request, queryset):
        try:
            with transaction.atomic():
                super().delete_queryset(request, queryset)
        except AmbiguousDefaultRouteError as error:
            messages.error(request, str(error))

    def response_delete(self, request, obj_display, obj_id):
        if Route.objects.filter(pk=obj_id).exists():  # refused above: no success message, back to the route
            return HttpResponseRedirect(reverse("admin:integrations_route_change", args=[obj_id]))
        return super().response_delete(request, obj_display, obj_id)
```

Known limits, both accepted: (1) Django's `delete_selected` action adds its own "Successfully deleted N routes" message after `delete_queryset` returns, so a refused bulk delete shows both the error and a (wrong) success line — nothing is deleted and the error names why; the single-object path is clean. (2) `ModelAdmin.delete_view` writes its admin `LogEntry` *before* calling `delete_model`, so a refused single delete still leaves a "deleted" entry in the admin history. `ActivityLog` is unaffected.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `$PY -m pytest integrations/tests/test_admin.py -q`
Expected: all pass.

- [ ] **Step 5: Regression run, commit, open PR 2**

Run: `$PY -m pytest integrations api/v2 -q --ignore=integrations/tests/test_metrics.py 2>&1 | tail -20`

```bash
git add cdip_admin/integrations/admin.py cdip_admin/integrations/tests/test_admin.py
git commit -m "Show default-route refusals as admin messages and inline form errors

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
git push -u origin feature/default-route-invariant-delete
gh pr create --base feature/default-route-invariant-enforce --title "Keep default_route valid when a provider leaves a route or a route is deleted" --body-file - <<'EOF'
## What

PR 2 of 4 for the default route invariant (spec: `docs/superpowers/specs/2026-09-18-default-route-invariant-design.md` §5.1 entry points 2–3, plan: `docs/superpowers/plans/2026-09-18-default-route-invariant.md`). Stacked on #<PR1>; retarget to `main` once it merges.

- **Provider leaves a route** — `pre_remove`/`pre_clear` on `Route.data_providers` and `pre_delete(RouteProvider)`: one remaining route → reassign and log; several → `AmbiguousDefaultRouteError` aborts the operation. Cascades starting at the Integration are left alone.
- **Route deleted** — `Integration.default_route.on_delete` is now `reassign_default_route`, a custom callable that schedules the new default through `Collector.add_field_update()` (the mechanism `SET_NULL` itself uses). A `pre_delete(Route)` receiver cannot do this: the collector records the SET_NULL update at collection time and applies it afterwards — the test `test_reassignment_survives_deleting_the_default_route` fails without the callable. State-only migration `0118`.
- **Refusals surfaced** — `DELETE`/`PATCH /v2/routes/{id}` → `409 {"detail", "candidates": [{id, name}]}`; admin delete → `messages.error` naming the candidates, nothing deleted; removing a provider in the Route inline → form error before anything is saved.

## Known limit

Django's `delete_selected` action appends its own success message after `delete_queryset` returns, so a refused bulk delete shows both lines. Nothing is deleted.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
```

---

# PR 3 — Detect: shared queryset, status pipeline, `check_default_routes`

Branch: `feature/default-route-invariant-detect` cut from `feature/default-route-invariant-delete`.

```bash
git checkout -b feature/default-route-invariant-detect
```

### Task 9: One queryset that defines "violation"

**Files:**
- Modify: `cdip_admin/integrations/models/v2/services.py`
- Test: `cdip_admin/integrations/tests/test_default_route_detection.py` (new)

**Interfaces:**
- Produces (all in `services.py`, re-exported by `from .services import *` in `models/v2/__init__.py`):
  - `class DefaultRouteState(str, Enum)`: `VALID="valid"`, `MISSING="missing"`, `NOT_MEMBER="not_member"`, `EMPTY_DEFAULT="empty_default"`.
  - `DEFAULT_ROUTE_STATUS_DETAILS: dict[DefaultRouteState, str]` (the three UNHEALTHY messages).
  - `annotate_default_route_state(queryset) -> QuerySet` adding boolean annotations `default_route_missing`, `default_route_not_member`, `default_route_empty`.
  - `filter_by_default_route_state(queryset, state: DefaultRouteState) -> QuerySet` — providers only.
  - `providers_without_valid_default_route() -> QuerySet[Integration]` — annotated; violators only.
  - `get_default_route_state(integration) -> DefaultRouteState | None` — `None` means "not a provider, exempt".

- [ ] **Step 1: Write the failing tests**

Create `cdip_admin/integrations/tests/test_default_route_detection.py`:

```python
"""Detection layer (spec §5.2): one queryset defines what a broken default route is."""
import uuid

import pytest

from integrations.models import (
    Integration,
    Route,
    RouteDestination,
    RouteProvider,
    DefaultRouteState,
    annotate_default_route_state,
    filter_by_default_route_state,
    get_default_route_state,
    providers_without_valid_default_route,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def make_provider(organization, integration_type_lotek):
    def _make(name="Provider"):
        return Integration.objects.create(
            type=integration_type_lotek, owner=organization,
            name=f"{name} {uuid.uuid4().hex[:6]}", base_url="https://api.test.lotek.com",
        )
    return _make


@pytest.fixture
def make_route(organization):
    def _make(name="Route", providers=(), destinations=()):
        route = Route.objects.create(owner=organization, name=f"{name} {uuid.uuid4().hex[:6]}")
        RouteProvider.objects.bulk_create([RouteProvider(integration=p, route=route) for p in providers])
        RouteDestination.objects.bulk_create([RouteDestination(integration=d, route=route) for d in destinations])
        return route
    return _make


def set_default(integration, route):
    Integration.objects.filter(pk=integration.pk).update(default_route=route)
    integration.refresh_from_db()


@pytest.fixture
def zoo(make_provider, make_route, destination_movebank):
    """One provider per state, plus an exempt destination-only integration."""
    valid = make_provider("valid")
    set_default(valid, make_route("valid", providers=[valid], destinations=[destination_movebank]))

    valid_empty_alone = make_provider("valid-empty-alone")           # empty default, no other route delivers
    set_default(valid_empty_alone, make_route("empty", providers=[valid_empty_alone]))
    make_route("also-empty", providers=[valid_empty_alone])

    missing = make_provider("missing")
    make_route("m", providers=[missing])

    not_member = make_provider("not-member")
    make_route("nm", providers=[not_member], destinations=[destination_movebank])
    set_default(not_member, make_route("orphan"))

    empty_default = make_provider("empty-default")
    set_default(empty_default, make_route("placeholder", providers=[empty_default]))
    make_route("real", providers=[empty_default], destinations=[destination_movebank])

    return {
        "valid": valid, "valid_empty_alone": valid_empty_alone, "missing": missing,
        "not_member": not_member, "empty_default": empty_default, "exempt": destination_movebank,
    }


def test_get_default_route_state_classifies_each_shape(zoo):
    assert get_default_route_state(zoo["valid"]) == DefaultRouteState.VALID
    assert get_default_route_state(zoo["valid_empty_alone"]) == DefaultRouteState.VALID
    assert get_default_route_state(zoo["missing"]) == DefaultRouteState.MISSING
    assert get_default_route_state(zoo["not_member"]) == DefaultRouteState.NOT_MEMBER
    assert get_default_route_state(zoo["empty_default"]) == DefaultRouteState.EMPTY_DEFAULT


def test_destination_only_integration_is_exempt(zoo):
    assert get_default_route_state(zoo["exempt"]) is None
    assert zoo["exempt"].pk not in providers_without_valid_default_route().values_list("pk", flat=True)


def test_providers_without_valid_default_route_returns_exactly_the_violators(zoo):
    violators = set(providers_without_valid_default_route().values_list("pk", flat=True))

    assert violators == {zoo["missing"].pk, zoo["not_member"].pk, zoo["empty_default"].pk}


def test_annotations_are_mutually_exclusive_per_row(zoo):
    rows = annotate_default_route_state(Integration.providers.all()).values(
        "pk", "default_route_missing", "default_route_not_member", "default_route_empty",
    )
    for row in rows:
        flags = [row["default_route_missing"], row["default_route_not_member"], row["default_route_empty"]]
        assert sum(bool(f) for f in flags) <= 1, row


@pytest.mark.parametrize("state, key", [
    (DefaultRouteState.MISSING, "missing"),
    (DefaultRouteState.NOT_MEMBER, "not_member"),
    (DefaultRouteState.EMPTY_DEFAULT, "empty_default"),
])
def test_filter_by_state_returns_one_provider_each(zoo, state, key):
    assert set(filter_by_default_route_state(Integration.objects.all(), state).values_list("pk", flat=True)) == {zoo[key].pk}


def test_filter_by_valid_returns_the_valid_providers_only(zoo):
    valid = set(filter_by_default_route_state(Integration.objects.all(), DefaultRouteState.VALID).values_list("pk", flat=True))

    assert {zoo["valid"].pk, zoo["valid_empty_alone"].pk} <= valid
    assert not ({zoo["missing"].pk, zoo["not_member"].pk, zoo["empty_default"].pk, zoo["exempt"].pk} & valid)


def test_violation_queryset_is_a_single_statement(zoo, django_assert_num_queries):
    with django_assert_num_queries(1):
        list(providers_without_valid_default_route())
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `$PY -m pytest integrations/tests/test_default_route_detection.py -q`
Expected: FAIL at import (`DefaultRouteState`).

- [ ] **Step 3: Implement**

In `services.py`, change the Django import to `from django.db.models import Subquery, Q, Exists, OuterRef, ExpressionWrapper, BooleanField` and add after `ConnectionStatus`:

```python
class DefaultRouteState(str, Enum):
    """Where an integration stands against the default-route invariant (spec §4).
    Only meaningful for providers; destination-only integrations are exempt."""
    VALID = "valid"
    MISSING = "missing"              # §4 clause 1: default_route is NULL
    NOT_MEMBER = "not_member"        # §4 clause 2: not a provider on its default route
    EMPTY_DEFAULT = "empty_default"  # §4 clause 3: default has no destinations while another route does


DEFAULT_ROUTE_STATUS_DETAILS = {
    DefaultRouteState.MISSING: (
        "No default route — data from this provider cannot be routed. "
        "Assign one in Admin → Integration, or run check_default_routes --fix."
    ),
    DefaultRouteState.NOT_MEMBER: (
        "Default route is not one of this provider's routes — data from this provider cannot be routed. "
        "Assign one in Admin → Integration, or run check_default_routes --fix."
    ),
    DefaultRouteState.EMPTY_DEFAULT: (
        "Default route has no destinations while another route does — data from this provider is not delivered. "
        "Assign one in Admin → Integration, or run check_default_routes --fix."
    ),
}

_DEFAULT_ROUTE_STATE_ANNOTATION = {
    DefaultRouteState.MISSING: "default_route_missing",
    DefaultRouteState.NOT_MEMBER: "default_route_not_member",
    DefaultRouteState.EMPTY_DEFAULT: "default_route_empty",
}


def annotate_default_route_state(queryset):
    """Annotate an Integration queryset with three booleans, one per §4 clause.

    Each is an Exists() subquery, so the whole thing stays one SQL statement.
    Used by the status pipeline, the admin filter and check_default_routes so
    the three cannot disagree about what "broken" means.
    """
    RouteProvider = apps.get_model("integrations", "RouteProvider")
    RouteDestination = apps.get_model("integrations", "RouteDestination")
    is_member_of_default = Exists(
        RouteProvider.objects.filter(integration_id=OuterRef("pk"), route_id=OuterRef("default_route_id"))
    )
    default_has_destinations = Exists(
        RouteDestination.objects.filter(route_id=OuterRef("default_route_id"))
    )
    some_route_has_destinations = Exists(
        RouteDestination.objects.filter(route__routeprovider__integration_id=OuterRef("pk"))
    )
    has_default = Q(default_route__isnull=False)
    return queryset.annotate(
        default_route_missing=ExpressionWrapper(Q(default_route__isnull=True), output_field=BooleanField()),
        default_route_not_member=ExpressionWrapper(has_default & ~is_member_of_default, output_field=BooleanField()),
        default_route_empty=ExpressionWrapper(
            has_default & is_member_of_default & ~default_has_destinations & some_route_has_destinations,
            output_field=BooleanField(),
        ),
    )


def _providers_only(queryset):
    return queryset.filter(routing_rules_by_provider__isnull=False).distinct()


def filter_by_default_route_state(queryset, state):
    """Restrict an Integration queryset to providers in the given state."""
    annotated = annotate_default_route_state(_providers_only(queryset))
    if state == DefaultRouteState.VALID:
        return annotated.filter(default_route_missing=False, default_route_not_member=False, default_route_empty=False)
    return annotated.filter(**{_DEFAULT_ROUTE_STATE_ANNOTATION[DefaultRouteState(state)]: True})


def providers_without_valid_default_route():
    """Providers violating §4 (any clause). One statement, no Python loop."""
    Integration = apps.get_model("integrations", "Integration")
    return annotate_default_route_state(Integration.providers.all()).filter(
        Q(default_route_missing=True) | Q(default_route_not_member=True) | Q(default_route_empty=True)
    )


def get_default_route_state(integration):
    """State of one integration, or None when it is a provider on no route (exempt)."""
    Integration = apps.get_model("integrations", "Integration")
    row = annotate_default_route_state(Integration.providers.filter(pk=integration.pk)).values(
        "default_route_missing", "default_route_not_member", "default_route_empty",
    ).first()
    if row is None:
        return None
    if row["default_route_missing"]:
        return DefaultRouteState.MISSING
    if row["default_route_not_member"]:
        return DefaultRouteState.NOT_MEMBER
    if row["default_route_empty"]:
        return DefaultRouteState.EMPTY_DEFAULT
    return DefaultRouteState.VALID
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `$PY -m pytest integrations/tests/test_default_route_detection.py -q`
Expected: 9 passed. If `test_violation_queryset_is_a_single_statement` fails with 2 queries, the `.distinct()` from `Integration.providers` combined with annotations has produced a subquery wrapper — acceptable only if it is still one statement; inspect `str(providers_without_valid_default_route().query)`.

- [ ] **Step 5: Commit**

```bash
git add cdip_admin/integrations/models/v2/services.py cdip_admin/integrations/tests/test_default_route_detection.py
git commit -m "Define default-route violations once, as an annotated queryset

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 10: Status pipeline branch

**Files:**
- Modify: `cdip_admin/integrations/models/v2/services.py` (`calculate_integration_status`)
- Test: `cdip_admin/integrations/tests/test_calc_integration_status.py`

**Interfaces:**
- Consumes: `get_default_route_state`, `DEFAULT_ROUTE_STATUS_DETAILS`, `DefaultRouteState`.

- [ ] **Step 1: Write the failing tests**

Append to `test_calc_integration_status.py` (add `Route, RouteProvider, RouteDestination` to the `from integrations.models import` line and `from ..models.v2 import DEFAULT_ROUTE_STATUS_DETAILS, DefaultRouteState`):

```python
# --- default route invariant (spec §5.2) ----------------------------------------

def _null_default_without_signals(integration):
    Integration.objects.filter(pk=integration.pk).update(default_route=None)


def test_provider_without_default_route_is_unhealthy_naming_the_cause(provider_lotek_panthera):
    _null_default_without_signals(provider_lotek_panthera)

    calculate_integration_status(integration_id=provider_lotek_panthera.id)

    provider_lotek_panthera.status.refresh_from_db()
    assert provider_lotek_panthera.status.status == IntegrationStatus.Status.UNHEALTHY
    assert provider_lotek_panthera.status.status_details == DEFAULT_ROUTE_STATUS_DETAILS[DefaultRouteState.MISSING]


def test_provider_whose_default_is_not_one_of_its_routes_is_unhealthy(provider_lotek_panthera, organization):
    orphan = Route.objects.create(owner=organization, name="Orphan")
    Integration.objects.filter(pk=provider_lotek_panthera.pk).update(default_route=orphan)

    calculate_integration_status(integration_id=provider_lotek_panthera.id)

    provider_lotek_panthera.status.refresh_from_db()
    assert provider_lotek_panthera.status.status == IntegrationStatus.Status.UNHEALTHY
    assert provider_lotek_panthera.status.status_details == DEFAULT_ROUTE_STATUS_DETAILS[DefaultRouteState.NOT_MEMBER]


def test_provider_with_empty_default_beside_delivering_route_is_unhealthy(
    provider_lotek_panthera, destination_movebank, organization
):
    real = Route.objects.create(owner=organization, name="Real")
    RouteProvider.objects.bulk_create([RouteProvider(integration=provider_lotek_panthera, route=real)])
    RouteDestination.objects.bulk_create([RouteDestination(integration=destination_movebank, route=real)])
    # the fixture's default is an empty placeholder; leave it as the default

    calculate_integration_status(integration_id=provider_lotek_panthera.id)

    provider_lotek_panthera.status.refresh_from_db()
    assert provider_lotek_panthera.status.status == IntegrationStatus.Status.UNHEALTHY
    assert provider_lotek_panthera.status.status_details == DEFAULT_ROUTE_STATUS_DETAILS[DefaultRouteState.EMPTY_DEFAULT]


def test_destination_only_integration_is_not_flagged(destination_movebank):
    assert destination_movebank.default_route is None

    calculate_integration_status(integration_id=destination_movebank.id)

    destination_movebank.status.refresh_from_db()
    assert destination_movebank.status.status == IntegrationStatus.Status.HEALTHY


def test_default_route_branch_precedes_error_threshold(
    provider_lotek_panthera,
    pull_observations_action_started_activity_log,
    pull_observations_action_failed_activity_log,
    pull_observations_action_failed_activity_log_2,
    pull_observations_action_failed_activity_log_3,
):
    """A missing default is the cause of downstream errors; the detail must name the cause."""
    _null_default_without_signals(provider_lotek_panthera)

    calculate_integration_status(integration_id=provider_lotek_panthera.id)

    provider_lotek_panthera.status.refresh_from_db()
    assert provider_lotek_panthera.status.status == IntegrationStatus.Status.UNHEALTHY
    assert provider_lotek_panthera.status.status_details == DEFAULT_ROUTE_STATUS_DETAILS[DefaultRouteState.MISSING]


def test_disabled_wins_over_default_route(provider_lotek_panthera):
    _null_default_without_signals(provider_lotek_panthera)
    Integration.objects.filter(pk=provider_lotek_panthera.pk).update(enabled=False)

    calculate_integration_status(integration_id=provider_lotek_panthera.id)

    provider_lotek_panthera.status.refresh_from_db()
    assert provider_lotek_panthera.status.status == IntegrationStatus.Status.DISABLED
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `$PY -m pytest integrations/tests/test_calc_integration_status.py -q -k "default_route or destination_only or disabled_wins"`
Expected: 4 FAIL (status HEALTHY, or UNHEALTHY with the wrong detail for the threshold test); `test_destination_only_integration_is_not_flagged` and `test_disabled_wins_over_default_route` pass.

- [ ] **Step 3: Implement**

In `calculate_integration_status`, directly after the `if not integration.enabled:` block's `return`, insert:

```python
    # A broken default route is the *cause* of downstream errors, so it is
    # checked before the dispatcher / error-threshold branches and names itself
    # (spec §5.2). Destination-only integrations return None here and are exempt.
    default_route_state = get_default_route_state(integration)
    if default_route_state is not None and default_route_state != DefaultRouteState.VALID:
        integration_status.status = IntegrationStatus.Status.UNHEALTHY
        integration_status.status_details = DEFAULT_ROUTE_STATUS_DETAILS[default_route_state]
        integration_status.save()
        return integration_status.status
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `$PY -m pytest integrations/tests/test_calc_integration_status.py integrations/tests/test_email_alerts.py integrations/tests/test_tasks.py -q`
Expected: all pass (`filter_connections_by_status` / the email task need no change: provider `UNHEALTHY` already flips the connection).

- [ ] **Step 5: Commit**

```bash
git add cdip_admin/integrations/models/v2/services.py cdip_admin/integrations/tests/test_calc_integration_status.py
git commit -m "Mark providers with a broken default route UNHEALTHY, naming the cause

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 11: `check_default_routes` management command

**Files:**
- Create: `cdip_admin/integrations/management/commands/check_default_routes.py`
- Test: `cdip_admin/integrations/tests/test_commands.py`

**Interfaces:**
- Consumes: `providers_without_valid_default_route`, `get_default_route_state`, `resolve_default_route(integration, via="check_default_routes")`, `AmbiguousDefaultRouteError`.
- Produces: `python manage.py check_default_routes [--fix] [--integration <uuid>] [--json]`. Exit code 1 (via `CommandError`) when violators remain.

- [ ] **Step 1: Write the failing tests**

Append to `integrations/tests/test_commands.py` (add `import uuid`, `from activity_log.models import ActivityLog`, and `Integration, Route, RouteProvider, RouteDestination` to the `integrations.models` import):

```python
# --- check_default_routes -------------------------------------------------------

@pytest.fixture
def broken_providers(organization, integration_type_lotek, destination_movebank):
    def provider(name):
        return Integration.objects.create(
            type=integration_type_lotek, owner=organization, name=name, base_url="https://api.test.lotek.com",
        )

    def route(name, providers=(), destinations=()):
        r = Route.objects.create(owner=organization, name=name)
        RouteProvider.objects.bulk_create([RouteProvider(integration=p, route=r) for p in providers])
        RouteDestination.objects.bulk_create([RouteDestination(integration=d, route=r) for d in destinations])
        return r

    fixable = provider("Fixable")                      # NULL default, one route → repairable
    fixable_route = route("Fixable route", providers=[fixable], destinations=[destination_movebank])

    ambiguous = provider("Ambiguous")                  # NULL default, two delivering routes → needs a human
    route("Amb A", providers=[ambiguous], destinations=[destination_movebank])
    route("Amb B", providers=[ambiguous], destinations=[destination_movebank])

    fine = provider("Fine")
    fine_route = route("Fine route", providers=[fine], destinations=[destination_movebank])
    Integration.objects.filter(pk=fine.pk).update(default_route=fine_route)

    return {"fixable": fixable, "fixable_route": fixable_route, "ambiguous": ambiguous, "fine": fine}


def _run(*args):
    out, err = StringIO(), StringIO()
    call_command("check_default_routes", *args, stdout=out, stderr=err)
    return out.getvalue(), err.getvalue()


def test_check_default_routes_dry_run_lists_violators_and_exits_nonzero(broken_providers):
    out = StringIO()
    with pytest.raises(CommandError, match="2 provider"):
        call_command("check_default_routes", stdout=out)

    text = out.getvalue()
    assert str(broken_providers["fixable"].id) in text and "missing" in text
    assert str(broken_providers["ambiguous"].id) in text
    assert str(broken_providers["fine"].id) not in text
    broken_providers["fixable"].refresh_from_db()
    assert broken_providers["fixable"].default_route is None          # dry run wrote nothing


def test_check_default_routes_exits_zero_when_clean(broken_providers):
    out, _ = _run("--integration", str(broken_providers["fine"].id))
    assert "No default route violations" in out


def test_check_default_routes_fix_repairs_unambiguous_and_lists_ambiguous(broken_providers):
    out = StringIO()
    with pytest.raises(CommandError, match="1 provider"):
        call_command("check_default_routes", "--fix", stdout=out)

    fixable = broken_providers["fixable"]
    fixable.refresh_from_db()
    assert fixable.default_route == broken_providers["fixable_route"]
    log = ActivityLog.objects.get(integration=fixable, value="default_route_auto_assigned")
    assert log.details["via"] == "check_default_routes"
    broken_providers["ambiguous"].refresh_from_db()
    assert broken_providers["ambiguous"].default_route is None
    text = out.getvalue()
    assert "fixed" in text and "ambiguous" in text and "Amb A" in text and "Amb B" in text


def test_check_default_routes_fix_exits_zero_when_everything_was_repaired(broken_providers):
    out, _ = _run("--fix", "--integration", str(broken_providers["fixable"].id))
    assert "fixed" in out


def test_check_default_routes_integration_scope(broken_providers):
    out = StringIO()
    with pytest.raises(CommandError, match="1 provider"):
        call_command("check_default_routes", "--integration", str(broken_providers["ambiguous"].id), stdout=out)
    assert str(broken_providers["fixable"].id) not in out.getvalue()


def test_check_default_routes_json_output(broken_providers):
    out = StringIO()
    with pytest.raises(CommandError):
        call_command("check_default_routes", "--json", stdout=out)

    report = json.loads(out.getvalue())
    by_id = {entry["id"]: entry for entry in report}
    fixable = by_id[str(broken_providers["fixable"].id)]
    assert fixable["violation"] == "missing"
    assert fixable["default_route"] is None
    assert fixable["candidates"] == [
        {"id": str(broken_providers["fixable_route"].id), "name": "Fixable route", "destination_count": 1}
    ]
    assert set(fixable) >= {"id", "name", "type", "owner", "default_route", "violation", "candidates"}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `$PY -m pytest integrations/tests/test_commands.py -q -k check_default_routes`
Expected: FAIL — `CommandError: Unknown command: 'check_default_routes'`.

- [ ] **Step 3: Implement**

Create `cdip_admin/integrations/management/commands/check_default_routes.py`:

```python
"""Audit — and with --fix, repair — providers whose default route violates the invariant.

Spec: docs/superpowers/specs/2026-09-18-default-route-invariant-design.md §5.2.
Dry by default. Exit code 1 while any violator remains, so it works as a
post-deploy gate. Run it, READ the output, then run --fix.
"""
import json

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count

from integrations.models import (
    AmbiguousDefaultRouteError,
    Route,
    get_default_route_state,
    providers_without_valid_default_route,
    resolve_default_route,
)


class Command(BaseCommand):
    help = (
        "List providers whose default_route is missing, not one of their routes, or empty while "
        "another route delivers. --fix repairs the unambiguous ones (logged to ActivityLog) and "
        "lists the rest. Exit code 1 while violators remain."
    )

    def add_arguments(self, parser):
        parser.add_argument("--fix", action="store_true", help="Repair unambiguous violators.")
        parser.add_argument("--integration", type=str, help="Only this integration (UUID).")
        parser.add_argument("--json", action="store_true", dest="as_json", help="Machine-readable output.")

    def handle(self, *args, **options):
        queryset = providers_without_valid_default_route().select_related("type", "owner", "default_route")
        if options["integration"]:
            queryset = queryset.filter(pk=options["integration"])
        queryset = queryset.order_by("owner__name", "name")

        report = []
        for integration in queryset:
            entry = self._describe(integration)
            if options["fix"]:
                entry["repair"] = self._repair(integration)
            report.append(entry)

        remaining = [entry for entry in report if entry.get("repair", {}).get("result") != "fixed"]

        if options["as_json"]:
            self.stdout.write(json.dumps(report, indent=2))
        elif not report:
            self.stdout.write(self.style.SUCCESS("No default route violations found."))
        else:
            for entry in report:
                self.stdout.write(self._format(entry))
            fixed = len(report) - len(remaining)
            self.stdout.write(f"\n{len(report)} violator(s) found" + (f", {fixed} fixed" if options["fix"] else ""))

        if remaining:
            raise CommandError(
                f"{len(remaining)} provider(s) without a valid default route"
                + ("" if options["fix"] else " (dry run; pass --fix to repair the unambiguous ones)")
            )

    @staticmethod
    def _describe(integration):
        state = get_default_route_state(integration)
        candidates = (
            Route.objects.filter(data_providers=integration.pk)
            .annotate(destination_count=Count("destinations"))
            .order_by("name")
        )
        return {
            "id": str(integration.pk),
            "name": integration.name,
            "type": integration.type.value,
            "owner": integration.owner.name,
            "default_route": (
                {"id": str(integration.default_route_id), "name": integration.default_route.name}
                if integration.default_route_id else None
            ),
            "violation": state.value if state else None,
            "candidates": [
                {"id": str(route.pk), "name": route.name, "destination_count": route.destination_count}
                for route in candidates
            ],
        }

    @staticmethod
    def _repair(integration):
        # Each repair in its own transaction so one ambiguous case cannot roll back the others.
        try:
            with transaction.atomic():
                route = resolve_default_route(integration, via="check_default_routes")
        except AmbiguousDefaultRouteError as error:
            return {
                "result": "ambiguous",
                "candidates": [{"id": str(r.pk), "name": r.name} for r in error.candidates],
            }
        return {
            "result": "fixed",
            "default_route": {"id": str(route.pk), "name": route.name} if route else None,
        }

    @staticmethod
    def _format(entry):
        default = entry["default_route"]
        lines = [
            f"{entry['id']}  {entry['name']}  [{entry['type']}]  owner={entry['owner']}",
            f"    violation: {entry['violation']}   default_route: "
            + (f"{default['name']} ({default['id']})" if default else "NULL"),
        ]
        for candidate in entry["candidates"]:
            lines.append(
                f"    candidate: {candidate['name']} ({candidate['id']})  destinations={candidate['destination_count']}"
            )
        repair = entry.get("repair")
        if repair:
            if repair["result"] == "fixed":
                lines.append(f"    -> fixed: default_route = {repair['default_route']['name']}")
            else:
                names = ", ".join(c["name"] for c in repair["candidates"])
                lines.append(f"    -> ambiguous, left alone. Choose one of: {names}")
        return "\n".join(lines)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `$PY -m pytest integrations/tests/test_commands.py -q`
Expected: all pass.

- [ ] **Step 5: Commit, regression run, open PR 3**

```bash
git add cdip_admin/integrations/management/commands/check_default_routes.py cdip_admin/integrations/tests/test_commands.py
git commit -m "Add check_default_routes to audit and repair broken default routes

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
$PY -m pytest integrations api/v2 -q --ignore=integrations/tests/test_metrics.py 2>&1 | tail -20
git push -u origin feature/default-route-invariant-detect
gh pr create --base feature/default-route-invariant-delete --title "Detect broken default routes: status pipeline and check_default_routes" --body-file - <<'EOF'
## What

PR 3 of 4 for the default route invariant (spec §5.2, plan: `docs/superpowers/plans/2026-09-18-default-route-invariant.md`). Stacked on #<PR2>.

- `providers_without_valid_default_route()` — one annotated queryset (three `Exists()` clauses) defines "violation" for the status pipeline, the admin filter (PR 4) and the command, so they cannot disagree.
- `calculate_integration_status()` — a provider violating any clause becomes `UNHEALTHY` with a detail naming the cause, checked right after `DISABLED` and before the dispatcher/error-threshold branches. The existing connection-status email fires unchanged. Catches `QuerySet.update()`/`bulk_create()` bypasses within one beat cycle.
- `python manage.py check_default_routes [--fix] [--integration <uuid>] [--json]` — dry by default, exit 1 while violators remain; `--fix` repairs unambiguous ones (each in its own transaction, logged) and lists ambiguous ones with their candidates.

## Rollout (after merge)

Run `check_default_routes` on dev → stage → prod and **read the output** before `--fix`. Ambiguous rows need a human to pick the default in Admin → Integration.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
```

---

# PR 4 — See: Django admin

Branch: `feature/default-route-invariant-admin` cut from `feature/default-route-invariant-detect`.

```bash
git checkout -b feature/default-route-invariant-admin
```

### Task 12: `IntegrationAdmin` — default route column, filter, autocomplete, panels

**Files:**
- Modify: `cdip_admin/integrations/admin.py` (`IntegrationAdmin` ~line 292; `RouteAdmin.search_fields`)
- Test: `cdip_admin/integrations/tests/test_admin.py`

**Interfaces:**
- Consumes: `DefaultRouteState`, `filter_by_default_route_state`.
- Produces: `DefaultRouteStateFilter(admin.SimpleListFilter)` (`parameter_name="default_route_state"`), `IntegrationAdmin.default_route_link`, `.routes_as_provider_panel`, `.routes_as_destination_panel`; `RouteAdmin.search_fields = ("id", "name")`.

- [ ] **Step 1: Write the failing tests**

Append to `test_admin.py`:

```python
# --- default route visibility: IntegrationAdmin ---------------------------------

@pytest.fixture
def mock_api_key_column(mocker, mock_get_api_key):
    """IntegrationAdmin.list_display renders ``api_key``, which calls Kong per row."""
    mocker.patch("integrations.models.v2.models.Integration.api_key", mock_get_api_key)


@pytest.fixture
def visibility_zoo(organization, integration_type_lotek, integrations_list_er):
    def provider(name):
        return Integration.objects.create(
            type=integration_type_lotek, owner=organization, name=name, base_url="https://api.test.lotek.com",
        )

    def route(name, providers=(), destinations=()):
        r = Route.objects.create(owner=organization, name=name)
        RouteProvider.objects.bulk_create([RouteProvider(integration=p, route=r) for p in providers])
        RouteDestination.objects.bulk_create([RouteDestination(integration=d, route=r) for d in destinations])
        return r

    er = integrations_list_er[0]
    valid = provider("Valid provider")
    valid_route = route("Valid route", providers=[valid], destinations=[er])
    Integration.objects.filter(pk=valid.pk).update(default_route=valid_route)

    missing = provider("Missing provider")
    route("Missing route", providers=[missing], destinations=[er])

    not_member = provider("Not-member provider")
    route("NM route", providers=[not_member], destinations=[er])
    Integration.objects.filter(pk=not_member.pk).update(default_route=route("Orphan route"))

    empty = provider("Empty-default provider")
    Integration.objects.filter(pk=empty.pk).update(default_route=route("Placeholder", providers=[empty]))
    route("Real route", providers=[empty], destinations=[er])

    return {"valid": valid, "valid_route": valid_route, "missing": missing, "not_member": not_member, "empty": empty, "er": er}


@pytest.mark.parametrize("state, key", [
    ("missing", "missing"), ("not_member", "not_member"), ("empty_default", "empty"),
])
def test_integration_changelist_default_route_filter_isolates_each_violation(admin_client, mock_api_key_column, visibility_zoo, state, key):
    url = reverse("admin:integrations_integration_changelist") + f"?default_route_state={state}"

    response = admin_client.get(url)

    assert response.status_code == 200
    assert {obj.pk for obj in response.context["cl"].queryset} == {visibility_zoo[key].pk}


def test_integration_changelist_default_route_filter_valid_excludes_violators(admin_client, mock_api_key_column, visibility_zoo):
    url = reverse("admin:integrations_integration_changelist") + "?default_route_state=valid"

    response = admin_client.get(url)

    pks = {obj.pk for obj in response.context["cl"].queryset}
    assert visibility_zoo["valid"].pk in pks
    assert not ({visibility_zoo["missing"].pk, visibility_zoo["not_member"].pk, visibility_zoo["empty"].pk} & pks)


def test_integration_changelist_shows_default_route_as_link(admin_client, mock_api_key_column, visibility_zoo):
    url = reverse("admin:integrations_integration_changelist") + f"?q={visibility_zoo['valid'].name}"

    content = admin_client.get(url).content.decode()

    assert reverse("admin:integrations_route_change", args=[visibility_zoo["valid_route"].pk]) in content
    assert "Valid route" in content


def test_integration_changelist_query_count_does_not_scale_with_rows(admin_client, mock_api_key_column, visibility_zoo, organization, integration_type_lotek):
    url = reverse("admin:integrations_integration_changelist")
    baseline = _render_query_count(admin_client, url)

    route = Route.objects.create(owner=organization, name="Shared default")
    Integration.objects.bulk_create([
        Integration(type=integration_type_lotek, owner=organization, name=f"Bulk {i}",
                    base_url="https://api.test.lotek.com", default_route=route)
        for i in range(60)
    ])

    after = _render_query_count(admin_client, url)
    assert after - baseline <= 2, f"{baseline} -> {after} queries after adding 60 integrations"


def test_integration_change_page_shows_route_panels(admin_client, visibility_zoo):
    url = reverse("admin:integrations_integration_change", args=[visibility_zoo["empty"].pk])

    content = admin_client.get(url).content.decode()

    assert "Routes as provider" in content
    assert "★" in content                                   # the default is marked
    assert "Placeholder" in content and "Real route" in content
    assert visibility_zoo["er"].name in content             # destinations listed under the real route


def test_integration_change_page_destination_panel_lists_providers(admin_client, visibility_zoo):
    url = reverse("admin:integrations_integration_change", args=[visibility_zoo["er"].pk])

    content = admin_client.get(url).content.decode()

    assert "Routes as destination" in content
    assert "Valid provider" in content


def test_integration_change_page_default_route_uses_autocomplete(admin_client, visibility_zoo):
    url = reverse("admin:integrations_integration_change", args=[visibility_zoo["valid"].pk])
    response = admin_client.get(url)
    form = response.context["adminform"].form

    widget = form.fields["default_route"].widget
    if isinstance(widget, RelatedFieldWidgetWrapper):
        widget = widget.widget
    assert isinstance(widget, AutocompleteSelect)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `$PY -m pytest integrations/tests/test_admin.py -q -k "integration_changelist or integration_change_page"`
Expected: filter tests FAIL (the `default_route_state` parameter is ignored → all integrations returned; Django may return 400 "Incorrect lookup parameters" — either is a failure); link/panel/autocomplete tests FAIL.

- [ ] **Step 3: Implement**

In `admin.py` change `from django.db.models import F` to `from django.db.models import F, Prefetch` and `from django.utils.html import format_html` to `from django.utils.html import format_html, format_html_join`; add `DefaultRouteState, filter_by_default_route_state` to the `from .models import (...)` block. Add before `IntegrationAdmin`:

```python
class DefaultRouteStateFilter(admin.SimpleListFilter):
    """One click to the providers violating the default-route invariant (spec §5.3).
    Choices map one-to-one onto the clauses of providers_without_valid_default_route()."""
    title = "Default route"
    parameter_name = "default_route_state"

    def lookups(self, request, model_admin):
        return (
            (DefaultRouteState.VALID.value, "Valid"),
            (DefaultRouteState.MISSING.value, "Missing (NULL)"),
            (DefaultRouteState.NOT_MEMBER.value, "Not one of its routes"),
            (DefaultRouteState.EMPTY_DEFAULT.value, "Empty while another route delivers"),
        )

    def queryset(self, request, queryset):
        try:
            state = DefaultRouteState(self.value())
        except ValueError:
            return queryset
        return filter_by_default_route_state(queryset, state)
```

Replace `IntegrationAdmin`'s attribute block (keep `delete_model` / `delete_queryset` as they are):

```python
@admin.register(Integration)
class IntegrationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "type",
        "owner",
        "name",
        "enabled",
        "default_route_link",
        "api_key",  # ToDo: Add an endpoint to manage API Keys to manage them through the Portal UI?
        "created_at",
    )
    list_select_related = ("default_route", "type", "owner")
    list_filter = (
        "owner",
        "type",
        DefaultRouteStateFilter,
        "created_at",
    )
    search_fields = (
        "id",
        "name",
        "owner__name",
        "type__name",
        "type__value",
    )
    # AJAX search box instead of a <select> of every Route (needs RouteAdmin.search_fields).
    autocomplete_fields = ("default_route",)
    readonly_fields = ("routes_as_provider_panel", "routes_as_destination_panel")
    inlines = [
        DispatcherDeploymentInline,
    ]

    @admin.display(description="Default route", ordering="default_route__name")
    def default_route_link(self, obj):
        if obj.default_route_id is None:
            return "—"
        url = reverse("admin:integrations_route_change", args=[obj.default_route_id])
        return format_html('<a href="{}">{}</a>', url, obj.default_route.name)

    @staticmethod
    def _integration_labels(integrations):
        return ", ".join(f"{i.name} ({i.type.name})" for i in integrations) or "none"

    @admin.display(description="Routes as provider")
    def routes_as_provider_panel(self, obj):
        """provider → route → destinations, default marked ★ (spec §5.3)."""
        if obj.pk is None:
            return "—"
        routes = obj.routing_rules_by_provider.prefetch_related(
            Prefetch("destinations", queryset=Integration.objects.select_related("type"))
        ).order_by("name")
        rows = [
            (
                "★ " if route.pk == obj.default_route_id else "",
                reverse("admin:integrations_route_change", args=[route.pk]),
                route.name,
                self._integration_labels(route.destinations.all()),
            )
            for route in routes
        ]
        if not rows:
            return "Not a provider on any route (default route not required)."
        return format_html("<ul>{}</ul>", format_html_join("", '<li>{}<a href="{}">{}</a> → {}</li>', rows))

    @admin.display(description="Routes as destination")
    def routes_as_destination_panel(self, obj):
        if obj.pk is None:
            return "—"
        routes = obj.routing_rules_by_destination.prefetch_related(
            Prefetch("data_providers", queryset=Integration.objects.select_related("type"))
        ).order_by("name")
        rows = [
            (
                self._integration_labels(route.data_providers.all()),
                reverse("admin:integrations_route_change", args=[route.pk]),
                route.name,
            )
            for route in routes
        ]
        if not rows:
            return "Not a destination on any route."
        return format_html("<ul>{}</ul>", format_html_join("", '<li>{} → <a href="{}">{}</a></li>', rows))
```

And on `RouteAdmin` add (required for the autocomplete):

```python
    search_fields = (
        "id",
        "name",
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `$PY -m pytest integrations/tests/test_admin.py -q`
Expected: all pass. If the query-count test fails, the culprit is almost always `Integration.__str__`/`api_key` in `list_display` touching relations not in `list_select_related`; the assertion is a *delta*, so only per-row growth fails it.

- [ ] **Step 5: Commit**

```bash
git add cdip_admin/integrations/admin.py cdip_admin/integrations/tests/test_admin.py
git commit -m "Show and filter default routes in the Integration admin

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 13: `RouteAdmin` — owner, providers, destinations, "Default for"

**Files:**
- Modify: `cdip_admin/integrations/admin.py` (`RouteAdmin`)
- Test: `cdip_admin/integrations/tests/test_admin.py`

**Interfaces:**
- Produces: `RouteAdmin.providers_display`, `.destinations_display`, `.default_for_display`, `.default_route_for_panel`, `.get_queryset` prefetching.

- [ ] **Step 1: Write the failing tests**

Append to `test_admin.py`:

```python
# --- default route visibility: RouteAdmin ---------------------------------------

def test_route_changelist_shows_owner_providers_destinations_and_default_for(admin_client, visibility_zoo):
    url = reverse("admin:integrations_route_changelist") + "?q=Valid+route"

    content = admin_client.get(url).content.decode()

    assert visibility_zoo["valid"].owner.name in content
    assert "Valid provider" in content
    assert visibility_zoo["er"].name in content
    assert "Default for" in content


def test_route_changelist_query_count_does_not_scale_with_rows(admin_client, visibility_zoo, organization, integration_type_lotek):
    url = reverse("admin:integrations_route_changelist")
    baseline = _render_query_count(admin_client, url)

    routes = Route.objects.bulk_create([Route(owner=organization, name=f"Bulk route {i}") for i in range(40)])
    RouteProvider.objects.bulk_create([RouteProvider(integration=visibility_zoo["valid"], route=r) for r in routes])
    RouteDestination.objects.bulk_create([RouteDestination(integration=visibility_zoo["er"], route=r) for r in routes])

    after = _render_query_count(admin_client, url)
    assert after - baseline <= 2, f"{baseline} -> {after} queries after adding 40 routes"


def test_route_change_page_shows_default_route_for_panel(admin_client, visibility_zoo):
    url = reverse("admin:integrations_route_change", args=[visibility_zoo["valid_route"].pk])

    content = admin_client.get(url).content.decode()

    assert "Default route for" in content
    assert "Valid provider" in content
    assert reverse("admin:integrations_integration_change", args=[visibility_zoo["valid"].pk]) in content
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `$PY -m pytest integrations/tests/test_admin.py -q -k "route_changelist or default_route_for_panel"`
Expected: FAIL (columns/panel absent).

- [ ] **Step 3: Implement**

Update `RouteAdmin`'s attributes and add methods (keep the refusal methods from Task 8 and `search_fields` from Task 12):

```python
    list_display = (
        "id",
        "name",
        "owner",
        "providers_display",
        "destinations_display",
        "default_for_display",
    )
    list_select_related = ("owner",)
    readonly_fields = ("default_route_for_panel",)

    def get_queryset(self, request):
        # The three new columns walk M2M/reverse FK relations; prefetch so the
        # changelist stays at a flat query count.
        return super().get_queryset(request).prefetch_related(
            Prefetch("data_providers", queryset=Integration.objects.only("id", "name")),
            Prefetch("destinations", queryset=Integration.objects.only("id", "name")),
            Prefetch("integrations_by_rule", queryset=Integration.objects.only("id", "name", "default_route")),
        )

    @admin.display(description="Providers")
    def providers_display(self, obj):
        return ", ".join(i.name for i in obj.data_providers.all()) or "—"

    @admin.display(description="Destinations")
    def destinations_display(self, obj):
        return ", ".join(i.name for i in obj.destinations.all()) or "—"

    @admin.display(description="Default for")
    def default_for_display(self, obj):
        return ", ".join(i.name for i in obj.integrations_by_rule.all()) or "—"

    @admin.display(description="Default route for")
    def default_route_for_panel(self, obj):
        """Integrations whose default this route is — the fact that matters before deleting it."""
        if obj.pk is None:
            return "—"
        rows = [
            (reverse("admin:integrations_integration_change", args=[i.pk]), i.name)
            for i in obj.integrations_by_rule.select_related("type").order_by("name")
        ]
        if not rows:
            return "No integration uses this route as its default."
        return format_html("<ul>{}</ul>", format_html_join("", '<li><a href="{}">{}</a></li>', rows))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `$PY -m pytest integrations/tests/test_admin.py -q`
Expected: all pass, including the two pre-existing Route change-page tests.

- [ ] **Step 5: Commit, regression run, open PR 4**

```bash
git add cdip_admin/integrations/admin.py cdip_admin/integrations/tests/test_admin.py
git commit -m "Show providers, destinations and default-for on the Route admin

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
$PY -m pytest integrations api/v2 -q --ignore=integrations/tests/test_metrics.py 2>&1 | tail -20
git push -u origin feature/default-route-invariant-admin
gh pr create --base feature/default-route-invariant-detect --title "Make default routes legible in Django admin" --body-file - <<'EOF'
## What

PR 4 of 4 for the default route invariant (spec §5.3, plan: `docs/superpowers/plans/2026-09-18-default-route-invariant.md`). Stacked on #<PR3>.

**Integration admin** — `default_route` column linked to the route; "Default route" filter (valid · missing · not one of its routes · empty while another delivers) backed by the same queryset the status pipeline uses; `default_route` as an autocomplete instead of a `<select>` of every Route; read-only "Routes as provider" (default ★, destinations listed) and "Routes as destination" panels on the change page.

**Route admin** — owner, providers, destinations and "Default for" columns (prefetched, query count flat); a "Default route for" panel on the change page — what to read before deleting a route; `search_fields` so the autocomplete works.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
```

---

## Rollout after PR 3 merges (operator checklist)

1. Deploy to dev. Run `python manage.py check_default_routes` in a portal pod; read every row. `--json > dev-default-routes.json` to keep a record.
2. Run `check_default_routes --fix`. Confirm one `default_route_auto_assigned` ActivityLog per fixed row and that the remaining rows are ambiguous ones. Pick their defaults in Admin → Integration → Default Routing Rule (autocomplete after PR 4).
3. Repeat for stage, then prod. In prod, expect the rows hand-repaired around PRs #469/#470/#472 to be absent already.
4. Exit code 1 from the command can be wired into a post-deploy check later; not part of this plan.

## Self-review against the spec

- §4 clauses 1–3 → `annotate_default_route_state` (Task 9) and `decide_default_route`'s validity test (Task 1). Exemption for non-providers → `Integration.providers` / `_providers_only` / `None` from `get_default_route_state`.
- §4.1 table rows → Tasks 2 (rows 1–2, 8), 5 (rows 6–7), 6 (rows 3–5); tests exist per row.
- §5.1 helper + logging shape → Task 1. Entry point 1 → Task 2. Entry point 2 → Task 5. Entry point 3 (custom `on_delete`, collector race, state-only migration) → Task 6. Entry point 4 → Task 3. Refusal surfacing admin/API → Tasks 7–8. Transactions → `perform_update` atomic (Task 7), savepoints in admin (Task 8), per-row `atomic()` in `--fix` (Task 11).
- §5.2 shared queryset, per-clause exposure, status branch placement and wording, command flags/exit code → Tasks 9–11.
- §5.3 every bullet → Tasks 12–13.
- §6 test list → each named module has the listed tests; the collector-subtlety test is `test_reassignment_survives_deleting_the_default_route`.
- §7 four PRs in order, no data migration → the four PR sections and the rollout checklist.
- Names are consistent across tasks: `decide_default_route`, `resolve_default_route`, `reassign_default_route`, `AmbiguousDefaultRouteError`, `AmbiguousDefaultRouteConflict`, `DefaultRouteState`, `providers_without_valid_default_route`, `filter_by_default_route_state`, `get_default_route_state`, `DEFAULT_ROUTE_STATUS_DETAILS`, `DEFAULT_ROUTE_AUTO_ASSIGNED`, `RouteProviderInlineFormSet`, `DefaultRouteStateFilter`.

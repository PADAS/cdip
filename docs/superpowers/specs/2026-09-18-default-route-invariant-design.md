# Default route invariant: enforce, detect, see

**Date:** 2026-09-18
**Status:** Approved design. Implementation plan: `docs/superpowers/plans/2026-09-18-default-route-invariant.md`
**Ticket:** [GUNDI-5731](https://allenai.atlassian.net/browse/GUNDI-5731) — *Default routing rule stays empty after creating a route from a new connection* (blocks GUNDI-5730)
**Related PRs:** #469, #470, #472 (the management-command instance of this bug, all merged)

## 1. Summary

`Integration.default_route` is the only route the routing service consults for a
provider. It is a nullable FK that nothing enforces, so every code path that
changes the provider↔route relationship has to remember to maintain it — and only
one does (`ensure_default_route()`, called by the v2 integration-create API).
Everything else leaves it NULL or stale, and data from that provider silently
stops flowing.

This spec makes the invariant real at three layers:

1. **Enforce** — signal handlers and a custom `on_delete` keep `default_route`
   correct whenever a provider joins or leaves a route or a route is deleted.
   Unambiguous cases self-heal (and are logged); ambiguous ones are refused with
   a message naming the candidates.
2. **Detect** — a single shared queryset defines "violation"; the existing status
   pipeline turns violators `UNHEALTHY` (so the existing email fires), and a
   `check_default_routes` command audits and repairs on demand.
3. **See** — Django admin shows each integration's default route, filters
   violators in one click, and lays out the provider→route→destination graph on
   the change page.

Delivered as four independent PRs; the first closes GUNDI-5731.

## 2. Background

### 2.1 What `default_route` is for

`cdip-routing/app/services/event_handlers.py:183-191` resolves a provider's
destinations through `connection.default_route.id` **only**, and reads field
mappings from that route's `configuration`. There is a `TODO` to consider all
routes; today, a provider whose default route is NULL cannot route anything, and
field mappings attached to any other route are never applied.

### 2.2 How it goes wrong — the bypass surface

The one code path that maintains the field is
`integrations/models/v2/services.py:20` `ensure_default_route()`, called from
`api/v2/serializers.py:719` on integration create when `create_default_route`
(default `true`) is set. Everything else bypasses it:

| # | Path | What happens |
|---|---|---|
| 1 | `POST /v2/routes/` (`RouteCreateUpdateSerializer`, `api/v2/serializers.py:1230-1234`) | Delegates to DRF `ModelSerializer`, which writes `data_providers` via `field.set(value)` (`rest_framework/serializers.py:1014,1040`) and never touches `default_route`. **This is GUNDI-5731**, both entry points: the Connections flow and `handleEnableReverseFlow` (`gundi-portal/src/components/routes/ManageRouteDetails.tsx:1743`). The frontend already documents it: `gundi-portal/src/api/routes/routesApi.tsx:76` — *"Note this does not touch integration.default_route."* |
| 2 | Django admin | `IntegrationAdmin` (`integrations/admin.py:292`) neither displays nor filters on `default_route`. `RouteAdmin` (`:454`) has a `RouteProviderInline`; adding a provider there sets no default. Admin "Add Integration" bypasses the serializer entirely. |
| 3 | `on_delete=SET_NULL` (`integrations/models/v2/models.py:296-303`) | Deleting a route that is a provider's default silently NULLs the field, even when the provider remains on other routes. Neither `RouteAdmin` nor the stock `RoutesView.destroy` guards this. |
| 4 | Direct ORM use — scripts, shells, `convert_bridge_integration` before #472 | `Integration.objects.create()` + hand-built routes. |

### 2.3 A second failure shape the ticket exposed

A connection created **with** an empty default route, followed by *Create Route +
destination* through path 1, yields a **second** route carrying the real
destinations while `default_route` still points at the empty one. The field is
set, and it *is* one of the provider's routes — yet nothing is delivered. Any
definition of "correct" that stops at "set and a member" misses this.

### 2.4 Existing plumbing this design reuses

- `calculate_integration_status()` (`services.py:87`) runs per integration on a
  Celery beat (`cdip_admin/settings.py:352` →
  `calculate_integration_statuses_in_batches`, `integrations/tasks.py:354`).
- `filter_connections_by_status()` derives connection-level status from provider
  and destination statuses; `send_unhealthy_connections_email()`
  (`tasks.py:363`) mails on `UNHEALTHY` and `NEEDS_REVIEW`.
- `integrations/signals.py` exists, is wired in `integrations/apps.py:7-8`, and
  already has `pre_delete(IntegrationConfiguration)` and
  `post_delete(RouteProvider)` receivers.
- `ActivityLog` with `Origin.PORTAL`, integer `LogLevels`, and the
  `value`/`title`/`details` shape used by `integrations/tasks.py:60`.
- DRF error precedent: `DuplicateIntegrationError(APIException)`
  (`serializers.py:31`) and the custom handler
  `api.v2.exception_handler.logging_exception_handler`.

## 3. Goals and non-goals

**Goals**

- A provider can never be left in a state where the routing service has no
  usable default route, by any code path, without a human being told.
- Existing violations are found and repaired with an auditable tool.
- The state is legible in admin without a mental three-table join.
- GUNDI-5731 closes, with tests that reproduce its two scenarios end to end.

**Non-goals**

- Frontend changes. The backend is the right layer; every UI path is covered.
- The routing service's own hardening against a NULL default route (in flight in
  `cdip-routing`; complementary).
- A portal page for the connection graph (option C in the brainstorm; the admin
  version is its specification if it is ever wanted).
- Multi-route destination resolution in the routing service (the `TODO` there).

## 4. The invariant

For every integration **I** that is a provider on at least one route:

1. `I.default_route` is not NULL;
2. `I.default_route` is a route on which **I** is a provider;
3. if `I.default_route` has **no destinations** and some other route on which **I**
   is a provider **does**, that is a violation. (The extension from §2.3.)

Integrations that are a provider on no route — destination-only integrations
such as EarthRanger sites — are exempt. This matches the API convention that
destination-only integrations are created with `create_default_route=false`
(`api/v2/tests/test_integrations_api.py:289`) and the `Integration.providers`
manager, which defines a "connection" as *has a route as provider*.

### 4.1 Policy: self-heal where unambiguous, refuse where not

| Event | Candidates for the new default | Action |
|---|---|---|
| Provider joins a route while `default_route` is NULL | that route | assign, log |
| Provider joins a route while its default is a bare placeholder (no destinations, no configuration) | that route | assign, log |
| Default route deleted; provider on no other route | none | NULL is correct (it is no longer a provider) |
| Default route deleted; provider on exactly one other route | that one | assign, log |
| Default route deleted; provider on several other routes | several | **refuse** the delete, naming them |
| Provider removed from its default route; stays on exactly one other | that one | assign, log |
| Provider removed from its default route; stays on several | several | **refuse** the removal, naming them |
| `default_route` set to a route the integration is not a provider on | — | add it as a provider (what `ensure_default_route()` does today) |

Nothing is ever routed somewhere nobody chose. Every self-heal is an
`ActivityLog` entry, so a burst of them is itself a signal that someone is
editing routes through a path that does not know about defaults.

`PROTECT` is deliberately **not** used for the FK: it would also block the
legitimate case — deleting a provider's only route — where NULL is exactly
right.

## 5. Design

### 5.1 Enforcement — `integrations/signals.py`

**Helper.** `resolve_default_route(integration, *, leaving_route=None,
joining_route=None, via="")`:

1. Compute `routes` = routes on which the integration is a provider, excluding
   `leaving_route`, including `joining_route`.
2. If `routes` is empty → set `default_route = None` if it is not already; done.
3. If `default_route` is in `routes` **and** is not a bare placeholder while
   another member of `routes` has destinations → done (already valid).
4. Otherwise candidates = `routes` (if the current default is a placeholder and
   `joining_route` is given, candidates = `[joining_route]`).
5. One candidate → assign, `save(update_fields=["default_route"])`, log.
   Several → raise `AmbiguousDefaultRouteError(integration, candidates)`.

Logging is an `ActivityLog` row: `origin=PORTAL`, `log_level=WARNING`,
`log_type=EVENT`, `value="default_route_auto_assigned"`,
`title=f"Default route set to '{route.name}'"`, `details={"route_id", "via",
"previous_default_route_id"}`, `is_reversible=False`. `via` names the entry
point (`"route_provider_added"`, `"route_deleted"`, …).

The helper is idempotent; entry points may fire more than once for one logical
operation and converge.

**Entry point 1 — a provider joins a route.** Two receivers, because Django
splits this: `post_save(RouteProvider)` catches `RouteProvider.objects.create()`
(and therefore `ensure_default_route()`); `m2m_changed(action="post_add")` on
`Route.data_providers.through` catches `.add()` / `.set()`, which bulk-insert and
do **not** fire `post_save`. The `m2m_changed` receiver handles both directions
(`reverse=False`: instance is the Route, `pk_set` are integration ids;
`reverse=True`: the inverse). Both skip when `raw=True`. This one entry point
closes bypass paths 1, 2 and 4, and is the fix for GUNDI-5731.

**Entry point 2 — a provider leaves a route.** `pre_delete(RouteProvider)` and
`m2m_changed(action in {"pre_remove", "pre_clear"})`. `pre_*` so the
relationship still exists and "other routes" is computable; a raised
`AmbiguousDefaultRouteError` aborts the operation inside the caller's
transaction.

**Entry point 3 — a route is deleted.** Not a signal. A `pre_delete(Route)`
receiver that reassigns defaults would be **silently undone**: Django's deletion
`Collector` records the `SET_NULL` field update *by primary key* at collection
time and applies it after `pre_delete` has run. The correct hook is Django's own:
replace `on_delete=SET_NULL` with a custom callable

```python
def reassign_default_route(collector, field, sub_objs, using):
    routes_being_deleted = {r.pk for r in collector.data.get(Route, ())}
    for integration in sub_objs:            # integrations defaulting to a doomed route
        candidates = integration.routing_rules_by_provider.exclude(pk__in=routes_being_deleted)
        ...  # 0 → add_field_update(field, None, [integration])
             # 1 → add_field_update(field, candidate, [integration]); log
             # 2+ → raise AmbiguousDefaultRouteError
```

`collector.add_field_update()` is how `SET()`/`SET_NULL` themselves work, so the
reassignment is applied by the collector rather than raced by it. The
`RouteProvider` rows cascaded by the same delete will also fire entry point 2;
it computes the same answer and converges (or raises the same error). Changing
`on_delete` is a state-only migration — no schema change.

**Entry point 4 — `default_route` set directly.** `post_save(Integration)`: if
`default_route` is set and the integration is not a provider on it, create the
`RouteProvider`. `post_save`, not `pre_save`, because the through-row needs the
integration's PK. Skips when `raw=True`.

**Surfacing a refusal.** `AmbiguousDefaultRouteError` is a plain exception in
`integrations` carrying the integration and candidate routes.

- Admin: `RouteAdmin.delete_model` / `delete_queryset` and the provider inline
  formset catch it and call `messages.error(request, ...)` naming the candidates.
- API: `RoutesView` maps it to a `409 Conflict` `APIException` (subclass beside
  `DuplicateIntegrationError`), body `{"detail": ..., "candidates": [{id, name}]}`.

**Transactions.** Receivers run in the caller's transaction, so a refusal leaves
nothing half-done. `--fix` in §5.2 wraps each integration's repair in its own
`atomic()` so one ambiguous case does not roll back the others.

### 5.2 Detection

**One query, defined once.** In `integrations/models/v2/services.py`:

```python
def providers_without_valid_default_route():
    """Providers violating §4. Used by the status pipeline, the admin filter
    and check_default_routes, so the three cannot disagree about "broken"."""
```

Built from `Integration.providers` (already "has a route as provider") with
`Exists()` subqueries against `RouteProvider` / `RouteDestination`:

- `default_route__isnull=True`, **or**
- `~Exists(RouteProvider(integration=OuterRef("pk"), route=OuterRef("default_route")))`, **or**
- `~Exists(RouteDestination(route=OuterRef("default_route")))` **and**
  `Exists(RouteDestination(route__routeprovider__integration=OuterRef("pk")))`.

Each clause is also exposed separately (for the admin filter's four choices).
Single statement, no Python loop.

**Status pipeline.** New branch in `calculate_integration_status()` placed
immediately after the `DISABLED` check and **before** the dispatcher/error
checks — a missing default route is the *cause* of downstream errors and the
detail should name the cause. Applies only when the integration is a provider.

```
status  = UNHEALTHY
details = "No default route — data from this provider cannot be routed.
           Assign one in Admin → Integration, or run check_default_routes --fix."
```

(The wording adapts for the two other clauses: *"Default route is not one of
this provider's routes"*, *"Default route has no destinations while another route
does"*.) `filter_connections_by_status()` and `send_unhealthy_connections_email()`
need no change: provider `UNHEALTHY` already flips the connection and mails.
Re-evaluated every beat cycle, so a violation by any path — including
`QuerySet.update()` and `bulk_create()`, which bypass signals — is caught within
one cycle.

**`check_default_routes` management command.**

```
python manage.py check_default_routes [--fix] [--integration <uuid>] [--json]
```

Dry by default (same convention as `repair_everywhere_hub_jq_filter`). Prints
each violator: id, name, type, owner, current `default_route`, which clause it
violates, and candidate routes with their destination counts. Exit code 1 if any
violators, so it works as a post-deploy gate. `--fix` runs
`resolve_default_route()` per violator in its own `atomic()`: unambiguous ones
are repaired and logged like any self-heal; ambiguous ones are listed with their
candidates and left alone. `--json` for machine-readable output.

### 5.3 Visibility — Django admin

**`IntegrationAdmin`**

- `default_route` in `list_display`, rendered as a link to the route's change
  page; `list_select_related = ("default_route", "type", "owner")`.
- `SimpleListFilter` titled **"Default route"**, parameter `default_route_state`,
  choices mapping one-to-one onto §5.2 clauses: `valid` · `missing` ·
  `not_member` · `empty_default`. Each choice filters with the shared queryset.
- Read-only change-page panels via `readonly_fields` methods returning
  `format_html`: **Routes as provider** (each route linked, its destinations
  listed, the default marked ★) and **Routes as destination** (each route linked,
  its providers listed). Prefetched.
- `default_route` in `autocomplete_fields` so the change page stops loading every
  Route into a `<select>`; requires `search_fields = ("id", "name")` on
  `RouteAdmin`, which it lacks today.

**`RouteAdmin`**

- `list_display` gains `owner`, provider names, destination names, and
  **"Default for"** (integrations whose default this route is). `list_select_related`
  and `get_queryset()` prefetching so the columns don't multiply queries.
- Read-only **"Default route for"** panel on the change page — the fact that
  matters before deleting.
- `delete_model` / `delete_queryset` catch `AmbiguousDefaultRouteError` →
  `messages.error` naming the candidates (from §5.1).

## 6. Testing

All test-first.

- **`integrations/tests/test_default_route_invariant.py`** (signals): every row
  of the §4.1 table; each self-heal produces exactly one `ActivityLog` with the
  expected `value`/`via`; each refusal raises with the right candidates; the
  placeholder switch; `raw=True` is skipped; **a reassignment survives deleting
  the route** (the test that would have caught the collector subtlety); a
  queryset `.delete()` spanning several routes; `.set()` / `.add()` /
  `.remove()` / `.clear()` each fire.
- **`api/v2/tests/test_routes_api.py`**: two tests reproducing GUNDI-5731 end to
  end — (a) connection with no default, `POST /v2/routes/` with provider and
  destination → default set to that route; (b) reverse flow via `POST /v2/routes/`
  → the reverse provider's default is set. Plus: `DELETE /v2/routes/{id}` on an
  ambiguous default → 409 with candidates.
- **`integrations/tests/test_calc_integration_status.py`**: each clause turns a
  provider `UNHEALTHY` with the expected detail; a destination-only integration is
  untouched; the branch precedes the error-threshold branch.
- **`integrations/tests/test_commands.py`** (or a sibling module): dry run lists
  and exits 1; `--fix` repairs unambiguous, lists ambiguous, exits 1 only if
  ambiguous remain; `--integration` scopes; `--json` parses.
- **`integrations/tests/test_admin.py`**: each filter choice returns the right
  set; new columns render without N+1 (`django_assert_num_queries`); delete of an
  ambiguous default renders the message and deletes nothing.

## 7. Migration and rollout

**Migration.** One state-only migration for the `on_delete` change. No data
migration: existing violations are repaired by an operator running
`check_default_routes` then `--fix` per environment, deliberately — repairs are
logged and ambiguous ones need a human to choose.

**Delivery — four PRs, each independently useful, in this order:**

| PR | Contents | Closes |
|---|---|---|
| 1 | `resolve_default_route()`, `AmbiguousDefaultRouteError`, entry points 1 and 4, the two GUNDI-5731 API tests | GUNDI-5731 |
| 2 | Entry points 2 and 3 (custom `on_delete` + migration), refusal surfacing in admin and API | |
| 3 | Shared queryset, status-pipeline branch, `check_default_routes` | |
| 4 | Admin visibility | |

After PR 3 lands: run `check_default_routes` dev → stage → prod and **read the
output** before `--fix`.

## 8. Risks and accepted limits

- **Bulk ORM operations** (`QuerySet.update()`, `bulk_create()`) bypass signals.
  Accepted: detection catches them within one beat cycle.
- **Double-firing** of `post_save(RouteProvider)` and `m2m_changed` for one
  logical add, and of entry points 2 and 3 for one route delete. Accepted: the
  helper is idempotent and converges.
- **Raising inside a signal** surfaces as an exception to callers that don't
  expect one. Mitigated: admin and the API map it (§5.1); scripts see a clear
  exception type and message.
- **Beat-cycle latency** for detection (currently the interval configured at
  `settings.py:352`). Accepted: enforcement is the primary layer; detection is the
  safety net.
- **Placeholder heuristic** ("no destinations and no configuration") could
  misclassify a deliberately empty route someone intends to fill later. Accepted:
  the switch is logged, and if the user then adds destinations to the placeholder
  the invariant still holds (default is a member); they can re-point the default
  in admin.

## 9. Decisions log

| Decision | Chosen | Alternatives considered |
|---|---|---|
| Invariant scope | Providers only (§4), with the empty-default extension | Every integration has a default; single-route ⇒ default |
| Violation policy | Self-heal unambiguous, refuse ambiguous | Always self-heal (deterministic pick); never self-heal |
| Detection channel | Existing status pipeline + command | ActivityLog error threshold; dedicated alerting |
| Visibility | Django admin + command | CLI only; portal graph page |
| Route deletion hook | Custom `on_delete` callable | `pre_delete(Route)` receiver (undone by collector); `PROTECT` (blocks the legitimate case) |
| Delivery | Four PRs, ticket fix first | Single PR |

## 10. References

- `cdip-routing/app/services/event_handlers.py:183-191` — router consults `default_route` only
- `integrations/models/v2/services.py:20` — `ensure_default_route()`
- `integrations/models/v2/services.py:87` — `calculate_integration_status()`
- `integrations/models/v2/models.py:296-303` — the FK, `on_delete=SET_NULL`
- `integrations/signals.py`, `integrations/apps.py:7-8` — existing receivers and wiring
- `integrations/admin.py:292`, `:454` — `IntegrationAdmin`, `RouteAdmin`
- `api/v2/serializers.py:719`, `:1230-1234`, `:31` — API create path, Routes serializer, error precedent
- `api/v2/tests/test_integrations_api.py:289` — destination-only convention
- `rest_framework/serializers.py:1014,1040` — DRF writes M2M via `.set()`
- `gundi-portal/src/api/routes/routesApi.tsx:76`, `src/components/routes/ManageRouteDetails.tsx:1743`
- Brainstorm conducted 2026-09-18; PRs #469, #470, #472 for the management-command instance

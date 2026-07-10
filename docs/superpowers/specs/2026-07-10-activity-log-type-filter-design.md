# Activity-log filtering by integration type (GUNDI-5409)

**Status:** Design approved · **Ticket:** [GUNDI-5409](https://allenai.atlassian.net/browse/GUNDI-5409) · **Date:** 2026-07-10

## Problem

The `gundi` CLI's `gundi integrations logs --type <slug>` reads the latest
activity logs across all integrations of a type. `GET /v2/logs/`
(`ActivityLogsViewSet`) has **no server-side filter by integration type**, so
the CLI gathers every integration id of the type and filters via
`integration__in=<ids>`. For a type with many integrations (e.g. `spidertracks`)
the id list overruns the gateway request-line limit (HTTP 400 "Request Line is
too large") and/or drops the connection.

A naive server-side join filter (`integration__type__value=<slug>`) is **not
safe to ship**: `ActivityLog.integration_type` is a Python `@property`, not a
column, and the partitioned `activity_log_activitylog` table has **no index on
(type, time)** — only `(-created_at)` and the composite `(integration,
-created_at)` (migration 0005). A join filter risks the planner walking the
`created_at DESC` index newest-first and join-filtering each row, scanning a
large slice of the partitioned table to find N matches (worst for rare types).

## Goal

Add a server-side `integration_type` filter to `/v2/logs/` that is
index-friendly and safe on the partitioned table, so the CLI can (later) drop
its id-gathering and chunking workaround.

## Approach (Option 1: subquery IN-expansion)

Expand the type slug to its integration ids via a **subquery**, producing the
`integration IN (…)` shape that the existing `(integration, -created_at)`
composite index already serves — rather than a join on the type value.

```python
# cdip_admin/integrations/filters.py — ActivityLogFilter
integration_type = django_filters_rest.CharFilter(method="filter_by_integration_type")

def filter_by_integration_type(self, queryset, name, value):
    integrations = Integration.objects.filter(type__value__iexact=value)
    return queryset.filter(integration__in=Subquery(integrations.values("id")))
```

No schema change, no migration.

### Why this shape is low-risk

`ActivityLogsViewSet.get_queryset` **already** uses this exact pattern for every
non-superuser request:

```python
user_integrations = get_user_integrations_qs(user=self.request.user)
return queryset.filter(integration__in=Subquery(user_integrations.values("id")))
```

So `integration IN (subquery)` + `ORDER BY -created_at` + LIMIT against the
composite index is **already the production query plan** for non-admin traffic.
The new filter reuses it.

### Org-scoping composes for free

For a non-superuser the queryset is already scoped to
`integration__in=Subquery(user's integrations)`. Adding the type filter ANDs a
second `integration__in`, so a non-admin filtering by type only ever sees their
own integrations of that type. Correct by construction; no extra permission
logic needed.

## API contract

- **Param:** `?integration_type=<slug>` (e.g. `earth_ranger`).
- **Value:** the type **slug** (`IntegrationType.value`), matched
  **case-insensitively** (`type__value__iexact`). Chosen over UUID so the CLI
  can pass `--type` straight through with zero client-side resolution.
- **Single value only.** No `__in` variant (YAGNI — the CLI needs one type).
- **Unknown / empty slug → empty result set**, no error (the subquery yields no
  ids). Consistent with the other `ActivityLogFilter` filters.
- **Composes** with the existing `from_date`, `to_date`, `log_level`, `origin`,
  `integration`, `value` filters (all ANDed).

## EXPLAIN validation (merge gate)

Per the ticket, the query plan MUST be validated with
`EXPLAIN (ANALYZE, BUFFERS)` on a representative/staging dataset **before merge**.
The implementation plan will ship a runbook with the exact queries. Coverage:

| Case | Type | Context | Why |
|---|---|---|---|
| High volume | `spidertracks` (many integrations, many rows) | **superuser** (no pre-scoping) | worst case for a large multi-integration merge |
| Rare / inactive | a type with few/old rows | **superuser** | the main risk: planner walking `-created_at` to find N matches |

Each query uses the real `ORDER BY created_at DESC LIMIT <page size>`.

**Acceptance criteria:**
- Plan uses the `(integration, -created_at)` composite index (index scan +
  merge/append across partitions), **not** a full-partition sequential scan.
- Bounded, reasonable buffer usage; latency comparable to the equivalent
  `integration__in` request the CLI issues today.

**If the rare-type case degenerates** (wide `-created_at` walk): first try a
materialized id-list (`list(integrations.values_list("id", flat=True))`) in place
of the `Subquery`, re-`EXPLAIN`; if still unacceptable, escalate to **Option 2**
(denormalize `integration_type` onto `ActivityLog` + `(integration_type,
-created_at)` index) as a separate, larger piece of work. Option 2 is documented
here as the escalation, not built now.

## Testing

`cdip_admin/api/v2/tests/test_activity_logs_api.py`:

1. `?integration_type=<slug>` returns only that type's logs.
2. Case-insensitive match (`Earth_Ranger` == `earth_ranger`).
3. Unknown slug → empty result (200, `results: []`), not an error.
4. Composes with `from_date` / `log_level` (intersection).
5. **Org-scoping preserved:** a non-admin filtering by a type they only partially
   own sees only their own integrations' logs of that type.

## Out of scope (follow-ups)

- **CLI simplification** (gundi-client): drop the `--type` id-gathering +
  `integration__in` chunking, call `get_activity_logs(params={"integration_type":
  slug})` instead. Separate PR **after this deploys**. Keep chunking only if a
  version-compatibility fallback proves necessary.
- **Option 2** (denormalize + dedicated index): only if `EXPLAIN` demands it.

## Files touched

- `cdip_admin/integrations/filters.py` — add `integration_type` to
  `ActivityLogFilter`.
- `cdip_admin/api/v2/tests/test_activity_logs_api.py` — new tests.
- Runbook (docs / PR description) — the `EXPLAIN (ANALYZE, BUFFERS)` queries.

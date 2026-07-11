# Activity-log `integration_type` filter — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **SUPERSEDED IN PART (2026-07-11):** staging EXPLAIN validation (see the
> runbook's Results/Decision) flipped the query strategy: the shipped filter
> materializes the integration ids in Python (org-scoped for non-superusers)
> and returns `queryset.none()` for empty id lists, instead of passing a
> `Subquery`. The Subquery "MUST" below is retained as written history only —
> the opaque subquery gives the planner a type-blind estimate and degenerates
> (non-terminating for unknown slugs). Do not re-introduce it.

**Goal:** Add a server-side `integration_type` filter to `GET /v2/logs/` so activity logs can be filtered by integration type slug, using an index-friendly subquery.

**Architecture:** Add one method filter to `ActivityLogFilter` that expands the type slug to its integration ids via a `Subquery` and filters `integration__in=…` — the same shape `ActivityLogsViewSet.get_queryset` already uses for non-superuser scoping, so it rides the existing `(integration, -created_at)` composite index. No schema change, no migration. A separate `EXPLAIN (ANALYZE, BUFFERS)` runbook gates the merge.

**Tech Stack:** Django 3.2, django-filter (`django_filters.rest_framework`), Django REST Framework, pytest + `pytest.mark.django_db`, Postgres (partitioned `activity_log_activitylog`).

## Global Constraints

- **No naive join filter.** The type filter MUST expand to `integration__in=Subquery(...)`, never `integration__type__value=<slug>` directly — the join has no supporting index on the partitioned table.
- **No schema change / no migration** for this plan (Option 1 only). Option 2 (denormalize) is explicitly out of scope.
- **Slug value, case-insensitive:** match on `type__value__iexact`. Param name is `integration_type`. Single value (no `__in`).
- **Unknown/empty slug → empty result set**, never an error.
- **Org-scoping is enforced by the viewset**, not the filter — tests must confirm the filter does not widen a non-admin's visibility.
- **Merge gate:** the `EXPLAIN` runbook (Task 4) must be run on staging with acceptable plans before the PR merges.
- `Subquery` and `Integration` are already imported in `cdip_admin/integrations/filters.py` — do not re-import.

---

### Task 1: Add the `integration_type` filter (core)

**Files:**
- Modify: `cdip_admin/integrations/filters.py` (class `ActivityLogFilter`, ~lines 677–709)
- Test: `cdip_admin/api/v2/tests/test_activity_logs_api.py`

**Interfaces:**
- Consumes: existing `ActivityLogFilter`, `_test_list_activity_logs(api_client, user, expected_logs, params=None)` helper, fixtures `api_client`, `superuser`, `provider_lotek_panthera` (type `lotek`), `provider_movebank_ewt` (type `movebank`).
- Produces: query param `?integration_type=<slug>` on `GET /v2/logs/`; filter method `ActivityLogFilter.filter_by_integration_type(self, queryset, name, value)`.

- [ ] **Step 1: Write the failing test**

Add to `cdip_admin/api/v2/tests/test_activity_logs_api.py`:

```python
def test_filter_logs_by_integration_type_as_superuser(
        api_client, superuser, provider_lotek_panthera, provider_movebank_ewt,
):
    # One log on a lotek-type integration, one on a movebank-type integration.
    ActivityLog.objects.create(
        log_level=ActivityLog.LogLevels.INFO,
        log_type=ActivityLog.LogTypes.EVENT,
        origin=ActivityLog.Origin.INTEGRATION,
        integration=provider_lotek_panthera,
        value="integration_action_started",
        title="lotek log",
        details={},
        is_reversible=False,
    )
    ActivityLog.objects.create(
        log_level=ActivityLog.LogLevels.INFO,
        log_type=ActivityLog.LogTypes.EVENT,
        origin=ActivityLog.Origin.INTEGRATION,
        integration=provider_movebank_ewt,
        value="integration_action_started",
        title="movebank log",
        details={},
        is_reversible=False,
    )
    # Filtering by the lotek slug returns only the lotek log, excluding movebank.
    _test_list_activity_logs(
        api_client=api_client,
        user=superuser,
        params={"integration_type": "lotek"},
        expected_logs=ActivityLog.objects.filter(
            integration__type__value__iexact="lotek"
        )[:20],
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest cdip_admin/api/v2/tests/test_activity_logs_api.py::test_filter_logs_by_integration_type_as_superuser -v`
Expected: FAIL — an unknown query param is ignored by django-filter, so both logs are returned (`assert 2 == 1`).

- [ ] **Step 3: Add the filter field and method**

In `cdip_admin/integrations/filters.py`, class `ActivityLogFilter`, add the declared filter immediately after the `integration__in = CharInFilter(...)` block:

```python
    integration_type = django_filters_rest.CharFilter(method="filter_by_integration_type")
```

Then add the method immediately after `filter_by_log_level`:

```python
    def filter_by_integration_type(self, queryset, name, value):
        # Expand the type slug to its integration ids and filter with
        # integration__in=Subquery(...). This rides the (integration, -created_at)
        # composite index — the same shape the viewset uses for org scoping —
        # instead of a join on integration__type__value, which the partitioned
        # table has no index for. See GUNDI-5409.
        integrations = Integration.objects.filter(type__value__iexact=value)
        return queryset.filter(integration__in=Subquery(integrations.values("id")))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest cdip_admin/api/v2/tests/test_activity_logs_api.py::test_filter_logs_by_integration_type_as_superuser -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cdip_admin/integrations/filters.py cdip_admin/api/v2/tests/test_activity_logs_api.py
git commit -m "feat: add integration_type filter to activity logs (GUNDI-5409)"
```

---

### Task 2: Contract tests — case-insensitivity and unknown slug

**Files:**
- Test: `cdip_admin/api/v2/tests/test_activity_logs_api.py`

**Interfaces:**
- Consumes: the `integration_type` filter from Task 1; fixtures `api_client`, `superuser`, `provider_lotek_panthera`.
- Produces: nothing new (test-only).

- [ ] **Step 1: Write the failing tests**

Add to `cdip_admin/api/v2/tests/test_activity_logs_api.py`:

```python
def test_filter_logs_by_integration_type_is_case_insensitive(
        api_client, superuser, provider_lotek_panthera,
):
    ActivityLog.objects.create(
        log_level=ActivityLog.LogLevels.INFO,
        log_type=ActivityLog.LogTypes.EVENT,
        origin=ActivityLog.Origin.INTEGRATION,
        integration=provider_lotek_panthera,
        value="integration_action_started",
        title="lotek log",
        details={},
        is_reversible=False,
    )
    _test_list_activity_logs(
        api_client=api_client,
        user=superuser,
        params={"integration_type": "LOTEK"},  # uppercase must still match
        expected_logs=ActivityLog.objects.filter(
            integration__type__value__iexact="lotek"
        )[:20],
    )


def test_filter_logs_by_unknown_integration_type_returns_empty(
        api_client, superuser, provider_lotek_panthera,
):
    ActivityLog.objects.create(
        log_level=ActivityLog.LogLevels.INFO,
        log_type=ActivityLog.LogTypes.EVENT,
        origin=ActivityLog.Origin.INTEGRATION,
        integration=provider_lotek_panthera,
        value="integration_action_started",
        title="lotek log",
        details={},
        is_reversible=False,
    )
    _test_list_activity_logs(
        api_client=api_client,
        user=superuser,
        params={"integration_type": "does_not_exist"},
        expected_logs=[],  # no type matches -> empty subquery -> no rows
    )
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `pytest cdip_admin/api/v2/tests/test_activity_logs_api.py -k "case_insensitive or unknown_integration_type" -v`
Expected: PASS (the Task 1 implementation already satisfies both — these lock the contract).

Note: these are contract-locking tests for behavior Task 1 already provides, so they pass immediately. If either fails, the Task 1 implementation is wrong (e.g. used `exact` instead of `iexact`) — fix `filter_by_integration_type`, do not weaken the test.

- [ ] **Step 3: Commit**

```bash
git add cdip_admin/api/v2/tests/test_activity_logs_api.py
git commit -m "test: lock integration_type filter contract (case-insensitive, unknown slug)"
```

---

### Task 3: Composition and org-scoping tests

**Files:**
- Test: `cdip_admin/api/v2/tests/test_activity_logs_api.py`

**Interfaces:**
- Consumes: the `integration_type` filter (Task 1); the existing `log_level` filter (`log_level__gte`); fixtures `api_client`, `superuser`, `org_admin_user` (member of `organization`), `provider_lotek_panthera`, `integrations_list_er` (10 ER integrations; indices 0–4 owned by `organization`, 5–9 by `other_organization`).
- Produces: nothing new (test-only).

- [ ] **Step 1: Write the composition test**

Add to `cdip_admin/api/v2/tests/test_activity_logs_api.py`:

```python
def test_filter_logs_by_integration_type_composes_with_log_level(
        api_client, superuser, provider_lotek_panthera, provider_movebank_ewt,
):
    # lotek: one INFO + one ERROR; movebank: one ERROR (must be excluded by type).
    ActivityLog.objects.create(
        log_level=ActivityLog.LogLevels.INFO,
        log_type=ActivityLog.LogTypes.EVENT,
        origin=ActivityLog.Origin.INTEGRATION,
        integration=provider_lotek_panthera,
        value="integration_action_started", title="lotek info",
        details={}, is_reversible=False,
    )
    ActivityLog.objects.create(
        log_level=ActivityLog.LogLevels.ERROR,
        log_type=ActivityLog.LogTypes.EVENT,
        origin=ActivityLog.Origin.INTEGRATION,
        integration=provider_lotek_panthera,
        value="integration_action_failed", title="lotek error",
        details={}, is_reversible=False,
    )
    ActivityLog.objects.create(
        log_level=ActivityLog.LogLevels.ERROR,
        log_type=ActivityLog.LogTypes.EVENT,
        origin=ActivityLog.Origin.INTEGRATION,
        integration=provider_movebank_ewt,
        value="integration_action_failed", title="movebank error",
        details={}, is_reversible=False,
    )
    # type=lotek AND log_level>=ERROR -> only the lotek error log.
    _test_list_activity_logs(
        api_client=api_client,
        user=superuser,
        params={
            "integration_type": "lotek",
            "log_level": ActivityLog.LogLevels.ERROR.value,
        },
        expected_logs=ActivityLog.objects.filter(
            integration__type__value__iexact="lotek",
            log_level__gte=ActivityLog.LogLevels.ERROR.value,
        )[:20],
    )
```

- [ ] **Step 2: Write the org-scoping test**

Add to `cdip_admin/api/v2/tests/test_activity_logs_api.py`:

Note: `integrations_list_er` creates FIVE earth_ranger integrations owned by the
user's `organization` (indices 0–4) and five owned by `other_organization`
(5–9), and fixture setup emits activity logs for several of them. So the user
legitimately has many earth_ranger logs — do NOT assert an exact count against a
single integration. Assert scoping by presence/absence of specific logs and by
checking every returned log belongs to the user's own integrations.

```python
def test_filter_logs_by_integration_type_preserves_org_scoping(
        api_client, org_admin_user, integrations_list_er,
):
    # integrations_list_er[0..4] belong to `organization` (org_admin_user's org);
    # [5..9] belong to `other_organization`. All are type earth_ranger.
    owned = integrations_list_er[0]
    not_owned = integrations_list_er[5]
    owned_log = ActivityLog.objects.create(
        log_level=ActivityLog.LogLevels.INFO,
        log_type=ActivityLog.LogTypes.EVENT,
        origin=ActivityLog.Origin.INTEGRATION,
        integration=owned,
        value="integration_action_started", title="owned ER log",
        details={}, is_reversible=False,
    )
    not_owned_log = ActivityLog.objects.create(
        log_level=ActivityLog.LogLevels.INFO,
        log_type=ActivityLog.LogTypes.EVENT,
        origin=ActivityLog.Origin.INTEGRATION,
        integration=not_owned,
        value="integration_action_started", title="other org ER log",
        details={}, is_reversible=False,
    )
    api_client.force_authenticate(org_admin_user)
    response = api_client.get(
        reverse("logs-list"), {"integration_type": "earth_ranger"}
    )
    assert response.status_code == status.HTTP_200_OK
    results = response.json()["results"]
    titles = {log["title"] for log in results}
    # The user's own earth_ranger log is visible; the other org's is not.
    assert "owned ER log" in titles
    assert "other org ER log" not in titles
    # Every returned log belongs to one of the user's own integrations —
    # the type filter did not widen visibility beyond org scoping.
    visible_ids = {
        str(i) for i in get_user_integrations_qs(
            user=org_admin_user
        ).values_list("id", flat=True)
    }
    for log in results:
        assert log["integration"]["id"] in visible_ids
    # Sanity: the not-owned log exists but is scoped out.
    assert str(not_owned_log.id) != str(owned_log.id)
```

- [ ] **Step 3: Run both tests to verify they pass**

Run: `pytest cdip_admin/api/v2/tests/test_activity_logs_api.py -k "composes_with_log_level or preserves_org_scoping" -v`
Expected: PASS. The org-scoping test proves the `integration__in` (viewset) and `integration__in` (filter) compose to an intersection; if `"other org ER log"` appears in `titles`, the filter is bypassing scoping — fix the filter, not the test.

- [ ] **Step 4: Run the whole file (no regressions)**

Run: `pytest cdip_admin/api/v2/tests/test_activity_logs_api.py -v`
Expected: PASS (all pre-existing tests plus the four new ones).

- [ ] **Step 5: Commit**

```bash
git add cdip_admin/api/v2/tests/test_activity_logs_api.py
git commit -m "test: integration_type filter composes with log_level and preserves org scoping"
```

---

### Task 4: `EXPLAIN (ANALYZE, BUFFERS)` runbook (merge gate)

**Files:**
- Create: `docs/superpowers/runbooks/2026-07-10-gundi-5409-explain-validation.md`

**Interfaces:**
- Consumes: the `filter_by_integration_type` query shape (Task 1).
- Produces: a runbook to be executed on **staging** and its results pasted into the PR before merge.

- [ ] **Step 1: Write the runbook**

Create `docs/superpowers/runbooks/2026-07-10-gundi-5409-explain-validation.md` with:

````markdown
# GUNDI-5409 — EXPLAIN validation (run on staging before merge)

Validates that `?integration_type=<slug>` on `/v2/logs/` uses the
`(integration, -created_at)` composite index and does not seq-scan the
partitioned `activity_log_activitylog` table.

Run in the staging Django shell (`python manage.py shell`), as the query the
filter builds, in **superuser context** (no org pre-scoping — the worst case):

```python
from activity_log.models import ActivityLog
from integrations.models import Integration
from django.db.models import Subquery

def type_logs(slug, limit=20):
    ints = Integration.objects.filter(type__value__iexact=slug)
    return (
        ActivityLog.objects
        .filter(integration__in=Subquery(ints.values("id")))
        .order_by("-created_at")[:limit]
    )

# (a) High-volume type — many integrations, many rows
print(type_logs("spidertracks").explain(analyze=True, buffers=True))

# (b) Rare / inactive type — few/old rows (replace with a real low-volume slug)
print(type_logs("<rare_type_slug>").explain(analyze=True, buffers=True))
```

## Acceptance criteria

- [ ] Plan shows an **Index Scan / Index-Only Scan** (or per-partition
      Append of index scans) on `activity_lo_integra_258066_idx`
      (the `(integration, -created_at)` composite) — **not** a Seq Scan of a
      partition.
- [ ] No sort step over a large row set for the `-created_at` ordering (the
      index provides order).
- [ ] Buffer counts and total time are bounded and comparable to the
      equivalent `?integration__in=<ids>` request the CLI issues today.

## If the rare-type case degenerates (wide `-created_at` walk / seq scan)

1. Try a materialized id-list instead of the subquery and re-run EXPLAIN:
   ```python
   ids = list(Integration.objects.filter(type__value__iexact=slug).values_list("id", flat=True))
   ActivityLog.objects.filter(integration__in=ids).order_by("-created_at")[:20]
   ```
2. If still unacceptable, escalate to **Option 2** (denormalize `integration_type`
   onto `ActivityLog` + `(integration_type, -created_at)` index) as separate work.

## Results (fill in before merge)

- Date / environment:
- (a) spidertracks plan summary + verdict:
- (b) rare type (slug used) plan summary + verdict:
- Decision: [ship as-is | switch to materialized ids | escalate to Option 2]
````

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/runbooks/2026-07-10-gundi-5409-explain-validation.md
git commit -m "docs: EXPLAIN validation runbook for the activity-log type filter (GUNDI-5409)"
```

---

## Post-implementation (not tasks in this plan)

- **Run Task 4 on staging** and paste results into the PR; only merge with an acceptable plan (or after switching to the materialized-id variant).
- **Follow-up PR (gundi-client):** simplify the CLI `logs --type` path to call `get_activity_logs(params={"integration_type": slug})` and drop `_resolve_type_id` id-gathering + `_INTEGRATION_IN_CHUNK` chunking, once this filter is deployed. Update the `using-the-gundi-cli` skill's "`logs --type` can be slow" gotcha accordingly.

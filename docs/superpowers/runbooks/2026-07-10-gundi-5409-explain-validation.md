# GUNDI-5409 — EXPLAIN validation (run on staging before merge)

Validates that `?integration_type=<slug>` on `/v2/logs/` uses the
`(integration, -created_at)` composite index and does not seq-scan the
partitioned `activity_log_activitylog` table.

Run in the staging Django shell (`python manage.py shell`), as the query the
filter builds, in **superuser context** (no org pre-scoping — the worst case):

```python
from activity_log.models import ActivityLog
from integrations.models import Integration

def type_logs(slug, limit=20):
    # Mirrors the SHIPPED filter: materialized ids (see Decision below).
    ids = list(Integration.objects.filter(type__value__iexact=slug).values_list("id", flat=True))
    return (
        ActivityLog.objects
        .filter(integration__in=ids)
        .order_by("-created_at")[:limit]
    )

# Historical Subquery form — do NOT run with analyze=True (see Results, case c):
# ActivityLog.objects.filter(integration__in=Subquery(ints.values("id")))

# (a) High-volume type — many integrations, many rows
print(type_logs("spidertracks").explain(analyze=True, buffers=True))

# (b) Rare / inactive type — few/old rows (replace with a real low-volume slug)
print(type_logs("<rare_type_slug>").explain(analyze=True, buffers=True))
```

> **Caution:** verify the slug matches existing integrations BEFORE running
> `explain(analyze=True)` — for the Subquery form, a slug with zero matches
> makes the LIMIT unable to terminate the scan and the "explain" runs a
> full-table walk (see Results, case c). Plain `.explain()` is always safe.

## Acceptance criteria

- [x] **No Seq Scan of any partition**, and no unbounded scan: either
      per-partition scans on the `(integration, -created_at)` composite
      index (expected for sparse types with materialized ids), or a
      newest-first `created_at` walk **that terminates quickly because
      matches are dense** (acceptable for high-volume types). The exact
      index name varies per partition; what matters is the shape and that
      it is bounded.
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

## Results

- **Date / environment:** 2026-07-11 (UTC), staging
- **(a) spidertracks (Subquery form):** Merge Append walk over per-partition
  `created_at DESC` indexes + Nested Loop Semi Join against the id subquery
  (composite index NOT used). Walked 1,864 rows for 20 hits; 2,209 buffers;
  42ms exec / 119ms plan (cold catalog). PASS — but only because spidertracks
  matches are dense in recent history.
- **(b) tracpoint (materialized ids, 1 integration):** per-partition Index
  Scans on the `(integration_id, created_at)` composite
  (`Index Cond: integration_id = <id> AND created_at <= now`), merged in
  order. 46 buffers; **4.4ms exec / 2.7ms plan**. PASS — bounded regardless
  of how stale the type's newest rows are.
- **(c) nonexistent slug (discovered accidentally via "awt"):** Subquery form
  produced the identical walk plan with ZERO possible matches → the LIMIT can
  never terminate the scan → full-table walk across all partitions; query had
  to be killed. **FAIL — and user-triggerable via `?integration_type=<typo>`
  on the API.** The materialized-ids form short-circuits (`__in=[]` → Django
  emits no query).
- **Estimation finding:** the Subquery form gets a near-identical ~12.1M-row
  estimate for every slug (spidertracks 12,155,810 vs nonexistent "awt"
  12,160,386) — the planner is blind behind the opaque subquery, so plan
  choice is type-independent and the outcome depends entirely on where the
  type's rows sit in `created_at` order.

## Decision: switch to materialized ids

Do not ship the `Subquery` form. In the filter/view:

1. Resolve `ids = list(Integration.objects.filter(type__value__iexact=slug).values_list("id", flat=True))` in Python.
2. If `ids` is empty (unknown or typo'd slug), return an empty page early —
   sane API semantics and no DB round trip.
3. Pass the literal list to `integration__in` — with real per-id statistics
   the planner picks the composite index for sparse types (measured: 4.4ms)
   and remains free to choose the newest-first walk where it genuinely wins
   (dense types).

Option 2 (denormalized `integration_type` on ActivityLog) is NOT required.
Residual note: revisit the IN-list size if any type ever accumulates
thousands of integrations (today's max is low hundreds).

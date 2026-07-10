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

# Prod Redis Inspection & Stale-Key Cleanup — Design

**Date:** 2026-08-04
**Status:** Approved
**Target:** ER dispatcher Redis in production (private IP, reached locally via port-forward/tunnel)

## Problem

The ER dispatcher's production Redis is filling up. Volume comes from two sources:

1. `dispatched_observation.{gundi_id}.{destination_id}` idempotency keys — one per
   observation per destination, 25h TTL. These self-expire and MUST NOT be deleted
   early: they enforce the PubSub redelivery-idempotency contract
   (`gundi-dispatcher-er/core/event_handlers.py::is_observation_dispatched`); deleting
   a live key can cause duplicate delivery to ER (409 loops with throttling distress).
2. Leaked keys with **no TTL** — Movebank integration `backfill.*` job-queue keys and
   `backfill_watermark.*` keys accumulate per job and never expire. Pre-fix
   `dispatched_observation` strays without TTL may also exist (the
   `DISPATCHED_OBSERVATIONS_CACHE_TTL` env-var bug fixed in gundi-dispatcher-er PR #45).

We need (a) visibility into which key families use how much memory, and (b) a safe way
to delete old no-TTL keys — first as manually run scripts (phase 1), later as a
recurring in-cluster job (phase 2).

## Phase 1: Two standalone scripts

Location: `cdip_admin/scripts/`. No Django dependency; plain `redis`-py, configured via
`REDIS_HOST` / `REDIS_PORT` env vars (port defaults to 6379). Both scripts throttle
their SCAN loops (`--throttle`, default 50ms sleep between batches) to cap prod load,
and show progress (scanned/total, rate) like the existing idle-key script.

### `redis_memory_profiler.py` (read-only)

1. Always prints an instance overview first:
   - `INFO memory`: used_memory_human, maxmemory + policy, fragmentation ratio
   - `INFO keyspace`: key/expires counts per db
2. Given an optional positional `db` argument, additionally profiles that db (with no
   `db`, only the overview is printed): SCAN loop, pipelined `MEMORY USAGE` (sampled)
   + `TTL` per key, aggregated by prefix.
   - Prefix = first N segments of the key split on `.` or `:` (`--depth`, default 1).
     `dispatched_observation.{uuid}.{uuid}` → `dispatched_observation`;
     `backfill_watermark.123` → `backfill_watermark`.
3. Output: one row per prefix, sorted by total bytes desc — key count, total MB,
   avg bytes/key, **% of keys with no TTL** (the leak-detector column).

### `redis_stale_key_cleaner.py` (destructive, railed)

Selection rule: a key is a deletion candidate **only if `TTL == -1` (no expiry) AND
`OBJECT IDLETIME` > threshold**. Keys with any TTL are never candidates.

CLI:

- `db` (positional, required)
- `--idle-threshold DAYS` (float, default 30)
- `--match GLOB` — optional `SCAN MATCH` pattern to constrain a run (e.g. `backfill*`)
- `--delete` — actually delete; **without it the script is a dry-run** (inverted from
  the earlier idle-key script's default)
- `--yes` — skip the confirmation prompt (for unattended/phase-2 use)
- `--throttle MS`, `--batch-size N` (default 500)

Safety rails:

1. Dry-run is the default; deletion requires explicit `--delete`.
2. Hard floor: `--delete` combined with `--idle-threshold < 2` (days) is refused.
3. Keys with TTL ≥ 0 are never touched (they self-expire; early deletion of
   `dispatched_observation.*` breaks redelivery idempotency).
4. Before the confirmation prompt, print a candidate summary: per-prefix count + MB
   (`MEMORY USAGE` fetched for candidates only), plus the top 20 largest candidates —
   the operator sees exactly which key families will be deleted.
5. Deletion uses `UNLINK` (non-blocking server-side) in batches with throttle.
6. If `OBJECT IDLETIME` returns an error (e.g. LFU maxmemory-policy), abort with a
   clear message — never treat unknown idle as 0.
7. Interruption-safe: state is recomputed from live Redis on every run; re-running is
   always safe.

## Error handling

- Keys deleted/expired mid-scan: pipeline returns nil for that key; skip silently.
- Connection errors: fail fast with the error; the operator re-runs.
- `MEMORY USAGE` returning nil (key gone): treat as 0 bytes / skip.

## Testing

- Core logic (candidate selection, prefix bucketing, batch chunking, summary
  aggregation) factored into pure functions importable without executing the CLI.
- Unit tests with `fakeredis` under `cdip_admin/scripts/tests/`; `OBJECT IDLETIME`
  is not implemented by fakeredis, so idle lookup goes through a small wrapper the
  tests monkeypatch.
- Manual verification sequence:
  1. Both scripts against local docker Redis (seed keys with/without TTL).
  2. Profiler against prod (read-only).
  3. Cleaner dry-run against prod; sanity-check the candidate summary.
  4. First real deletion constrained with `--match 'backfill*'`, then a full run.

## Phase 2: Recurring in-cluster cleanup (planned, separate implementation)

- Containerize the cleaner (slim `python:3.11` base + `redis`), deploy a Kubernetes
  CronJob alongside the ER dispatcher, weekly schedule, running
  `--delete --yes --idle-threshold 30`, logs to Cloud Logging.
- **Prerequisite ticket (fix the leak at the source):** Movebank `backfill.*` /
  `backfill_watermark.*` keys should be written with a TTL. The CronJob is a backstop,
  not the primary mechanism.
- Open question deferred to phase 2: which repo owns the CronJob manifest (dispatcher
  helm chart vs. infra repo).
- Never enable `allkeys-*` eviction on this Redis as an alternative — it would evict
  live idempotency keys.

## Out of scope

- Shortening the `dispatched_observation` TTL (must stay ≥ PubSub subscription max
  event age; see gundi-dispatcher-er PR #45 context).
- Offline RDB analysis tooling.
- Changes to the Movebank integration itself (tracked as the phase-2 prerequisite
  ticket).

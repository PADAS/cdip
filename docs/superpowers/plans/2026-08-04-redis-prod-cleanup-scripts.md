# Prod Redis Profiler & Stale-Key Cleaner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Two standalone CLI scripts — a read-only Redis memory profiler and a safety-railed stale-key cleaner — for trimming the ER dispatcher's production Redis (phase 1 of `docs/superpowers/specs/2026-08-04-redis-prod-cleanup-design.md`).

**Architecture:** A small shared helpers module (`redis_ops_common.py`) plus two CLI scripts in `cdip_admin/scripts/`. All Redis-touching logic is factored into functions that accept injectable fetcher callables so unit tests can run on `fakeredis` (which doesn't implement `OBJECT IDLETIME`, and whose `MEMORY USAGE` support we don't rely on).

**Tech Stack:** Python 3.10+, `redis` 6.4.0 (already pinned), `fakeredis` (new dev dep), pytest (repo convention: run from `cdip_admin/` with the venv at `<repo>/.venv`).

## Global Constraints

- Scripts live in `cdip_admin/scripts/`, import nothing from Django, and read `REDIS_HOST` (required) / `REDIS_PORT` (default `6379`) from the environment.
- Cleaner candidate rule (spec §Cleaner): key is a candidate **only if `TTL == -1` AND `OBJECT IDLETIME > threshold`**. Keys with any TTL are NEVER candidates.
- Dry-run is the cleaner's default; deletion requires explicit `--delete`.
- Hard floor: `--delete` with `--idle-threshold < 2` (days) must be refused (exit 1).
- Deletion uses `UNLINK` (never `DEL`), in batches (default 500), throttled.
- If `OBJECT IDLETIME` errors (e.g. LFU maxmemory-policy), abort with a clear message — never treat idle as 0.
- Keys gone mid-scan (`TTL == -2`, or nil `MEMORY USAGE`): skip silently / treat as 0 bytes.
- SCAN loops sleep between batches (`--throttle`, default 50 ms).
- Tests: `fakeredis` under `cdip_admin/scripts/tests/`; idle-time and (for aggregation) stats fetchers are injected in tests.
- Dependencies via pip-compile: edit `dependencies/requirements-dev.in`, then from repo root run `pip-compile --output-file=dependencies/requirements-dev.txt dependencies/requirements-dev.in dependencies/requirements.in`.
- Run tests as: `cd cdip_admin && ../.venv/bin/pytest scripts/tests/... -v` (pytest-django loads `cdip_admin.local_settings`; these tests never touch the DB, so no DB env overrides are needed).
- Commit after each task with a `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` trailer.

---

### Task 1: Dev dependency + shared helpers module

**Files:**
- Modify: `dependencies/requirements-dev.in` (add `fakeredis`)
- Modify: `dependencies/requirements-dev.txt` (via pip-compile)
- Create: `cdip_admin/scripts/tests/__init__.py` (empty)
- Create: `cdip_admin/scripts/tests/test_redis_ops_common.py`
- Create: `cdip_admin/scripts/redis_ops_common.py`

**Interfaces:**
- Consumes: nothing.
- Produces (used by Tasks 2–5):
  - `get_redis_from_env(db: int) -> redis.Redis` — raises `SystemExit(1)` with a printed error if `REDIS_HOST` unset or `REDIS_PORT` non-integer.
  - `key_prefix(key: bytes, depth: int = 1) -> str` — first `depth` segments split on `.`/`:`, joined with `.`; undecodable bytes replaced.
  - `chunked(items: list, size: int)` — generator of lists of ≤ `size` items.
  - `iter_key_batches(r, match=None, count=500, throttle_seconds=0.05)` — generator yielding non-empty key batches from SCAN, sleeping `throttle_seconds` between iterations.

- [ ] **Step 1: Add fakeredis to dev requirements and install it**

Append to `dependencies/requirements-dev.in`:

```
fakeredis
```

Then from the repo root:

```bash
.venv/bin/pip install pip-tools 2>/dev/null; .venv/bin/pip-compile --output-file=dependencies/requirements-dev.txt dependencies/requirements-dev.in dependencies/requirements.in
.venv/bin/pip install fakeredis
```

(If `pip-compile` is unavailable or errors on unrelated pins, still `pip install fakeredis` so tests run, and note the compile problem in the commit message.)

- [ ] **Step 2: Create the test package and write failing tests**

Create empty `cdip_admin/scripts/tests/__init__.py`, then `cdip_admin/scripts/tests/test_redis_ops_common.py`:

```python
import fakeredis
import pytest

from scripts.redis_ops_common import (
    chunked,
    get_redis_from_env,
    iter_key_batches,
    key_prefix,
)


class TestKeyPrefix:
    def test_dot_separated_key_buckets_to_first_segment(self):
        assert key_prefix(b"dispatched_observation.0a1b.9f8e") == "dispatched_observation"

    def test_colon_separated_key(self):
        assert key_prefix(b"backfill:job:123") == "backfill"

    def test_depth_two_joins_first_two_segments(self):
        assert key_prefix(b"backfill.movebank.123", depth=2) == "backfill.movebank"

    def test_key_without_separator_is_its_own_prefix(self):
        assert key_prefix(b"celery") == "celery"

    def test_undecodable_bytes_do_not_crash(self):
        assert key_prefix(b"\xff\xfe.tail") == "��"


class TestChunked:
    def test_splits_into_batches_of_size(self):
        assert list(chunked([1, 2, 3, 4, 5], 2)) == [[1, 2], [3, 4], [5]]

    def test_empty_list_yields_nothing(self):
        assert list(chunked([], 10)) == []


class TestGetRedisFromEnv:
    def test_missing_host_exits(self, monkeypatch):
        monkeypatch.delenv("REDIS_HOST", raising=False)
        with pytest.raises(SystemExit):
            get_redis_from_env(0)

    def test_non_integer_port_exits(self, monkeypatch):
        monkeypatch.setenv("REDIS_HOST", "localhost")
        monkeypatch.setenv("REDIS_PORT", "not-a-port")
        with pytest.raises(SystemExit):
            get_redis_from_env(0)

    def test_valid_env_returns_client(self, monkeypatch):
        monkeypatch.setenv("REDIS_HOST", "localhost")
        monkeypatch.setenv("REDIS_PORT", "6390")
        client = get_redis_from_env(3)
        kwargs = client.connection_pool.connection_kwargs
        assert (kwargs["host"], kwargs["port"], kwargs["db"]) == ("localhost", 6390, 3)


class TestIterKeyBatches:
    def _seeded(self):
        r = fakeredis.FakeRedis()
        for i in range(25):
            r.set(f"prefix.{i}", "x")
        r.set("other.key", "x")
        return r

    def test_yields_all_keys_across_batches(self):
        r = self._seeded()
        seen = [k for batch in iter_key_batches(r, count=10, throttle_seconds=0) for k in batch]
        assert len(seen) == 26
        assert set(seen) == set(r.keys("*"))

    def test_match_filters_keys(self):
        r = self._seeded()
        seen = [k for batch in iter_key_batches(r, match="prefix.*", count=10, throttle_seconds=0) for k in batch]
        assert len(seen) == 25
        assert all(k.startswith(b"prefix.") for k in seen)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd cdip_admin && ../.venv/bin/pytest scripts/tests/test_redis_ops_common.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.redis_ops_common'`

- [ ] **Step 4: Implement the module**

Create `cdip_admin/scripts/redis_ops_common.py`:

```python
"""Shared helpers for the standalone Redis ops scripts. No Django dependency."""
import os
import re
import time

import redis

_SEPARATORS = re.compile(r"[.:]")


def get_redis_from_env(db):
    """Build a client from REDIS_HOST (required) and REDIS_PORT (default 6379)."""
    host = os.environ.get("REDIS_HOST")
    if not host:
        print("Error: REDIS_HOST environment variable is not set")
        raise SystemExit(1)
    port_str = os.environ.get("REDIS_PORT", "6379")
    try:
        port = int(port_str)
    except ValueError:
        print(f"Error: REDIS_PORT must be an integer, got '{port_str}'")
        raise SystemExit(1)
    return redis.Redis(host=host, port=port, db=db)


def key_prefix(key, depth=1):
    """Bucket a key by its first `depth` segments, splitting on '.' and ':'."""
    parts = _SEPARATORS.split(key.decode(errors="replace"))
    return ".".join(parts[:depth])


def chunked(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def iter_key_batches(r, match=None, count=500, throttle_seconds=0.05):
    """Yield batches of keys via SCAN, sleeping between iterations to cap server load."""
    cursor = 0
    while True:
        cursor, keys = r.scan(cursor, match=match, count=count)
        if keys:
            yield keys
        if cursor == 0:
            return
        if throttle_seconds:
            time.sleep(throttle_seconds)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd cdip_admin && ../.venv/bin/pytest scripts/tests/test_redis_ops_common.py -v`
Expected: PASS (all)

- [ ] **Step 6: Commit**

```bash
git add dependencies/requirements-dev.in dependencies/requirements-dev.txt \
  cdip_admin/scripts/tests/__init__.py cdip_admin/scripts/tests/test_redis_ops_common.py \
  cdip_admin/scripts/redis_ops_common.py
git commit -m "Add fakeredis dev dep and shared helpers for Redis ops scripts"
```

---

### Task 2: Profiler aggregation logic

**Files:**
- Create: `cdip_admin/scripts/redis_memory_profiler.py` (logic only; CLI comes in Task 3)
- Create: `cdip_admin/scripts/tests/test_redis_memory_profiler.py`

**Interfaces:**
- Consumes: `key_prefix` from `scripts.redis_ops_common`.
- Produces (used by Task 3):
  - `PrefixStats` dataclass: fields `count: int = 0`, `total_bytes: int = 0`, `no_ttl_count: int = 0`.
  - `fetch_key_stats(r, keys) -> list[tuple[int | None, int]]` — pipelined `(MEMORY USAGE samples=0, TTL)` per key, order-aligned with `keys`.
  - `aggregate_prefix_stats(key_batches, stats_fetcher, depth=1, on_batch=None) -> dict[str, PrefixStats]` — `stats_fetcher(keys)` must return what `fetch_key_stats` returns; `on_batch(n_keys)` called per batch.
  - `format_stats_table(stats: dict[str, PrefixStats]) -> str` — rows sorted by `total_bytes` desc with columns: prefix, keys, MB, avg B, % no-TTL.

- [ ] **Step 1: Write failing tests**

Create `cdip_admin/scripts/tests/test_redis_memory_profiler.py`:

```python
from scripts.redis_memory_profiler import (
    PrefixStats,
    aggregate_prefix_stats,
    format_stats_table,
)

STATS_TABLE = {
    b"disp.1.a": (100, 90000),      # (memory bytes, ttl seconds)
    b"disp.2.b": (150, 90000),
    b"backfill.9": (1000, -1),      # leaked: no TTL
    b"gone.1": (None, -2),          # vanished mid-scan
}


def fake_fetcher(keys):
    return [STATS_TABLE[k] for k in keys]


class TestAggregatePrefixStats:
    def test_aggregates_counts_bytes_and_no_ttl_by_prefix(self):
        batches = [[b"disp.1.a", b"disp.2.b"], [b"backfill.9"]]
        stats = aggregate_prefix_stats(batches, fake_fetcher)
        assert stats["disp"] == PrefixStats(count=2, total_bytes=250, no_ttl_count=0)
        assert stats["backfill"] == PrefixStats(count=1, total_bytes=1000, no_ttl_count=1)

    def test_key_gone_mid_scan_is_skipped(self):
        stats = aggregate_prefix_stats([[b"gone.1", b"backfill.9"]], fake_fetcher)
        assert "gone" not in stats
        assert stats["backfill"].count == 1

    def test_nil_memory_usage_counts_as_zero_bytes(self):
        def fetcher(keys):
            return [(None, -1)]
        stats = aggregate_prefix_stats([[b"backfill.9"]], fetcher)
        assert stats["backfill"] == PrefixStats(count=1, total_bytes=0, no_ttl_count=1)

    def test_on_batch_reports_progress(self):
        seen = []
        aggregate_prefix_stats(
            [[b"disp.1.a", b"disp.2.b"], [b"backfill.9"]], fake_fetcher, on_batch=seen.append
        )
        assert seen == [2, 1]


class TestFormatStatsTable:
    def test_rows_sorted_by_total_bytes_desc_with_leak_column(self):
        stats = {
            "small": PrefixStats(count=10, total_bytes=1000, no_ttl_count=0),
            "big": PrefixStats(count=4, total_bytes=8 * 1048576, no_ttl_count=2),
        }
        out = format_stats_table(stats)
        lines = out.splitlines()
        assert "prefix" in lines[0] and "% no-TTL" in lines[0]
        assert lines[1].startswith("big")
        assert "8.0" in lines[1] and "50.0%" in lines[1]
        assert lines[2].startswith("small")
        assert "0.0%" in lines[2]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd cdip_admin && ../.venv/bin/pytest scripts/tests/test_redis_memory_profiler.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.redis_memory_profiler'`

- [ ] **Step 3: Implement the logic**

Create `cdip_admin/scripts/redis_memory_profiler.py`:

```python
"""Read-only memory profiler for a Redis instance: per-db overview plus
per-key-prefix memory/count/no-TTL breakdown. Never writes or deletes.

Usage:
    REDIS_HOST=... python redis_memory_profiler.py            # overview only
    REDIS_HOST=... python redis_memory_profiler.py 0 --depth 1
"""
import argparse
import sys
import time
from collections import defaultdict
from dataclasses import dataclass

from scripts.redis_ops_common import get_redis_from_env, iter_key_batches, key_prefix


@dataclass
class PrefixStats:
    count: int = 0
    total_bytes: int = 0
    no_ttl_count: int = 0


def fetch_key_stats(r, keys):
    """Pipelined (MEMORY USAGE, TTL) per key. Memory is None if the key vanished."""
    pipe = r.pipeline(transaction=False)
    for k in keys:
        pipe.memory_usage(k, samples=0)
    for k in keys:
        pipe.ttl(k)
    results = pipe.execute()
    return list(zip(results[: len(keys)], results[len(keys):]))


def aggregate_prefix_stats(key_batches, stats_fetcher, depth=1, on_batch=None):
    stats = defaultdict(PrefixStats)
    for keys in key_batches:
        for key, (mem, ttl) in zip(keys, stats_fetcher(keys)):
            if ttl == -2:  # key expired/deleted mid-scan
                continue
            s = stats[key_prefix(key, depth)]
            s.count += 1
            s.total_bytes += mem or 0
            if ttl == -1:
                s.no_ttl_count += 1
        if on_batch:
            on_batch(len(keys))
    return dict(stats)


def format_stats_table(stats):
    rows = sorted(stats.items(), key=lambda kv: kv[1].total_bytes, reverse=True)
    lines = [f"{'prefix':<50} {'keys':>12} {'MB':>10} {'avg B':>8} {'% no-TTL':>9}"]
    for prefix, s in rows:
        avg = s.total_bytes // s.count if s.count else 0
        pct = (s.no_ttl_count / s.count * 100) if s.count else 0.0
        lines.append(
            f"{prefix:<50} {s.count:>12,} {s.total_bytes / 1048576:>10.1f} "
            f"{avg:>8,} {pct:>8.1f}%"
        )
    return "\n".join(lines)
```

(CLI `main()` is added in Task 3 — this task delivers importable, tested logic.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd cdip_admin && ../.venv/bin/pytest scripts/tests/test_redis_memory_profiler.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add cdip_admin/scripts/redis_memory_profiler.py cdip_admin/scripts/tests/test_redis_memory_profiler.py
git commit -m "Add prefix-aggregation logic for Redis memory profiler"
```

---

### Task 3: Profiler CLI (overview + progress + wiring)

**Files:**
- Modify: `cdip_admin/scripts/redis_memory_profiler.py` (append `print_overview`, `parse_args`, `main`)
- Modify: `cdip_admin/scripts/tests/test_redis_memory_profiler.py` (append overview test)

**Interfaces:**
- Consumes: Task 2's functions; `get_redis_from_env`, `iter_key_batches` from common.
- Produces: `python redis_memory_profiler.py [db] [--depth N] [--scan-count N] [--throttle MS]` CLI; `print_overview(r)` printing INFO memory highlights + INFO keyspace.

- [ ] **Step 1: Write failing test for the overview**

Append to `cdip_admin/scripts/tests/test_redis_memory_profiler.py`:

```python
import fakeredis

from scripts.redis_memory_profiler import print_overview


class TestPrintOverview:
    def test_prints_memory_and_keyspace_sections(self, capsys):
        r = fakeredis.FakeRedis()
        r.set("a", "x")
        print_overview(r)
        out = capsys.readouterr().out
        assert "used_memory" in out
        assert "db0" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd cdip_admin && ../.venv/bin/pytest scripts/tests/test_redis_memory_profiler.py::TestPrintOverview -v`
Expected: FAIL — `ImportError: cannot import name 'print_overview'`

- [ ] **Step 3: Implement overview and CLI**

Append to `cdip_admin/scripts/redis_memory_profiler.py`:

```python
def print_overview(r):
    mem = r.info("memory")
    print(
        f"used_memory: {mem.get('used_memory_human')}  "
        f"maxmemory: {mem.get('maxmemory_human', mem.get('maxmemory'))} "
        f"(policy: {mem.get('maxmemory_policy')})  "
        f"fragmentation: {mem.get('mem_fragmentation_ratio')}"
    )
    keyspace = r.info("keyspace")
    for db_name in sorted(keyspace):
        info = keyspace[db_name]
        print(
            f"{db_name}: keys={info.get('keys'):,} expires={info.get('expires'):,} "
            f"avg_ttl={info.get('avg_ttl')}"
        )
    print()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Read-only Redis memory profiler: instance overview, plus "
        "per-prefix memory breakdown for one db."
    )
    parser.add_argument("db", type=int, nargs="?", default=None,
                        help="db number to profile by prefix (omit for overview only)")
    parser.add_argument("--depth", type=int, default=1,
                        help="key segments (split on . and :) per prefix bucket (default 1)")
    parser.add_argument("--scan-count", type=int, default=500,
                        help="SCAN COUNT hint per batch (default 500)")
    parser.add_argument("--throttle", type=float, default=50,
                        help="sleep between SCAN batches in ms (default 50)")
    return parser.parse_args()


def main():
    args = parse_args()
    r = get_redis_from_env(args.db if args.db is not None else 0)
    print_overview(r)
    if args.db is None:
        return

    total = r.dbsize()
    print(f"Profiling db {args.db} (~{total:,} keys) by prefix (depth {args.depth})...\n")
    progress = {"scanned": 0, "start": time.time(), "last_print": 0.0}

    def on_batch(n):
        progress["scanned"] += n
        now = time.time()
        if now - progress["last_print"] >= 1.0:
            elapsed = now - progress["start"]
            rate = progress["scanned"] / elapsed if elapsed > 0 else 0
            pct = (progress["scanned"] / total * 100) if total else 0
            sys.stdout.write(
                f"\rScanned {progress['scanned']:,}/{total:,} ({pct:.1f}%) | {rate:,.0f} keys/s"
            )
            sys.stdout.flush()
            progress["last_print"] = now

    batches = iter_key_batches(
        r, count=args.scan_count, throttle_seconds=args.throttle / 1000.0
    )
    stats = aggregate_prefix_stats(
        batches, lambda keys: fetch_key_stats(r, keys), depth=args.depth, on_batch=on_batch
    )
    sys.stdout.write("\n\n")
    print(format_stats_table(stats))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the full profiler test file**

Run: `cd cdip_admin && ../.venv/bin/pytest scripts/tests/test_redis_memory_profiler.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add cdip_admin/scripts/redis_memory_profiler.py cdip_admin/scripts/tests/test_redis_memory_profiler.py
git commit -m "Add CLI and instance overview to Redis memory profiler"
```

---

### Task 4: Cleaner candidate selection

**Files:**
- Create: `cdip_admin/scripts/redis_stale_key_cleaner.py` (selection logic; CLI in Task 5)
- Create: `cdip_admin/scripts/tests/test_redis_stale_key_cleaner.py`

**Interfaces:**
- Consumes: `iter_key_batches` from common.
- Produces (used by Task 5):
  - `IdleTimeUnavailable(RuntimeError)`.
  - `fetch_idle_times(r, keys) -> list[int | None]` — pipelined `OBJECT IDLETIME`; raises `IdleTimeUnavailable` on `redis.exceptions.ResponseError`.
  - `find_stale_candidates(r, idle_threshold_seconds, match=None, scan_count=500, throttle_seconds=0.05, idle_fetcher=None, on_progress=None) -> list[tuple[bytes, int]]` — `(key, idle_seconds)` pairs where `TTL == -1` and idle > threshold; `idle_fetcher(r, keys)` defaults to `fetch_idle_times`; `on_progress(n_scanned_in_batch, n_candidates_total)`.

- [ ] **Step 1: Write failing tests**

Create `cdip_admin/scripts/tests/test_redis_stale_key_cleaner.py`:

```python
import fakeredis
import pytest
import redis

from scripts.redis_stale_key_cleaner import (
    IdleTimeUnavailable,
    fetch_idle_times,
    find_stale_candidates,
)

DAY = 86400


def _seeded():
    r = fakeredis.FakeRedis()
    r.set("backfill.old", "x")                                   # no TTL, idle 40d
    r.set("backfill.recent", "x")                                # no TTL, idle 1d
    r.set("dispatched_observation.a.b", "x", ex=25 * 3600)       # has TTL, idle 40d
    idle = {
        b"backfill.old": 40 * DAY,
        b"backfill.recent": 1 * DAY,
        b"dispatched_observation.a.b": 40 * DAY,
    }
    return r, lambda _r, keys: [idle[k] for k in keys]


class TestFindStaleCandidates:
    def test_only_no_ttl_keys_over_threshold_are_candidates(self):
        r, idle_fetcher = _seeded()
        cands = find_stale_candidates(
            r, idle_threshold_seconds=30 * DAY, idle_fetcher=idle_fetcher, throttle_seconds=0
        )
        assert cands == [(b"backfill.old", 40 * DAY)]

    def test_key_with_ttl_is_never_a_candidate_even_when_idle(self):
        r, idle_fetcher = _seeded()
        cands = find_stale_candidates(
            r, idle_threshold_seconds=1, idle_fetcher=idle_fetcher, throttle_seconds=0
        )
        assert all(not k.startswith(b"dispatched_observation") for k, _ in cands)

    def test_match_constrains_scan(self):
        r, idle_fetcher = _seeded()
        r.set("other.old", "x")
        cands = find_stale_candidates(
            r, idle_threshold_seconds=1, match="backfill*",
            idle_fetcher=idle_fetcher, throttle_seconds=0,
        )
        assert {k for k, _ in cands} == {b"backfill.old", b"backfill.recent"}

    def test_idle_fetcher_error_propagates(self):
        r, _ = _seeded()

        def boom(_r, keys):
            raise IdleTimeUnavailable("no idle times")

        with pytest.raises(IdleTimeUnavailable):
            find_stale_candidates(
                r, idle_threshold_seconds=1, idle_fetcher=boom, throttle_seconds=0
            )

    def test_on_progress_reports_totals(self):
        r, idle_fetcher = _seeded()
        calls = []
        find_stale_candidates(
            r, idle_threshold_seconds=30 * DAY, idle_fetcher=idle_fetcher,
            throttle_seconds=0, on_progress=lambda n, c: calls.append((n, c)),
        )
        assert sum(n for n, _ in calls) == 3
        assert calls[-1][1] == 1


class TestFetchIdleTimes:
    def test_response_error_raises_idle_time_unavailable(self, monkeypatch):
        r = fakeredis.FakeRedis()
        r.set("k", "v")

        class BoomPipe:
            def execute_command(self, *args):
                return self

            def execute(self):
                raise redis.exceptions.ResponseError("An LFU maxmemory policy is selected")

        monkeypatch.setattr(r, "pipeline", lambda transaction=False: BoomPipe())
        with pytest.raises(IdleTimeUnavailable, match="OBJECT IDLETIME failed"):
            fetch_idle_times(r, [b"k"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd cdip_admin && ../.venv/bin/pytest scripts/tests/test_redis_stale_key_cleaner.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.redis_stale_key_cleaner'`

- [ ] **Step 3: Implement selection logic**

Create `cdip_admin/scripts/redis_stale_key_cleaner.py`:

```python
"""Find (and optionally UNLINK) keys that have NO TTL and have been idle longer
than a threshold. Keys with any TTL are never touched: they expire on their own,
and deleting live dispatched_observation.* idempotency keys early breaks the
PubSub redelivery contract (see docs/superpowers/specs/2026-08-04-redis-prod-cleanup-design.md).

Dry-run by default; deletion requires --delete.

Usage:
    REDIS_HOST=... python redis_stale_key_cleaner.py 0                       # dry-run, 30d
    REDIS_HOST=... python redis_stale_key_cleaner.py 0 --match 'backfill*' --delete
"""
import argparse
import sys
import time

import redis

from scripts.redis_ops_common import (
    chunked,
    get_redis_from_env,
    iter_key_batches,
    key_prefix,
)

MIN_DELETE_IDLE_DAYS = 2.0
DAY_SECONDS = 86400


class IdleTimeUnavailable(RuntimeError):
    pass


def fetch_idle_times(r, keys):
    """Pipelined OBJECT IDLETIME. Aborts loudly if the server can't answer
    (e.g. LFU maxmemory-policy) — never treat unknown idle as 0."""
    pipe = r.pipeline(transaction=False)
    for k in keys:
        pipe.execute_command("OBJECT", "IDLETIME", k)
    try:
        return pipe.execute()
    except redis.exceptions.ResponseError as exc:
        raise IdleTimeUnavailable(
            f"OBJECT IDLETIME failed ({exc}). If maxmemory-policy is an LFU policy, "
            "idle times are unavailable; aborting rather than treating idle as 0."
        ) from exc


def find_stale_candidates(r, idle_threshold_seconds, match=None, scan_count=500,
                          throttle_seconds=0.05, idle_fetcher=None, on_progress=None):
    """Return (key, idle_seconds) for keys with TTL == -1 and idle > threshold."""
    idle_fetcher = idle_fetcher or fetch_idle_times
    candidates = []
    for keys in iter_key_batches(r, match=match, count=scan_count,
                                 throttle_seconds=throttle_seconds):
        pipe = r.pipeline(transaction=False)
        for k in keys:
            pipe.ttl(k)
        ttls = pipe.execute()
        no_ttl_keys = [k for k, ttl in zip(keys, ttls) if ttl == -1]
        if no_ttl_keys:
            for k, idle in zip(no_ttl_keys, idle_fetcher(r, no_ttl_keys)):
                if idle is not None and idle > idle_threshold_seconds:
                    candidates.append((k, idle))
        if on_progress:
            on_progress(len(keys), len(candidates))
    return candidates
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd cdip_admin && ../.venv/bin/pytest scripts/tests/test_redis_stale_key_cleaner.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add cdip_admin/scripts/redis_stale_key_cleaner.py cdip_admin/scripts/tests/test_redis_stale_key_cleaner.py
git commit -m "Add no-TTL idle-key candidate selection for Redis cleaner"
```

---

### Task 5: Cleaner rails, summary, deletion, CLI

**Files:**
- Modify: `cdip_admin/scripts/redis_stale_key_cleaner.py` (append summary/delete/validation/CLI)
- Modify: `cdip_admin/scripts/tests/test_redis_stale_key_cleaner.py` (append tests)

**Interfaces:**
- Consumes: Task 4's functions; `chunked`, `key_prefix` from common.
- Produces:
  - `validate_delete_args(delete: bool, idle_threshold_days: float) -> None` — `SystemExit(1)` if `delete` and `idle_threshold_days < MIN_DELETE_IDLE_DAYS` (2.0).
  - `fetch_sizes(r, keys) -> list[int]` — pipelined `MEMORY USAGE` (nil → 0), chunked internally (500/pipeline).
  - `summarize_candidates(sized: list[tuple[bytes, int, int]], depth=1) -> list[tuple[str, int, int]]` — input `(key, idle_seconds, size_bytes)`, output `(prefix, count, total_bytes)` sorted by bytes desc.
  - `delete_keys(r, keys, batch_size=500, throttle_seconds=0.05, on_progress=None) -> int` — UNLINKs in batches, returns deleted count.
  - CLI: `python redis_stale_key_cleaner.py DB [--idle-threshold DAYS] [--match GLOB] [--delete] [--yes] [--batch-size N] [--throttle MS]`.

- [ ] **Step 1: Write failing tests**

Append to `cdip_admin/scripts/tests/test_redis_stale_key_cleaner.py`:

```python
from scripts.redis_stale_key_cleaner import (
    MIN_DELETE_IDLE_DAYS,
    delete_keys,
    summarize_candidates,
    validate_delete_args,
)


class TestValidateDeleteArgs:
    def test_delete_below_floor_is_refused(self):
        with pytest.raises(SystemExit):
            validate_delete_args(delete=True, idle_threshold_days=1.9)

    def test_delete_at_floor_is_allowed(self):
        validate_delete_args(delete=True, idle_threshold_days=MIN_DELETE_IDLE_DAYS)

    def test_dry_run_below_floor_is_allowed(self):
        validate_delete_args(delete=False, idle_threshold_days=0.1)


class TestSummarizeCandidates:
    def test_groups_by_prefix_sorted_by_bytes_desc(self):
        sized = [
            (b"backfill.1", 40 * DAY, 100),
            (b"backfill.2", 41 * DAY, 300),
            (b"backfill_watermark.9", 50 * DAY, 5000),
        ]
        assert summarize_candidates(sized) == [
            ("backfill_watermark", 1, 5000),
            ("backfill", 2, 400),
        ]


class TestDeleteKeys:
    def test_unlinks_all_keys_in_batches_and_reports_progress(self):
        r = fakeredis.FakeRedis()
        keys = []
        for i in range(10):
            r.set(f"stale.{i}", "x")
            keys.append(f"stale.{i}".encode())
        r.set("keep.me", "x")
        progress = []
        deleted = delete_keys(r, keys, batch_size=3, throttle_seconds=0,
                              on_progress=progress.append)
        assert deleted == 10
        assert r.dbsize() == 1
        assert progress[-1] == 10
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd cdip_admin && ../.venv/bin/pytest scripts/tests/test_redis_stale_key_cleaner.py -v`
Expected: FAIL — `ImportError: cannot import name 'MIN_DELETE_IDLE_DAYS'` (or similar)

- [ ] **Step 3: Implement rails, summary, deletion, CLI**

Append to `cdip_admin/scripts/redis_stale_key_cleaner.py`:

```python
def validate_delete_args(delete, idle_threshold_days):
    if delete and idle_threshold_days < MIN_DELETE_IDLE_DAYS:
        print(
            f"Refusing --delete with --idle-threshold {idle_threshold_days} days: "
            f"the floor is {MIN_DELETE_IDLE_DAYS} days. Keys written recently may be "
            "live idempotency state."
        )
        raise SystemExit(1)


def fetch_sizes(r, keys):
    sizes = []
    for batch in chunked(keys, 500):
        pipe = r.pipeline(transaction=False)
        for k in batch:
            pipe.memory_usage(k, samples=0)
        sizes.extend(size or 0 for size in pipe.execute())
    return sizes


def summarize_candidates(sized, depth=1):
    totals = {}
    for key, _idle, size in sized:
        prefix = key_prefix(key, depth)
        count, total = totals.get(prefix, (0, 0))
        totals[prefix] = (count + 1, total + size)
    return sorted(
        ((prefix, count, total) for prefix, (count, total) in totals.items()),
        key=lambda row: row[2],
        reverse=True,
    )


def delete_keys(r, keys, batch_size=500, throttle_seconds=0.05, on_progress=None):
    deleted = 0
    for batch in chunked(keys, batch_size):
        deleted += r.unlink(*batch)
        if on_progress:
            on_progress(deleted)
        if throttle_seconds:
            time.sleep(throttle_seconds)
    return deleted


def parse_args():
    parser = argparse.ArgumentParser(
        description="Find (and optionally UNLINK) keys with NO TTL idle longer than "
        "a threshold. Dry-run unless --delete is given."
    )
    parser.add_argument("db", type=int, help="Redis database number to scan")
    parser.add_argument("--idle-threshold", type=float, default=30,
                        help="idle threshold in days (default 30)")
    parser.add_argument("--match", default=None,
                        help="optional SCAN MATCH glob, e.g. 'backfill*'")
    parser.add_argument("--delete", action="store_true",
                        help="actually delete candidates (default: dry-run)")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="skip the confirmation prompt")
    parser.add_argument("--batch-size", type=int, default=500,
                        help="keys per UNLINK batch (default 500)")
    parser.add_argument("--throttle", type=float, default=50,
                        help="sleep between SCAN/UNLINK batches in ms (default 50)")
    return parser.parse_args()


def main():
    args = parse_args()
    validate_delete_args(args.delete, args.idle_threshold)
    threshold_seconds = int(args.idle_threshold * DAY_SECONDS)
    throttle_seconds = args.throttle / 1000.0
    r = get_redis_from_env(args.db)

    total = r.dbsize()
    mode = "DELETE" if args.delete else "dry-run"
    print(
        f"db {args.db}: ~{total:,} keys; selecting no-TTL keys idle > "
        f"{args.idle_threshold} days (match={args.match or '*'}) [{mode}]\n"
    )

    progress = {"scanned": 0, "start": time.time(), "last_print": 0.0}

    def on_progress(n_batch, n_candidates):
        progress["scanned"] += n_batch
        now = time.time()
        if now - progress["last_print"] >= 1.0:
            elapsed = now - progress["start"]
            rate = progress["scanned"] / elapsed if elapsed > 0 else 0
            pct = (progress["scanned"] / total * 100) if total else 0
            sys.stdout.write(
                f"\rScanned {progress['scanned']:,}/{total:,} ({pct:.1f}%) "
                f"| {rate:,.0f} keys/s | {n_candidates:,} candidates"
            )
            sys.stdout.flush()
            progress["last_print"] = now

    try:
        candidates = find_stale_candidates(
            r, threshold_seconds, match=args.match, throttle_seconds=throttle_seconds,
            on_progress=on_progress,
        )
    except IdleTimeUnavailable as exc:
        print(f"\n{exc}")
        raise SystemExit(1)
    sys.stdout.write("\n\n")

    if not candidates:
        print("No candidates found.")
        return

    print(f"Found {len(candidates):,} candidate keys. Sizing candidates...")
    sizes = fetch_sizes(r, [k for k, _ in candidates])
    sized = [(k, idle, size) for (k, idle), size in zip(candidates, sizes)]
    total_bytes = sum(size for _, _, size in sized)

    print(f"\nCandidate summary ({total_bytes / 1048576:.1f} MB total):")
    print(f"{'prefix':<50} {'keys':>12} {'MB':>10}")
    for prefix, count, nbytes in summarize_candidates(sized):
        print(f"{prefix:<50} {count:>12,} {nbytes / 1048576:>10.1f}")

    print("\nTop 20 largest candidates:")
    for key, idle, size in sorted(sized, key=lambda row: row[2], reverse=True)[:20]:
        print(f"{key.decode(errors='replace')}: {size:,} B, idle {idle // DAY_SECONDS} days")

    if not args.delete:
        print("\nDry-run complete; nothing deleted. Re-run with --delete to remove these keys.")
        return

    if not args.yes:
        try:
            confirm = input(f"\nUNLINK {len(candidates):,} keys from db {args.db}? [y/N] ")
        except EOFError:
            confirm = ""
        if confirm.strip().lower() != "y":
            print("Aborted.")
            raise SystemExit(0)

    print()
    keys_to_delete = [k for k, _, _ in sized]
    del_start = time.time()

    def on_delete_progress(deleted):
        elapsed = time.time() - del_start
        rate = deleted / elapsed if elapsed > 0 else 0
        pct = deleted / len(keys_to_delete) * 100
        sys.stdout.write(
            f"\rUnlinked {deleted:,}/{len(keys_to_delete):,} ({pct:.1f}%) | {rate:,.0f} keys/s"
        )
        sys.stdout.flush()

    deleted = delete_keys(
        r, keys_to_delete, batch_size=args.batch_size,
        throttle_seconds=throttle_seconds, on_progress=on_delete_progress,
    )
    print(f"\n\nUnlinked {deleted:,} keys total.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the whole scripts test suite**

Run: `cd cdip_admin && ../.venv/bin/pytest scripts/tests/ -v`
Expected: PASS (all tests from Tasks 1–5)

- [ ] **Step 5: Commit**

```bash
git add cdip_admin/scripts/redis_stale_key_cleaner.py cdip_admin/scripts/tests/test_redis_stale_key_cleaner.py
git commit -m "Add safety rails, candidate summary, and UNLINK deletion to Redis cleaner"
```

---

### Task 6: End-to-end smoke test against a local Redis

**Files:**
- None created/modified — verification only (fix anything found, amend the relevant task's file, and commit fixes).

**Interfaces:**
- Consumes: both finished CLIs.
- Produces: verified scripts, ready for the prod sequence in the spec (profiler → dry-run → `--match 'backfill*'` delete → full run).

- [ ] **Step 1: Start a throwaway Redis and seed it**

```bash
docker run --rm -d --name redis-cleanup-smoke -p 6390:6379 redis:7
sleep 2
docker exec redis-cleanup-smoke redis-cli set backfill.job1 "$(head -c 2048 /dev/zero | tr '\0' 'x')"
docker exec redis-cleanup-smoke redis-cli set backfill_watermark.42 "w"
docker exec redis-cleanup-smoke redis-cli set dispatched_observation.aaa.bbb "d" EX 90000
```

- [ ] **Step 2: Run the profiler (overview + db 0)**

```bash
cd cdip_admin && REDIS_HOST=localhost REDIS_PORT=6390 ../.venv/bin/python -m scripts.redis_memory_profiler 0
```

Expected: overview shows `used_memory` and `db0: keys=3`; table has rows for `backfill` (% no-TTL = 100.0%), `backfill_watermark` (100.0%), `dispatched_observation` (0.0%), with `backfill` largest by MB.

- [ ] **Step 3: Run the cleaner dry-run with a zero threshold**

```bash
cd cdip_admin && REDIS_HOST=localhost REDIS_PORT=6390 ../.venv/bin/python -m scripts.redis_stale_key_cleaner 0 --idle-threshold 0
```

Expected: 2 candidates (`backfill.job1`, `backfill_watermark.42`); `dispatched_observation.aaa.bbb` absent; ends with "Dry-run complete; nothing deleted."
(Fresh keys have idle 0 and the rule is strictly `idle > threshold` — if 0 candidates appear, wait ~65s after seeding and re-run; OBJECT IDLETIME has ~second resolution and LRU-clock granularity.)

- [ ] **Step 4: Verify the delete floor refuses a low threshold**

```bash
cd cdip_admin && REDIS_HOST=localhost REDIS_PORT=6390 ../.venv/bin/python -m scripts.redis_stale_key_cleaner 0 --idle-threshold 0 --delete; echo "exit=$?"
```

Expected: "Refusing --delete..." message, `exit=1`, all 3 keys still present (`docker exec redis-cleanup-smoke redis-cli dbsize` → 3).

- [ ] **Step 5: Verify --match constrains the dry-run**

```bash
cd cdip_admin && REDIS_HOST=localhost REDIS_PORT=6390 ../.venv/bin/python -m scripts.redis_stale_key_cleaner 0 --idle-threshold 0 --match 'backfill.*'
```

Expected: exactly 1 candidate (`backfill.job1`; the glob `backfill.*` requires the literal dot, so `backfill_watermark.42` is excluded).

- [ ] **Step 6: Tear down and run the full suite once more**

```bash
docker stop redis-cleanup-smoke
cd cdip_admin && ../.venv/bin/pytest scripts/tests/ -v
```

Expected: container stops; all tests PASS. If any smoke step required code fixes, commit them:

```bash
git add -A cdip_admin/scripts && git commit -m "Fix issues found in Redis cleanup scripts smoke test"
```

---

## Not in this plan (phase 2, per spec)

The recurring CronJob (containerized cleaner, weekly `--delete --yes --idle-threshold 30`) and the fix-the-leak-at-source Movebank ticket are deliberately excluded; they get their own plan after these scripts have proven themselves against prod.

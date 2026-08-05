"""Find (and optionally UNLINK) keys that have NO TTL and have been idle longer
than a threshold. Keys with any TTL are never touched: they expire on their own,
and deleting live dispatched_observation.* idempotency keys early breaks the
PubSub redelivery contract (see docs/superpowers/specs/2026-08-04-redis-prod-cleanup-design.md).

Dry-run by default; deletion requires --delete.

Usage:
    cd cdip_admin && REDIS_HOST=... python -m scripts.redis_stale_key_cleaner 0                       # dry-run, 30d
    cd cdip_admin && REDIS_HOST=... python -m scripts.redis_stale_key_cleaner 0 --match 'backfill*' --delete
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
    non_negative_float,
    positive_int,
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
    """UNLINK keys in batches, re-checking TTL immediately beforehand.

    Candidate selection can be followed by a long interactive confirm prompt,
    during which a key could be re-created with a TTL (e.g. a fresh
    dispatched_observation.* idempotency key). Re-checking TTL right before
    UNLINK closes that window: any key whose TTL is no longer -1 is dropped
    rather than deleted.

    The two reasons for dropping a key are counted separately because they mean
    different things to an operator: a key that gained a TTL is live again and
    worth investigating, while a key that vanished (TTL == -2) expired or was
    deleted by someone else and is unremarkable.

    Returns (deleted, skipped_ttl, skipped_gone).
    """
    deleted = 0
    skipped_ttl = 0
    skipped_gone = 0
    for batch in chunked(keys, batch_size):
        pipe = r.pipeline(transaction=False)
        for k in batch:
            pipe.ttl(k)
        ttls = pipe.execute()
        to_delete = []
        for key, ttl in zip(batch, ttls):
            if ttl == -1:
                to_delete.append(key)
            elif ttl == -2:
                skipped_gone += 1
            else:
                skipped_ttl += 1
        if to_delete:
            deleted += r.unlink(*to_delete)
        if on_progress:
            on_progress(deleted)
        if throttle_seconds:
            time.sleep(throttle_seconds)
    return deleted, skipped_ttl, skipped_gone


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
    parser.add_argument("--batch-size", type=positive_int, default=500,
                        help="keys per UNLINK batch (default 500)")
    parser.add_argument("--throttle", type=non_negative_float, default=50,
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

    deleted, skipped_ttl, skipped_gone = delete_keys(
        r, keys_to_delete, batch_size=args.batch_size,
        throttle_seconds=throttle_seconds, on_progress=on_delete_progress,
    )
    print(f"\n\nUnlinked {deleted:,} keys total.")
    if skipped_ttl:
        print(f"Skipped {skipped_ttl:,} keys that acquired a TTL since selection.")
    if skipped_gone:
        print(f"Skipped {skipped_gone:,} keys that no longer existed.")


if __name__ == "__main__":
    main()

"""Keep smartconnect-client's data model cache in step with the installed client.

smartconnect-client caches parsed SMART data models under ``cache:smart-ca:*``
with no TTL. A client upgrade that changes the parsed shape (1.11 -> 1.15 added
the CM node id the split-mode event type slug uses) would otherwise serve stale
entries to the first sync after a deploy. The flush runs from whichever task
gets there first, and keeps running for a grace period after the upgrade so
entries written by an old worker that is still draining are flushed too.
"""
import logging
import time

from smartconnect import __version__ as smartconnect_version
from smartconnect.cache import cache as smart_cache

logger = logging.getLogger(__name__)

GENERATION_KEY = "cache:smart-ca:generation"
CACHE_PATTERN = "cache:smart-ca:*"
# Longer than a rolling worker deployment: old workers can repopulate the cache
# until their last pod stops, so every task in this window flushes again.
UPGRADE_GRACE_SECONDS = 3600


def _parse_marker(raw) -> tuple[str | None, float | None]:
    """Return (version, upgraded_at); a marker without a stamp has None."""
    if raw is None:
        return None, None
    value = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    version, _, stamp = value.partition("@")
    try:
        return version, float(stamp)
    except ValueError:
        return version, None


def ensure_smart_cache_generation(
    client=None, version: str = smartconnect_version, now: float | None = None
) -> bool:
    """Flush the SMART data model cache unless this client version has owned it
    for longer than the upgrade grace period.

    Uses the same Redis client smartconnect-client reads through, so the
    database is right by construction. Returns True when a flush happened.
    """
    client = client if client is not None else smart_cache
    now = time.time() if now is None else now
    current, upgraded_at = _parse_marker(client.get(GENERATION_KEY))
    settled = upgraded_at is not None and now - upgraded_at > UPGRADE_GRACE_SECONDS
    if current == version and settled:
        return False
    deleted = 0
    for key in client.scan_iter(match=CACHE_PATTERN):
        name = key.decode("utf-8") if isinstance(key, bytes) else key
        if name != GENERATION_KEY:
            client.delete(key)
            deleted += 1
    if current != version or upgraded_at is None:
        # First task on the new client: start the grace period. Later flushes
        # inside the window keep the original stamp so the window ends.
        client.set(GENERATION_KEY, f"{version}@{now}")
    logger.warning(
        "Flushed %d smartconnect data model cache entries: cache generation %s -> %s",
        deleted,
        current,
        version,
    )
    return True

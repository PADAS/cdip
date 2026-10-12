"""Keep smartconnect-client's data model cache in step with the installed client.

smartconnect-client caches parsed SMART data models under ``cache:smart-ca:*``
with no TTL. A client upgrade that changes the parsed shape (1.11 -> 1.15 added
the CM node id the split-mode event type slug uses) would otherwise serve stale
entries to the first sync after a deploy. The flush runs once per client
version, from whichever task gets there first.
"""
import logging

from smartconnect import __version__ as smartconnect_version
from smartconnect.cache import cache as smart_cache

logger = logging.getLogger(__name__)

GENERATION_KEY = "cache:smart-ca:generation"
CACHE_PATTERN = "cache:smart-ca:*"


def ensure_smart_cache_generation(client=None, version: str = smartconnect_version) -> bool:
    """Flush the SMART data model cache unless it was written by this client version.

    Uses the same Redis client smartconnect-client reads through, so the
    database is right by construction. Returns True when a flush happened.
    """
    client = client if client is not None else smart_cache
    current = client.get(GENERATION_KEY)
    if isinstance(current, bytes):
        current = current.decode("utf-8")
    if current == version:
        return False
    deleted = 0
    for key in client.scan_iter(match=CACHE_PATTERN):
        name = key.decode("utf-8") if isinstance(key, bytes) else key
        if name != GENERATION_KEY:
            client.delete(key)
            deleted += 1
    client.set(GENERATION_KEY, version)
    logger.warning(
        "Flushed %d smartconnect data model cache entries: cache generation %s -> %s",
        deleted,
        current,
        version,
    )
    return True

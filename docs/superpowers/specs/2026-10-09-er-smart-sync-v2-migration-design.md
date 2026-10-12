# ER/SMART sync: move to EarthRanger event type v2 via er-smart-sync

**Date:** 2026-10-09
**Status:** Draft for review
**Author:** Chris Doehring (with Claude)

## Problem

EarthRanger deprecates writes to version 1 event types on 2026-07-31 and
removes them on **2026-10-15** (`das/activity/deprecations.py`,
`V1_EVENTTYPE_DEPRECATION`). The deprecated endpoints are:

- `POST/PATCH /api/v1.0/activity/events/eventtypes/`
- `/api/v1.0/activity/events/eventtypes/<id>/`
- `/api/v1.0/activity/events/schema/eventtype/<value>/`

Reads of events, patrols, files, subjects, observations and categories are
not affected.

The Gundi Portal's `sync_integrations` app (`er_smart_sync.py`, `tasks.py`)
pushes SMART Connect data models into EarthRanger as v1 event types through
`dasclient`, and reads ER events and patrols back into SMART Connect. After
the sunset the datamodel push fails on every site. The code is old, pins a
GitHub-wheel `dasclient`, and duplicates logic that now lives in a
maintained library.

## Goal

Every ER integration that the portal syncs with SMART Connect pushes v2
event types, with existing SMART-derived v1 types converted in place, before
2026-10-15. Event and patrol sync into SMART Connect keeps working with no
change in the payload SMART receives.

## Non-goals

- Consolidated configurable-model variants (`cm_variant_mode=consolidate`).
  When several nodes of a configurable model map to the same SMART category,
  the portal keeps today's layout of one ER event type per node. Consolidate
  mode would replace those with one type per group plus a discriminator
  dropdown, changing event type values on every synced site.
- Converting v1 event types that were not created by the SMART sync.
- Fixing the `cryptography` pin that breaks a full `pip-compile` under
  Python 3.11. It is pre-existing and unrelated.
- Any change to the Gundi v2 SMART integration (action runner).

## Approach

Adopt **er-smart-sync** (PyPI, repo `PADAS/earthranger-smart-utils`) as a
dependency and reduce the portal's `sync_integrations` code to glue. The
library is a protocol-based rewrite of the portal's synchronizer: it already
implements v2 event types with ER Choice lists, the SMART < 7.5.3
`update_event_with_smart_data` stopgap, patrol datamodel sync, and the same
`{"observation_type", "gundi_version": "v1", "tracing_context"}` publish
envelope the portal emits today.

Alternatives considered and rejected:

- **Patch the portal's synchronizer to emit v2 directly.** Re-implements the
  choices phase, metaschema compliance and migration handling that the
  library already has and tests.
- **Keep the old synchronizer behind a flag as fallback.** Only useful until
  the sunset, then dead code someone has to remove.

## The choice-value problem (ER -> SMART direction)

v2 event types cannot hold inline enums. The library turns every SMART
LIST/MLIST/TREE option into an ER `Choice` row whose `value` is
`sanitize_choice_value(option_key)`:

```python
re.sub(r"[^A-Za-z0-9]+", "_", key).strip("_").lower()
```

ER's events API returns the bare choice value in `event_details`. SMART
Connect rejects option keys it does not know, and option keys with mixed
case or dotted TREE paths do not survive the sanitizer. The v1 transformer
in cdip-routing (`app/services/transformers.py`, `_resolve_attribute`)
currently passes values through unchanged, so a v2 site would send
`some_tree_leaf` where SMART expects `some.tree.Leaf`.

The sanitize rule is load-bearing: sites already synced with er-smart-sync
have Choice rows under these values, so the rule cannot change and no
reversible encoding is possible. The fix is a reverse lookup at transform
time, against the SMART data model the transformer already loads.

## Design

### 1. smartconnect-client

Add to `smartconnect/models.py` (or a sibling module both libraries import):

- `sanitize_choice_value(key: str) -> str` with the rule above, including the
  91-char-plus-8-hex-hash shortening for long keys. This becomes
  the single definition; er-smart-sync imports it.
- `resolve_option_key(attribute, value: str) -> str` on `DataModel` and
  `ConfigurableDataModel`, given an attribute (as returned by
  `get_attribute(key=...)`) and a value from ER:
  1. If `value` equals an option key exactly, return it.
  2. Otherwise return the single option key whose sanitized form equals
     `value`. TREE options are matched on their dotted leaf path, the same
     keys the library flattens to.
  3. Raise `ValueError` if zero or more than one option matches.

Tests cover exact match, case-folded match, TREE dotted path, no match, and
collision.

### 2. er-smart-sync (release 0.5.0)

**Shared sanitizer.** `er_smart_sync/choices.py` imports
`sanitize_choice_value` from smartconnect-client instead of defining it.
A test asserts the two produce identical output over the existing fixture
set so a future drift is caught.

**Legacy v1 pre-migration.** New field on `EarthRangerConfig`:

```python
migrate_legacy_v1: bool = True  # only consulted when event_type_version == "v2"
```

In `ERSmartSynchronizer.synchronize_datamodel`, when the version is v2 and
the flag is on, fetch v1 event types once per run alongside the existing v2
snapshot. In `push_smart_ca_datamodel_to_earthranger`, after the choices
upsert and after the target event types for the CA (or CA+CM) are built,
before create-or-update:

1. Intersect the target values with the v1 snapshot values. SMART-derived
   values start with the CA UUID (and CM UUID), so a hand-built v1 type can
   never be selected.
2. If the intersection is non-empty, `POST /api/v2.0/activity/eventtypes/migrate/`
   with `{"dry_run": false, "event_types": [...]}` through `ERClient`
   (add a `migrate_event_types` method to earthranger-client if absent, else
   a thin wrapper in the library).
3. Record per-type results. Add `event_types_migrated` and
   `event_types_migrate_errored` to `datamodel_stats`.
4. Any migrate error aborts this CA's push, the same policy as a choice
   upsert error. The next scheduled run retries.
5. Remove the migrated values from the v1 snapshot and add them to the v2
   snapshot so the existing compare-and-patch step sees them.

The compare-and-patch step then rewrites the migrated record to the
library's schema shape, pointing at the shared `dm{8hex}_{attr_key}` Choice
lists. ER's migration creates its own Choice lists under its own names;
those are left active but unreferenced, the same documented state as the
legacy `et{8hex}_` lists.

Inactive v1 types (SMART categories that went inactive) are not migrated.
The library skips inactive categories on v2 and nothing else writes them.

The CLI exposes `--no-migrate-legacy-v1` for operators who want to
dry-run manually first.

Docs: update `docs/concepts/event-type-version.md`, `docs/troubleshooting.md`
("er-smart-sync doesn't wrap this endpoint yet" is no longer true) and the
changelog.

### 3. cdip-routing

In both `_resolve_attribute` call sites in `app/services/transformers.py`,
after the attribute is found in the CM or CA data model:

- For LIST attributes, replace the value with
  `datamodel.resolve_option_key(attribute, value)`.
- For MLIST, apply it per element.
- For TREE, apply it to the leaf path.
- If resolution raises, log at error with the integration, event type and
  attribute, and leave the value unchanged so the existing failure path
  (SMART rejects the observation) stays observable rather than silently
  dropping the field.

Bump the smartconnect-client pin from the 1.7.0 wheel to 1.15.0. That
release requires Python 3.10 and httpx 0.28, so the same PR moves routing
from Python 3.8 to 3.10 and lifts the chain httpx drags along (FastAPI,
Starlette, uvicorn, the OpenTelemetry packages, gundi-client 1.1.0,
gundi-client-v2 3.7.1, redis 6) and drops the unused walrus dependency.
Verified 2026-10-09: the full routing suite passes on that set, every
gundi client method routing calls still exists, and aioredis 2.0.1 works
against Redis 7 with redis-py 6 installed. 3.11 stays out of scope because
aioredis 2.0.1 fails at import there. Existing v1 sites are unaffected by
the lookup because their values match exactly on step 1.

This deploys **before** any site syncs as v2.

### 4. cdip (this repo)

**Dependencies.** `dependencies/requirements.in`: remove the `dasclient` and
`smartconnect_client` GitHub wheels, add `er-smart-sync==0.5.1`. This pulls
`earthranger-client` and `smartconnect-client>=1.14`. A narrow dependency
dry run against the current pins succeeded with no changes to existing
packages.

**`sync_integrations/er_smart_sync.py`** becomes a factory module:

- `build_sync_config(er_integration, smart_integration) -> SyncConfig` maps
  the inbound ER integration (endpoint, token/login, id) and the SMART
  outbound configuration (endpoint, credentials, version,
  `additional["ca_uuids"]`, `additional["configurable_models_lists"]`) to
  the library's config. `event_type_version` comes from a Django setting
  `ER_SMART_SYNC_EVENT_TYPE_VERSION` (env-overridable, default `"v2"`).
  `cm_variant_mode` is always `"split"`. `migrate_legacy_v1` is `True`.
- `build_synchronizer(...)` constructs `ERSmartSynchronizer` with four
  adapters:
  - publisher: `core.utils.get_publisher()` (already matches
    `MessagePublisher`), with `observations_topic` from settings.
  - file storage: `cdip_connector.core.cloudstorage` (already matches
    `FileStorage`).
  - state store: new `RedisStateStore` in `sync_integrations/state.py`
    reading and writing JSON under the existing key
    `er.function.state.{integration_id}` through `sync_integrations.cache`.
    The stored shape (`event_last_poll_at`, `patrol_last_poll_at`) is the
    library's `SyncState`, so last-poll timestamps carry over.
  - tracing: new adapter in `sync_integrations/tracing.py` wrapping
    `core.tracing` (start span, inject headers via
    `instrumentation.build_context_headers()`).

**`sync_integrations/tasks.py`** keeps every task name, the `QueueOnce`
decorators, the soft time limits, the `smartsyncs` queue routing in
settings, and the `sync_er_smart_datamodels -> sync_er_events ->
sync_er_patrols` chain. Each of the three tasks builds a synchronizer and
calls `synchronize_datamodel`, `synchronize_er_events` or
`synchronize_er_patrols`. Database-backed Beat schedules keep working
unchanged.

**Deleted:** the old `ER_SMART_Synchronizer` class and
`tests/test_er_smart_sync.py`. The untracked
`cdip_admin/cdip_admin/earthrangersmart.py` experiment is not part of this
change.

**Tests:**

- `build_sync_config` maps a fixture ER + SMART integration pair to the
  expected `SyncConfig`, including the version setting override.
- `RedisStateStore` round-trips state and reads a pre-existing key written
  in the old format.
- Each task constructs the synchronizer and invokes the matching library
  method (mocked), preserving the chain.

## Data flow after the change

```
SMART Connect --(datamodel)--> er-smart-sync --(migrate v1, choices, v2 types)--> ER
ER --(events, patrols, files)--> er-smart-sync --(gundi v1 envelope)--> PubSub
PubSub --> cdip-routing v1 transformer --(resolve_option_key)--> SMART Connect
```

The synchronizer publishes `gundi_version: "v1"`, so only the v1 transformer
in cdip-routing needs the reverse lookup.

## Rollout

Preconditions:

1. All production ER sites that the portal syncs run ER 2.146.1 or newer,
   the first release with the migrate endpoint. Verify before step 4.
2. smartconnect-client released with `resolve_option_key`.
3. er-smart-sync 0.5.1 released.

Order:

1. Deploy cdip-routing with the reverse lookup and the platform bump. Soak
   on stage before approving prod: confirm spans still reach Cloud Trace
   after the OpenTelemetry jump, and push one SMART event through a v1 and a
   v2 connection. Right after each environment's deploy, flush the SMART data
   model cache in routing's Redis (`cache:smart-ca:*:datamodel`,
   `cache:smart-ca:*:cdm:*`): entries written by the old client have no TTL
   and lack MLIST options, which the reverse lookup now depends on. No
   behaviour change for v1 sites.
2. Deploy the portal, then, before any datamodel sync runs, refresh the
   portal's own SMART data model cache: either run
   `maintain_smart_integrations` and wait for it to finish, or delete
   `cache:smart-ca:*` in the portal's Redis (`REDIS_HOST`, db
   `REDIS_DB`). Entries written by smartconnect-client 1.11 have no TTL
   and predate the CM node `id`, per-node option `config_id` and the CM
   TREE fix; a split-mode push from a stale entry would create event
   types under display-only slugs that get duplicated once the cache
   refreshes. Verify one key first: `GET cache:smart-ca:na:cdm:<uuid>`
   should contain `"id"` under its categories. Also confirm the celery
   worker's `REDIS_DB` is the database the old synchronizer wrote
   `er.function.state.*` to (the charts set `0`), or last-poll state
   does not carry over and the library falls back to its default
   lookback.
3. Trigger `sync_er_smart_datamodels` manually for one ER integration
   and review the run summary (`event_types_migrated`,
   `event_types_skipped_by_conflict` should be zero afterwards). Push one
   test patrol with a mixed-case or TREE option through to SMART.
4. Let Beat run the remaining sites on schedule.

Rollback: redeploy the previous portal image. Migrated v2 types stay v2;
reads are unaffected and v1 writes stop at the sunset regardless, so there
is no data to undo. Setting `ER_SMART_SYNC_EVENT_TYPE_VERSION=v1` is the
only in-place escape hatch and is meaningless after 2026-10-15.

Fixed in er-smart-sync 0.5.1 (the version the portal pins): the 0.5.0
patrol publish path caught every exception as "message too large" and
still advanced `patrol_last_poll_at`, so a Pub/Sub outage that outlasted
the publisher's retries lost those patrols. 0.5.1 skips only an
exception named `MessageTooLargeError` and re-raises everything else, so
the window is retried next run.

Known library follow-ups, not blocking the sunset: `_retry` catches
Celery's `SoftTimeLimitExceeded`, which is why the portal adds a hard
`time_limit`; and `process_event` spans no longer carry the ER event
attributes the old `enrich_span_from_er_event` set.

## Risks

- **A site still on an ER release without the migrate endpoint.** The
  pre-migration step fails for every CA on that site and the run summary
  shows errors. Mitigated by the precondition check.
- **Choice collision inside one attribute** (two option keys that sanitize
  to the same value, e.g. `Lion` and `lion`). The library does not detect
  this; the second upsert lands on the same ER Choice row, so ER only ever
  returns one value. `resolve_option_key` raises on the SMART side and
  routing logs the error with the attribute name. Detecting the collision
  during the push, as a warning in the run summary, is a small follow-up in
  er-smart-sync and is not required for the sunset.
- **Option keys longer than 100 characters.** The library shortens the ER
  value to a 91-character prefix plus a hash suffix. `resolve_option_key` must apply the same
  shortening when computing the sanitized form, so the shared helper in
  smartconnect-client owns that rule as well.
- **Duplicate Choice lists** left by ER's migrator. Cosmetic in the ER
  admin; no functional impact.
- **Types ER cannot persist.** ER's migrator writes each inline enum key
  into its own Choice table unsanitized, and that column is 100 characters.
  A SMART TREE leaf with a dotted path over that length fails the migrate
  call for its whole event type, every run, and the library aborts that CA's
  push each time. The rollout plan checks for this with a dry-run migrate
  against a TREE-bearing tenant before the portal goes live; if any such
  type exists, it needs an ER-side fix or a decision to deactivate the v1
  record and create the v2 type fresh.

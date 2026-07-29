# Pipeline Batch Envelope — Design

**Date:** 2026-07-29
**Status:** Approved design, pending implementation plan
**Scope:** Gundi v2 pipeline — portal API, cdip-routing, gundi-dispatcher-er, gundi-core

## Problem

Every item entering Gundi is processed individually end to end: the portal API
publishes one Pub/Sub message per Gundi object, routing handles one object per
push request, and the EarthRanger dispatcher makes one HTTP request to ER per
observation. For large loads (e.g. a Movebank backfill of millions of records)
this is doubly painful: per-request overhead at every stage, and ER writes each
observation to its database individually — its slowest path.

ER already supports bulk writes: `POST sensors/{type}/{provider_key}/status`
accepts a JSON array (erclient `post_sensor_observation` passes lists through
today), and `POST activity/events` accepts a list (das
`activity/views/events/base.py::EventsView.post` wraps a dict in a list and
serializes with `many=True`; erclient's `post_report` would need a small list
branch).

The batch actually survives most of the pipeline already: action runners POST
lists to the portal API (`SingleOrBulkCreateModelMixin`), and the shredding
happens at exactly one line — the per-item publish loop in
`cdip_admin/api/v2/utils.py::send_observations_to_routing`.

## Decisions made during design

1. **Target load:** primarily large backfills. Regular trickle traffic must not
   gain latency. Therefore no timer-based buffering anywhere — batching is
   *preserved from the source*, never accumulated in the pipeline.
2. **Observability:** "Tier 1" — per-batch delivery *events*, per-object trace
   *rows*. GundiTrace rows are still created per item at ingestion (unchanged)
   and stamped `delivered_at` via one bulk UPDATE per batch. Aggregate-only
   traces (dropping per-object rows) are explicitly out of scope — a separate
   future project.
3. **Stream scope:** observations first; events are phase 2. The mechanism is
   stream-agnostic, but events add erclient work and external_id bookkeeping
   (event_updates/attachments need ER event IDs) better tackled separately.
4. **Batch grouping key:** `(destination integration, provider_key)`. The ER
   sensors endpoint path embeds `provider_key`, so all items in one bulk post
   must share it. The dispatcher always uses `sensor_type='generic'`
   (gundi-dispatcher-er `core/dispatchers.py:323`), so sensor_type is not a
   grouping dimension today. A batch formed at the portal API is homogeneous by
   construction (one API call = one provider); routing's per-destination
   grouping supplies the other half of the key.
5. **Philosophy — envelope as carrier, not semantic unit:** the pipeline's
   message contract becomes "1..N items sharing (provider, stream_type)", with
   batch-of-1 as the degenerate case. Per-item processing semantics are
   preserved: future filters, analyzers, and custom processors are per-item
   functions that shared plumbing maps over an envelope's items. Batches only
   ever **shrink or split** (filter drops items, routing splits per
   destination); nothing ever merges batches, so no component ever needs a
   buffer or a flush timer. Windowed/stateful analyzers consume batched
   high-volume input and emit low-volume derived events as singletons — which
   is fine, because batching only matters where volume is.

## Rejected alternatives

- **Pull-based batching in the dispatcher only:** backlog-adaptive and
  single-component, but the dispatcher deploys as one function per destination
  topic — pull consumption means a subscriber per destination or a consolidated
  multi-topic service (a deployment-model re-architecture). It must also
  re-group interleaved providers per message, and captures none of the upstream
  savings (routing still does a million invocations per backfill).
- **Redis-buffered micro-batching with size-or-age flush:** adds exactly the
  latency window we're avoiding, plus ack-before-write durability problems.

## Section 1 — Batch envelope contract (gundi-core)

New versioned system events alongside (not replacing) the per-item ones:

- **`ObservationsBatchReceived`** — header: `batch_id` (UUID), `provider_id`,
  `stream_type`, `count`, `schema_version`; items: a list of the same per-item
  observation payload model used today (each with its own `gundi_id`). No new
  per-item schema — the envelope is a pure carrier.
- **`ObservationsBatchTransformedER`** — same envelope shape carrying a list of
  the existing `ERObservation` payloads, plus `provider_key` in the header.
- **`ObservationsBatchDelivered`** — see Section 6.

Documented invariants on the models: all items share `(provider,
stream_type)`; batches may be split or shrunk by any stage, never merged.

Pub/Sub attributes: existing attributes plus `batch=true`, so consumers branch
before parsing.

Size: `BATCH_MAX_ITEMS` (default ~500) per envelope keeps messages far below
Pub/Sub's 10 MB limit.

## Section 2 — Portal API

`send_observations_to_routing` (`cdip_admin/api/v2/utils.py:319`): if
`len(observations) >= BATCH_PUBLISH_THRESHOLD` (env var, default ~10), chunk
into envelopes of ≤ `BATCH_MAX_ITEMS` and publish those; otherwise publish
per-item exactly as today. GundiTrace creation at ingestion is untouched.

The threshold doubles as the kill switch: set it unreachable and the platform
reverts to per-item behavior with no redeploys.

## Section 3 — Routing (cdip-routing)

New branch keyed on the `batch=true` attribute:

- **Per-item dedup** using one pipelined Redis round-trip per envelope.
- **One connection/route lookup per envelope** (items share a provider) —
  removes ~499 of every 500 portal/Redis lookups on backfills.
- **Per-item transform** through the existing transformers, unchanged. Items
  failing transformation are dead-lettered individually; the rest continue
  (shrink, never abort).
- **Group by destination**, publish one `ObservationsBatchTransformedER` per
  destination topic with `provider_key` in the header. Observations don't use
  Pub/Sub ordering keys (only `event_update` does), so nothing changes there.

## Section 4 — ER dispatcher (gundi-dispatcher-er)

New handler branch for `ObservationsBatchTransformedER`:

- Build **one** er_client from `(destination integration, provider_key)` —
  both uniform by contract.
- **Idempotency:** before posting, skip items already recorded in the
  per-gundi_id dispatched cache (pipelined reads). This makes envelope
  redelivery safe.
- Post remaining items via `post_sensor_observation(list)` in sub-chunks of
  `ER_BULK_SIZE` (default ~200 — a separate knob from envelope size, tuned to
  what ER digests comfortably per request).
- **Throttling counts items, not messages:** `check_admission` debits N against
  the per-destination observation rate key; if the batch doesn't fit, 429/nack
  the whole envelope (existing push-retry behavior).
- Deployment config review: current function settings (`MAX_INSTANCES=1`,
  `CONCURRENCY=4`, `256Mi`) must be verified under 4 concurrent envelopes of
  `BATCH_MAX_ITEMS`.

## Section 5 — Failure & retry semantics

Rule: **transient failures nack the whole envelope; permanent failures shrink
it.**

- **Transient (ER 5xx, timeout, auth hiccup):** nack → Pub/Sub redelivers.
  Delivered items were recorded in the dispatched cache, so redelivery skips
  them — partial progress survives (chunk 1 delivered + chunk 2 timeout →
  redelivery retries only chunk 2).
- **Permanent (ER 400 on a chunk):** fall back to per-item posts for that
  chunk. Individual successes are recorded as delivered; poison items each
  publish `ObservationDeliveryFailed` (today's per-item event) and are not
  retried. The envelope is acked once every item is either delivered or
  individually failed — no redelivery loops caused by one bad record.
- **Circuit breaker:** `record_success`/`record_distress` fire per ER request
  (not per item) — the breaker measures ER's health, and one bulk request is
  one observation of that health.

## Section 6 — Observability (Tier 1)

- `ObservationsBatchDelivered`: `batch_id`, `data_provider_id`,
  `destination_id`, `gundi_ids`, `count`, `delivered_at`. The portal's
  dispatcher-events consumer handles it with one bulk
  `UPDATE ... SET delivered_at WHERE object_id IN (...) AND destination_id = ...`.
- **`external_id` stays null for batch-delivered observations.** ER's bulk
  sensor response doesn't provide reliable per-item IDs, and nothing downstream
  depends on observation external_ids (unlike events). This is a decision, not
  an accident.
- Failures remain per-item `ObservationDeliveryFailed` — aggregate success plus
  individual visibility into exactly the records that broke.
- One activity-log entry per batch: "Delivered N observations to ⟨destination⟩".

## Section 7 — Rollout order & compatibility

Every consumer handles both message shapes indefinitely. Deploy order makes
each step inert until the last:

1. gundi-core release: envelope schemas + `ObservationsBatchDelivered`.
2. Portal event-consumer handler for `ObservationsBatchDelivered` (dead code
   until the dispatcher emits it).
3. ER dispatcher batch branch (dead code until routing emits envelopes).
4. Routing batch branch (dead code until the portal emits envelopes).
5. Portal API publishes envelopes behind `BATCH_PUBLISH_THRESHOLD` — the single
   on-switch and the kill switch.

Then: enable in dev → real Movebank backfill → compare wall-clock, ER write
load, and trace correctness → stage → prod.

## Section 8 — Testing

- **gundi-core:** schema round-trips for the three new events.
- **Portal:** chunking and threshold behavior in
  `send_observations_to_routing`; consumer bulk trace update.
- **Routing:** per-item dedup, single connection lookup, destination grouping,
  shrink-on-transform-failure.
- **Dispatcher:** sub-chunking, dispatched-cache skip on redelivery, per-item
  fallback on 400, throttling debit of N, envelope ack/nack matrix.
- **E2E (dev):** large Movebank pull through the full pipeline; assert ER row
  counts, `delivered_at` stamped on all traces, one batch activity-log entry,
  and correct handling of a deliberately poisoned record in the batch.

## Phase 2 (out of scope here, noted for continuity)

Events batching: add a list branch to erclient `post_report` (das already
accepts lists; all-or-nothing 400 semantics make per-item fallback mandatory),
and map per-item ER event IDs from the ordered bulk response into the
dispatched cache so `event_update`/`attachment` messages keep working.

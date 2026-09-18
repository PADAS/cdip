# Push API Key `whoami` Endpoint — Design

**Date:** 2026-09-18
**Status:** Approved design, pending implementation plan
**Scope:** Gundi Portal backend (`cdip`), v2 only

## Problem

Push integrations identify themselves to Gundi with a single API key, passed in a
header or query-string parameter. The key is the *only* identity on the request. A
data provider that serves several Gundi customers must keep its own mapping of
"which key belongs to which customer's integration," and Gundi gives it no way to
check that mapping.

The consequence is that a wrong key is not an error. Whatever key is presented,
the data is accepted and written into the integration that key is bound to. A
provider mixup produces a clean, successful, cross-tenant write that is only
noticed when a human sees data in the wrong place.

## Goal

Give the holder of a push API key a self-service way to ask Gundi "which
integration does this key belong to, where does its data go, and is data
arriving?" — so that:

1. providers can audit their own key store at onboarding and on demand; and
2. providers obtain the integration id needed to use the **existing** echo-back
   check on push payloads, which turns a swapped key into a rejected request.

## Decisions taken during design

| Question | Decision |
|---|---|
| Primary outcome | Make the key→integration mapping self-verifiable (a `whoami` endpoint). Loud rejection of mismatches is obtained for free via the existing echo-back check, not new enforcement. |
| Disclosure level | Identity + routing summary **including destination base URLs** + delivery telemetry. |
| Key cardinality | One key ⇄ one integration. Multiple integrations per key are not supported and will not be. Response is a single object, not a list. |
| Volume telemetry | Live count on demand, backed by a new composite index on `GundiTrace`, cached 60s, gracefully degraded on timeout. |
| Header-spoofing hazard | Tracked as a **separate, higher-priority task** ([GUNDI-5736](https://allenai.atlassian.net/browse/GUNDI-5736)); not a dependency of this work (see *Exposure*). |
| Portal UI snippet | Filed separately against the front-end repo (`gundi-portal`); not in this spec. |

## Current state (verified in code)

- **Auth path.** `sensors.api.<env>.gundiservice.org` routes to the portal through
  Kong's `key-auth` plugin (`serca-helm-charts/charts/gundi/admin-portal/templates/service.yaml`,
  service `admin-portal-sensors`). Kong maps the key to a consumer named
  `integration:<uuid>` and injects `X-Consumer-Username`.
- **Consumer provisioning.** `integrations/utils.py:create_api_consumer` /
  `create_api_key` mint exactly one consumer and one key per integration.
- **Request binding.** `api/v2/middleware.py:ApiIntegrationIdMiddleware` sets
  `request.integration_id` from `X-Consumer-Username` (or, legacy, from
  `integration_ids[0]` in a base64 `X-Consumer-Custom-Id`).
- **Echo-back already exists.** `api/v2/serializers.py:1281-1305`: if a push
  payload includes an `integration` field, it is validated against
  `request.integration_id` and rejected with
  *"Your API Key is not authorized for the integration_id"* on mismatch. It is
  opt-in and undiscoverable today.
- **Existing key surface.** `GET /v2/integrations/{id}/api-key` returns the key
  but requires a portal *user* login; the provider cannot call it.
- **Telemetry sources.**
  - `IntegrationStatus.status` / `status_details` are maintained
    (`models/v2/services.py:calculate_integration_status`).
  - `IntegrationStatus.last_delivery` is **dead**: declared at
    `models/v2/models.py:600`, shown in admin, never written anywhere. Do not use.
  - `GundiTrace.created_at` (received) and `GundiTrace.delivered_at` (written by
    `event_consumers/dispatcher_events_consumer.py:98`) are live and per-record.
  - `IntegrationMetrics.data_frequency_minutes` is a nightly rollup
    (`0113_metrics_schedule.py`: 00:00 daily).
  - `GundiTrace` has indexes on `created_at` and `updated_at` only; nothing on
    `data_provider_id`.
- **Cache.** No `CACHES` block in production settings (only
  `local_settings.py` defines LocMemCache). Redis is reachable through
  `core/cache.py:get_redis_db()`.

## Endpoint contract

### `GET /v2/whoami/`

Served by the portal's Django URLconf; reached by providers at
`https://sensors.api.<env>.gundiservice.org/v2/whoami/` with the same `apikey`
they use to push. Because the Kong consumer is shared across ingress styles, the
same key a webhook provider posts with also works here.

Named `/v2/whoami/` (a plain path in `api/v2/urls.py`) rather than an action on
the `integrations` router: that router is OIDC/user-scoped with org-role
permission classes, and hanging a key-authenticated action off it invites later
reuse of the wrong permission class.

**Authentication.** `authentication_classes = []` (mirrors `ObservationsView`).
A new permission class `HasIntegrationApiKey` in `api/v2/permissions.py` grants
access iff `request.integration_id` is set. A logged-in portal user with no
consumer header is denied.

**Responses.**

| Status | When | Body |
|---|---|---|
| 200 | Consumer resolves to an existing integration | Payload below |
| 401 | No `request.integration_id` | `{"detail": "This API Key isn't associated with an integration."}` (existing wording) |
| 404 | Consumer names an integration that no longer exists | `{"detail": "Cannot find the integration associated with this API Key."}` (existing wording) |

Missing/invalid key never reaches Django — Kong `key-auth` returns 401 first.

**200 payload.**

```json
{
  "integration": {
    "id": "17e7a1e0-168b-4f68-9392-35ec29222f13",
    "name": "Savannah Tracking – Mara Conservancy",
    "type": { "value": "savannah_tracking", "name": "Savannah Tracking" },
    "base_url": "https://…",
    "enabled": true,
    "owner": { "id": "…", "name": "Mara Conservancy" }
  },
  "destinations": [
    { "id": "…", "name": "Mara ER", "type": "earth_ranger", "base_url": "https://mara.pamdas.org" }
  ],
  "push_endpoints": {
    "observations": "https://sensors.api.gundiservice.org/v2/observations/",
    "events": "https://sensors.api.gundiservice.org/v2/events/",
    "webhook": "https://…"
  },
  "delivery": {
    "status": "healthy",
    "status_details": "",
    "last_received_at": "2026-09-17T14:32:11Z",
    "last_delivered_at": "2026-09-17T14:32:40Z",
    "observations_last_24h": 412,
    "events_last_24h": 7,
    "delivered_last_24h": 419,
    "counts_as_of": "2026-09-17T15:01:02Z",
    "counts_unavailable": false,
    "data_frequency_minutes": 10,
    "data_frequency_as_of": "2026-09-17T00:00:00Z"
  }
}
```

Field sources and rules:

- `integration.*` — `Integration` row; `type` is `IntegrationType.value`/`name`;
  `owner` is the `Organization`.
- `destinations` — `Integration.destinations` (derived from routing rules). Empty
  list, not an error, when the provider is on no route.
- `push_endpoints.observations` / `events` — built from a new setting
  `SENSORS_API_BASE_URL` (per environment). `webhook` is present **only** when
  `integration.type.webhook` exists. The webhook host was not found in the helm
  charts read during design; **confirm its source during implementation** and
  read it from settings the same way.
- `delivery.status` / `status_details` — `IntegrationStatus`.
- `delivery.last_received_at` — `MAX(GundiTrace.created_at)` for this provider.
  Taken from the 24h window query; if that window is empty, from a fallback
  `ORDER BY created_at DESC LIMIT 1`.
- `delivery.last_delivered_at`, `*_last_24h` — the 24h window query below.
  Counts **include** rows with `is_duplicate = TRUE`: the provider is comparing
  against what it sent, not what survived dedup.
- `delivery.counts_as_of` — when the cached window query was executed.
- `delivery.counts_unavailable` — `true` (with the four count/`last_delivered_at`
  fields `null`) when the window query timed out. Identity fields are never
  affected by the telemetry query.
- `delivery.data_frequency_minutes` / `data_frequency_as_of` — most recent
  `IntegrationMetrics` row and its `created_at`; both `null` when none exists.
  Kept separate from the live counts because its freshness is a day, not a
  minute.
- Disabled integrations return the full payload with `"enabled": false`. A
  provider posting to a disabled integration must see that, not a 403 that looks
  like a bad key.
- The API key itself, or any fingerprint of it, is **never** included.

## Data layer

### New index

```python
# integrations/migrations/NNNN_gunditrace_provider_created_idx.py
atomic = False
operations = [
    AddIndexConcurrently(
        model_name="gunditrace",
        index=models.Index(
            fields=["data_provider", "created_at"],
            name="gunditrace_provider_created_idx",
        ),
    ),
]
```

Costs acknowledged: `integrations_gunditrace` is large, so the concurrent build
runs long in prod, and the index adds write overhead to the highest-volume insert
path in the system. Benefit beyond this endpoint: the nightly
`integrations/metrics.py:calculate_data_frequency` query filters the same two
columns and currently relies on the `created_at` index alone.

**Prod runbook note:** apply during a low-traffic window; monitor `pg_stat_progress_create_index`;
if the build fails it leaves an `INVALID` index that must be dropped before retry.

### Window query

One pass returns everything the `delivery` block needs:

```sql
SELECT object_type,
       COUNT(*)            AS received,
       COUNT(delivered_at) AS delivered,
       MAX(created_at)     AS last_received_at,
       MAX(delivered_at)   AS last_delivered_at
FROM integrations_gunditrace
WHERE data_provider_id = %s
  AND created_at >= NOW() - INTERVAL '24 hours'
GROUP BY object_type;
```

Executed under a per-statement `SET LOCAL statement_timeout` (default 2000 ms,
setting `WHOAMI_COUNTS_TIMEOUT_MS`). `OperationalError` from the timeout is
caught and mapped to `counts_unavailable: true`.

Implementation lives in a small service module, `api/v2/whoami.py` (or
`integrations/services/whoami.py`), with one function that returns the
`delivery` dict from a provider id. The view stays thin.

### Cache

Redis via `core.cache.get_redis_db()`, key `whoami:delivery:<integration_id>`,
TTL 60 s, value = JSON of the `delivery` block minus `status`/`status_details`
(those are cheap and read live). Django's cache framework is deliberately not
used: with no production `CACHES` block it would silently be per-pod LocMem.
Footprint is a few hundred bytes per active provider — negligible, but the prod
Redis instance has filled before, so the TTL stays short.

## Exposure and abuse

- **No enumeration surface.** The endpoint takes no identifier; it describes only
  the key's own integration.
- **Rate limiting.** Kong `rate-limiting` plugin on this route, keyed by
  consumer, 60/min. Cheap endpoint, but a stolen key should not get an unlimited
  "whose key is this?" oracle. Configured in the helm chart alongside
  `keyauth-plugin.yaml`.
- **Pre-existing header-trust hazard (tracked separately).**
  `ApiIntegrationIdMiddleware` trusts inbound `X-Consumer-*` headers. Both portal
  hosts serve the same URLconf, and nothing found in the Kong configuration
  (`sintegrate-kong/transforms.yaml` only *adds* a header) demonstrably strips
  client-supplied headers of those names. This has **not** been verified against
  a running Kong. If exploitable, the serious half is the existing **write**
  path (`serializers.py:1299` picks the target integration from
  `request.integration_id`), not this read endpoint. Action: verify as its own
  task — [GUNDI-5736](https://allenai.atlassian.net/browse/GUNDI-5736); if confirmed, strip `X-Consumer-*` and `X-Credential-*` from inbound
  requests at the edge on every route. This spec does not depend on the outcome.
- **Logging.** Log `integration_id`, never the key. The existing exception
  handler already attaches `integration_id` (`api/v2/exception_handler.py:59`).

## Discoverability

1. **Docs — the real payoff.** Add a page to `gundi-help-docs` presenting the
   pair as the recommended pattern: call `whoami` once at setup, store the
   returned `integration.id` alongside your customer record, and send it as the
   `integration` field on every push. From then on a swapped key is a 400 (the
   existing check at `serializers.py:1281`) instead of a silent cross-tenant
   write. Include a copy-paste `curl`.
2. **Schema.** Annotate the view with `drf_yasg` so it appears in `/v2/docs`.
3. **Portal UI snippet — separate follow-on, front-end repo.** The v2 key
   reaches the UI via `GET /v2/integrations/{id}/api-key`; the key-revealing
   Django views in this repo (`integrations/views.py:79,96,1053,1777`) are v1
   only. A "verify this key" snippet beside the revealed key belongs in
   `gundi-portal`.

## Out of scope (follow-ons)

- Per-integration "strict mode" requiring the `integration` echo field.
- Key rotation / revocation.
- v1 sensors-API (`cdip-api`) parity, including multi-integration consumers.
- Portal UI snippet (front-end repo).
- Header-stripping hardening at the Kong edge (separate, higher priority) — GUNDI-5736.

## Testing

New file `cdip_admin/api/v2/tests/test_whoami_api.py`. Kong is simulated as in
existing tests by passing `HTTP_X_CONSUMER_USERNAME` (`conftest.py:2314`,
`test_messages_api.py`). Existing provider/connection fixtures are reused.

**Contract**
- Valid consumer → 200; `integration.id`, `owner`, `type`, `enabled` populated.
- `destinations` reflects routing rules: two-destination provider; provider on
  no route → `[]`.
- Disabled provider → 200 with `"enabled": false`.
- No consumer header → 401. Consumer for a deleted integration → 404.
- Authenticated portal user, no consumer header → 401 (guards against a later
  swap to org-role permission classes).
- `push_endpoints.webhook` present only for a type with an `IntegrationWebhook`.

**Telemetry** (create `GundiTrace` rows directly)
- Mixed observations/events, some delivered → per-type received, delivered
  count, `last_received_at`, `last_delivered_at`.
- Rows older than 24h excluded from counts but drive `last_received_at` through
  the fallback query.
- Duplicate traces counted in received.
- Window query raises `OperationalError` → 200, count fields `null`,
  `counts_unavailable: true`, identity intact.

**Cache**
- Second call within TTL does not re-run the window query (patch
  `get_redis_db`, as `mock_kong_consumers_api_requests` patches externals at
  `conftest.py:2862`).

**Migration**
- No dedicated test; a `pytest` run on a fresh DB proves it applies.
  Concurrent-build behaviour is covered by the prod runbook note above.

## Files touched (expected)

- `cdip_admin/api/v2/urls.py` — add `path("whoami/", …)`.
- `cdip_admin/api/v2/views.py` — `WhoAmIView`.
- `cdip_admin/api/v2/serializers.py` — `WhoAmISerializer` (+ nested).
- `cdip_admin/api/v2/permissions.py` — `HasIntegrationApiKey`.
- `cdip_admin/api/v2/whoami.py` — delivery telemetry service + cache.
- `cdip_admin/integrations/migrations/NNNN_gunditrace_provider_created_idx.py`.
- `cdip_admin/cdip_admin/settings.py` — `SENSORS_API_BASE_URL`,
  `WHOAMI_COUNTS_TIMEOUT_MS`.
- `cdip_admin/api/v2/tests/test_whoami_api.py`.
- `serca-helm-charts` — rate-limiting plugin on the route (separate PR).
- `gundi-help-docs` — provider-facing page (separate PR).

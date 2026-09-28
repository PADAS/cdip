# Counting processed items from Cloud Trace spans

How to count observations, events, and other items flowing through Gundi in a
given timeframe by querying Cloud Trace spans in BigQuery.

Last verified: 2026-09-14.

## Where the spans live

Every Gundi service (portal, cdip-routing, ER dispatcher, SMART dispatcher)
exports 100% of its spans to Cloud Trace with the OpenTelemetry
`CloudTraceSpanExporter`. No sampler is configured. The exporter is built with
no `project_id`, so spans land in the project the workload **runs in**, not the
project named in the `GCP_PROJECT_ID` setting.

| Stack | Runtime project | Spans land in |
|---|---|---|
| Gundi v1 (legacy `cdip-prod01` GKE cluster) | `cdip-78ca` | `cdip-78ca` |
| Gundi v2 prod (GKE `sintegrate-4bb07e9c`, Cloud Run, Cloud Functions) | `cdip-prod1-78ca` | `cdip-prod1-78ca` |
| Gundi v2 stage | `cdip-stage-78ca` | `cdip-stage-78ca` |
| Gundi v2 dev | `cdip-dev-78ca` | `cdip-dev-78ca` |

Cloud Trace stores spans in an **observability bucket** named `_Trace`
(location `us`, fixed 30-day retention, no storage charge). Each prod project
has had this bucket since 2025-07-01. On 2026-09-14 we created a **linked
BigQuery dataset** on top of it in both prod projects:

| Project | BigQuery view |
|---|---|
| v2 prod | `cdip-prod1-78ca.trace_spans._AllSpans` |
| v1 prod | `cdip-78ca.trace_spans._AllSpans` |

The same queries work against either view. Swap the project name.

To add stage or dev:

```bash
gcloud beta observability buckets datasets links create \
  projects/PROJECT/locations/us/buckets/_Trace/datasets/Spans/links/trace_spans \
  --dataset=Spans --bucket=_Trace --location=us --project=PROJECT
```

Requires the Observability API enabled and `roles/observability.editor`.

### Why not a trace sink

Cloud Trace "trace sinks" (the export-to-BigQuery feature) were deprecated on
2026-02-18, creation was blocked on 2026-08-31, and they shut down on
2027-02-18. Attempting to create one returns `501 UNIMPLEMENTED`. The linked
dataset is Google's replacement.

A legacy sink `cdip-traces-sink` still exists in `cdip-78ca`, created in
November 2022. It writes to `cdip-78ca.cdip_traces.cloud_trace` (day-partitioned,
no expiration, ~26.6 billion rows / 13.9 TB logical / 1.6 TB physical as of
2026-09-14). That table has a different, older schema
(`span.displayName.value`, `span.attributes.attributeMap.<key>`) and is the only
place with more than 30 days of v1 history. It stops receiving data on
2027-02-18.

## Data latency

Measured on 2026-09-14 in `cdip-prod1-78ca` over ~600k spans from the previous
two hours:

| Measure | Value |
|---|---|
| Span start to Cloud Trace receipt, p50 | 2 s |
| Span start to Cloud Trace receipt, p95 | 4 s |
| Span start to Cloud Trace receipt, p99 | 5 s |
| Newest span visible in BigQuery vs. wall clock | 11 s behind |

In practice the view is near real time. Three things still make the trailing
edge incomplete:

- **Exporter batching.** Each service uses a `BatchSpanProcessor` with the
  default 5-second flush interval, and a span is only exported after it ends.
  A long-running span (a batch dispatch with hundreds of items) shows up when
  it finishes, timestamped with its start.
- **Hour truncation.** Any query grouping by `TIMESTAMP_TRUNC(start_time, HOUR)`
  reports a partial current hour. Filter to completed hours when comparing.
- **Retention.** The bucket keeps 30 days. Anything older is gone unless you
  roll it up (see "Keeping history" below).

Treat the last one to two minutes as provisional and everything older as
complete. The `receive_time` column records when Cloud Trace accepted the span
if you need to reason about lag yourself.

## Which span is one item

Each stage emits a differently named span per item. Pick the stage that matches
the question.

| Question | Span name | One span per | Key attributes |
|---|---|---|---|
| Items received by the portal API | `gundi_api.process_observation`, `.process_event`, `.process_event_update`, `.process_attachment`, `.process_text_message` | item | `integration_id`, `integration_name`, `integration_type`, `observation_type`, `external_source_id`, `is_duplicate` |
| System events processed by routing (v2) | `routing_service.process_observations_event` | PubSub event (may be a batch envelope) | `system_event_type`, `observation_type` |
| Items processed by routing (v1 path) | `routing_service.process_observation` | item | `environment` |
| Routing fan-out decisions | `routing_service.transform_and_route_observation` | item | `destinations_qty`, `destinations`, `is_discarded` |
| Items delivered to EarthRanger, one at a time | `er_dispatcher.dispatch_transformed_observation` | item **per destination** | `destination_id`, `is_dispatched_successfully`, `error` |
| Items delivered to EarthRanger in a batch envelope | `er_dispatcher.dispatch_observations_batch` | batch | `destination_id`, `batch_count`, `pending_count`, `delivered_count` |
| Items delivered to SMART | `smart_dispatcher.dispatch_transformed_observation` | item per destination | `destination_id`, `is_dispatched_successfully`, `is_throttled` |

Three traps:

1. **Duplicates are counted at intake.** On 2026-09-14 roughly two thirds of
   `gundi_api.process_observation` spans carried `is_duplicate = true`. Decide
   whether "items received" includes them.
2. **Dispatch spans are per destination.** An observation routed to three ER
   sites produces three dispatch spans.
3. **Batch envelopes are one span for many items.** For the ER batch path,
   `SUM(delivered_count)` is the item count, not `COUNT(*)`.

All attributes are stored as JSON strings, including booleans and integers.
Read them with `JSON_VALUE(attributes.key)` and cast as needed.

## Sample queries

Each query below was run against `cdip-prod1-78ca` on 2026-09-14. A 24-hour
window scans about 1.4 GB, so a full 30-day window is roughly 40 GB, or about
$0.25 at on-demand BigQuery pricing. Running the same SQL from the console's
Observability Analytics page is free.

### (a) Items delivered per hour and destination

Combines the single-item and batch ER paths into one delivered count. Add the
SMART span to the `IN` list to include SMART destinations.

```sql
SELECT
  TIMESTAMP_TRUNC(start_time, HOUR)                        AS hour,
  JSON_VALUE(attributes.destination_id)                    AS destination_id,
  COUNTIF(name = 'er_dispatcher.dispatch_transformed_observation'
          AND JSON_VALUE(attributes.is_dispatched_successfully) = 'true')
                                                           AS single_items_delivered,
  SUM(IF(name = 'er_dispatcher.dispatch_observations_batch',
         SAFE_CAST(JSON_VALUE(attributes.delivered_count) AS INT64), 0))
                                                           AS batch_items_delivered,
  COUNTIF(name = 'er_dispatcher.dispatch_transformed_observation'
          AND JSON_VALUE(attributes.is_dispatched_successfully) IS NULL)
                                                           AS single_items_failed
FROM `cdip-prod1-78ca.trace_spans._AllSpans`
WHERE start_time >= TIMESTAMP('2026-09-13 00:00:00')
  AND start_time <  TIMESTAMP('2026-09-14 00:00:00')
  AND name IN ('er_dispatcher.dispatch_transformed_observation',
               'er_dispatcher.dispatch_observations_batch')
GROUP BY hour, destination_id
ORDER BY hour, destination_id;
```

Add `single_items_delivered + batch_items_delivered` in an outer query for a
single total. To turn `destination_id` into a name, join to the portal
database's `integrations_integration` table, or look it up in the Gundi portal.

### (b) Items received per hour

Counts what reached the portal API, split by item type, with duplicates shown
separately so you can subtract them.

```sql
SELECT
  TIMESTAMP_TRUNC(start_time, HOUR)                           AS hour,
  COUNTIF(name = 'gundi_api.process_observation')             AS observations,
  COUNTIF(name = 'gundi_api.process_event')                   AS events,
  COUNTIF(name = 'gundi_api.process_event_update')            AS event_updates,
  COUNTIF(name = 'gundi_api.process_attachment')              AS attachments,
  COUNTIF(name = 'gundi_api.process_text_message')            AS text_messages,
  COUNT(*)                                                    AS total_received,
  COUNTIF(JSON_VALUE(attributes.is_duplicate) = 'true')       AS duplicates,
  COUNT(*) - COUNTIF(JSON_VALUE(attributes.is_duplicate) = 'true')
                                                              AS unique_items
FROM `cdip-prod1-78ca.trace_spans._AllSpans`
WHERE start_time >= TIMESTAMP('2026-09-13 00:00:00')
  AND start_time <  TIMESTAMP('2026-09-14 00:00:00')
  AND name LIKE 'gundi_api.process_%'
GROUP BY hour
ORDER BY hour;
```

For a per-hour count of what routing handled instead, replace the `name` filter
with `name = 'routing_service.process_observations_event'`. Note that in v2 a
single routing event can carry a batch of observations, so that number is
smaller than the portal intake count.

### (c) Items received per hour and integration type

`integration_type` is the provider slug (`vectronic`, `movebank`,
`spidertracks`, ...) and is set on every portal intake span.

```sql
SELECT
  TIMESTAMP_TRUNC(start_time, HOUR)                        AS hour,
  JSON_VALUE(attributes.integration_type)                  AS integration_type,
  COUNT(*)                                                 AS items_received,
  COUNTIF(JSON_VALUE(attributes.is_duplicate) = 'true')    AS duplicates,
  COUNT(DISTINCT JSON_VALUE(attributes.integration_id))    AS active_integrations
FROM `cdip-prod1-78ca.trace_spans._AllSpans`
WHERE start_time >= TIMESTAMP('2026-09-13 00:00:00')
  AND start_time <  TIMESTAMP('2026-09-14 00:00:00')
  AND name LIKE 'gundi_api.process_%'
GROUP BY hour, integration_type
ORDER BY hour, items_received DESC;
```

Swap `integration_type` for `integration_id` or `integration_name` to break
down by individual connection, or add `JSON_VALUE(attributes.observation_type)`
to separate observations (`obv`) from events (`ev`).

### Same questions against v1

Replace the project in the `FROM` clause:

```sql
FROM `cdip-78ca.trace_spans._AllSpans`
```

v1 has no `gundi_api.*` spans. Its intake is counted by
`routing_service.process_observation` and its delivery by
`er_dispatcher.dispatch_transformed_observation`. For v1 history older than 30
days, query the legacy sink table with the old schema:

```sql
SELECT
  TIMESTAMP_TRUNC(span.startTime, HOUR)               AS hour,
  span.attributes.attributeMap.destination_id         AS destination_id,
  COUNTIF(span.attributes.attributeMap.is_dispatched_successfully = 'true')
                                                      AS items_delivered
FROM `cdip-78ca.cdip_traces.cloud_trace`
WHERE _PARTITIONTIME BETWEEN TIMESTAMP('2026-06-01') AND TIMESTAMP('2026-06-30')
  AND span.displayName.value = 'er_dispatcher.dispatch_transformed_observation'
GROUP BY hour, destination_id
ORDER BY hour, destination_id;
```

Always filter on `_PARTITIONTIME` there. The table is 13.9 TB and an
unfiltered scan costs about $85.

## Keeping history beyond 30 days

The `_Trace` bucket retention cannot be changed. To keep counts, schedule a
BigQuery query that runs hourly or daily and appends aggregates to a small
table you own, for example:

```sql
INSERT INTO `cdip-prod1-78ca.gundi_metrics.hourly_span_counts`
SELECT
  TIMESTAMP_TRUNC(start_time, HOUR)                        AS hour,
  name                                                     AS span_name,
  JSON_VALUE(attributes.integration_type)                  AS integration_type,
  JSON_VALUE(attributes.destination_id)                    AS destination_id,
  COUNT(*)                                                 AS spans,
  COUNTIF(JSON_VALUE(attributes.is_duplicate) = 'true')    AS duplicates,
  COUNTIF(JSON_VALUE(attributes.is_dispatched_successfully) = 'true')
                                                           AS dispatched_ok,
  SUM(SAFE_CAST(JSON_VALUE(attributes.delivered_count) AS INT64))
                                                           AS batch_items_delivered
FROM `cdip-prod1-78ca.trace_spans._AllSpans`
WHERE start_time >= TIMESTAMP_TRUNC(TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY), DAY)
  AND start_time <  TIMESTAMP_TRUNC(CURRENT_TIMESTAMP(), DAY)
  AND (name LIKE 'gundi_api.process_%'
       OR name LIKE 'routing_service.process_%'
       OR name LIKE 'er_dispatcher.dispatch_%'
       OR name LIKE 'smart_dispatcher.dispatch_%')
GROUP BY hour, span_name, integration_type, destination_id;
```

That table would grow by a few thousand rows a day and cost cents to store and
query. This is not set up yet.

## Accuracy caveats

- The `BatchSpanProcessor` queue holds 2048 spans by default and drops silently
  when full, so counts undercount during load spikes.
- Cloud Trace has no per-span-name metric in Cloud Monitoring. The only metric
  is `cloudtrace.googleapis.com/billing/spans_ingested` for the whole project,
  useful for sanity-checking totals (v2 prod ingests about 17 million spans a
  day, v1 prod about 22 million).
- Roughly 40% of all spans are auto-instrumented `HTTP GET` / `HTTP POST`
  client spans. Always filter on `name` so they don't inflate counts.
- The `resource.attributes` column only carries `gcp.project_id`; the exporter
  version in use does not record `service.name`. Use the span name prefix
  (`gundi_api.`, `routing_service.`, `er_dispatcher.`, `smart_dispatcher.`) to
  tell services apart.

## Access

Querying needs `roles/bigquery.user` on the project plus read access to the
`_Trace` bucket (`roles/observability.viewer` or Cloud Trace User). Use the
`chrisdo@earthranger.com` identity for all these projects. From the CLI:

```bash
export CLOUDSDK_CORE_ACCOUNT=chrisdo@earthranger.com
bq query --project_id=cdip-prod1-78ca --use_legacy_sql=false --dry_run < query.sql   # cost check
bq query --project_id=cdip-prod1-78ca --use_legacy_sql=false --format=pretty < query.sql
```

## References

- [Export trace spans with sinks deprecation](https://docs.cloud.google.com/stackdriver/docs/deprecations/export-spans-with-sinks)
- [Trace storage overview](https://docs.cloud.google.com/trace/docs/storage-overview)
- [Migrate to Analytics](https://docs.cloud.google.com/trace/docs/analytics-migrate)
- [Analyze trace data with BigQuery](https://docs.cloud.google.com/trace/docs/analytics-query-linked-dataset)
- [Create observability buckets](https://docs.cloud.google.com/stackdriver/docs/observability/create-observability-buckets)
- [Trace release notes](https://docs.cloud.google.com/trace/docs/release-notes)

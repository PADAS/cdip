# Typeahead Reference Data — Contract Extension Design

**Date:** 2026-08-27
**Status:** Approved design
**Extends:** the reference-data design in
`gundi-integration-cmore/docs/superpowers/specs/2026-07-31-reference-data-config-ui-design.md`
(referenced, not edited — this document is the authority for the `search` extension only).
**Platform state this builds on:** cdip accepts the `"reference"` action type and
authorizes execute-proxy calls for config editors (PR #461, merged);
gundi-portal's `ReferenceSelectWidget` implements the base contract (merged).

## Problem

The `gundi:reference` contract populates config-form dropdowns from reference
actions, but its `params` support only literals and `{"$data": ...}` references
to other form fields. There is no way to pass the user's typed text, so any
vocabulary too large to enumerate — iNaturalist taxa (millions), projects by
name, place names — cannot be offered as a dropdown. The motivating consumer is
the iNaturalist integration's `taxa` field, where the upstream API already has
an ideal endpoint (`GET /v1/taxa/autocomplete?q=`) that the contract cannot
reach.

## Decision

Add an optional top-level `search` block to the `gundi:reference` annotation.
When present, the portal widget becomes input-driven (typeahead): the user's
typed text is sent as one named query param alongside the existing resolved
`params`. Considered and rejected:

- **`{"$search": true}` as a params value** (symmetric with `$data`): an old
  widget would send the literal marker object as the param value, producing a
  422 and a warning badge on every menu open. The top-level key degrades
  cleanly instead — old widgets ignore unknown annotation keys entirely.
- **A dedicated autocomplete endpoint or new action type**: recreates the
  parallel-invocation-path problems the original RFC rejected (separate auth
  story, no activity logging, no registration-time discoverability).

## Section 1 — The `search` annotation block

```json
"taxa": {
  "items": {
    "gundi:reference": {
      "action": "list_taxa",
      "target": "self",
      "params": {},
      "search": { "param": "q", "min_chars": 2 },
      "allow_free_text": true
    }
  }
}
```

- **`param`** (required, string): the reference action's query-model field that
  receives the typed text. It is sent in `config_overrides` merged with the
  resolved `params`; declaring the same name in both is a spec violation (the
  drift tests in integration repos should assert `search.param ∉ params`).
- **`min_chars`** (optional, integer, default `2`): the widget does not fetch
  while the input is shorter than this.
- Debounce interval, spinner copy, and cache sizing are widget implementation
  details, deliberately not part of the contract.
- The `search` block composes with `$data` params (e.g. search within a
  selected parent). The existing rule that an empty `$data` dependency blocks
  fetching still applies, regardless of typed text.

### Runner convention

The search param SHOULD be declared **optional** on the reference action's
query model. When it is absent or empty, the action returns either a sensible
capped default page (`truncated: true`) or empty `options` — never a 422. This
convention is what makes the extension backward compatible: an old widget that
ignores the `search` key fetches once on menu open with no search text and gets
a working (non-typeahead) dropdown or an empty list, not an error.

## Section 2 — Portal widget behavior (gundi-portal)

`ReferenceSelectWidget` changes only when `search` is present in the
annotation; without it, behavior is byte-for-byte today's.

With `search` declared:

- **No auto-fetch** on mount or menu open. The menu placeholder reads "Type at
  least N characters to search" (localized), N = `min_chars`.
- **Input-driven fetch**: input changes at or above `min_chars` debounce
  (~300 ms) into a fetch whose `config_overrides` are
  `{...resolvedParams, [search.param]: inputText}`.
- **Latest-query-wins**: responses for superseded queries are discarded; only
  the response matching the current input renders.
- **Caching**: client-side cache keyed on
  `(integration_id, action, resolved params, query)`, honoring
  `cache_ttl_seconds` — the same cache as today with the query folded into the
  key.
- **Unchanged**: free-text entry (`allow_free_text`), cold-start loading
  escalation copy, provider-target (`target: "provider"`) union-and-dedupe,
  fetch-failure degradation to plain text with retry.
- **Saved-value labels (known gap, deferred)**: because there is no menu-open
  fetch, a stored opaque ID renders as the raw ID with no label and no
  warning badge (the badge remains gated on a successful fetch, which will not
  have happened). A future `resolve` block — an annotation-declared lookup of
  options by stored value — is the designed fix; it is out of scope here.

## Section 3 — cdip (this repo): no code change

The execute proxy (`ActionTriggerView.execute`) already passes
`config_overrides` through verbatim, and PR #461 authorizes reference-action
execution for config editors. Typeahead traffic is just more frequent execute
calls; the widget's debounce, `min_chars` gate, and TTL cache bound the rate.
No server-side rate limiting is added now — revisit only if runner load or
activity-log volume shows a real problem. This document lives in cdip because
the platform owns the contract; the implementation work lands in gundi-portal
and the integration repos.

## Section 4 — Proving consumer: iNaturalist `list_taxa`

In `gundi-integration-inaturalist` (follows the patterns of its merged
reference-data PR #29):

- **Query model**: `ListTaxaQuery(ReferenceActionConfiguration)` with
  `q: Optional[str] = None`.
- **Handler**: `action_list_taxa` wraps pyinaturalist
  `get_taxa_autocomplete(q=...)` (pinned 0.19.0 exports it; public endpoint,
  no auth). Option shape: `value` = `str(taxon id)`; `label` =
  `"Common name (Scientific name)"`, falling back to the scientific name when
  no common name; `description` = rank. Empty/absent `q` returns
  `options: []`, `truncated: true` (the taxa vocabulary is too large for a
  meaningful default page).
- **`taxa` field reshape**: `Optional[List[str]]` in the schema (a dropdown
  attaches to array items, not to one comma-string field). The existing
  pre-validator inverts: it now coerces legacy comma-separated strings (and
  scalar leftovers) into the list shape. The datasource keeps its
  string-based interface — the handler joins the list at the call site;
  `get_observations` is unchanged. The repo's "taxa is a string everywhere"
  convention in CLAUDE.md is rewritten to: list in the config model, joined to
  a string at the datasource boundary.
- **ui_schema**: `taxa.items` gets the annotation shown in Section 1, added to
  the existing `ui_schema()` override; the existing drift test extends to
  `list_taxa` and additionally asserts `search.param` names a real query-model
  field and does not collide with `params` keys.

## Section 5 — Compatibility matrix

| Widget | Runner annotation | Result |
|---|---|---|
| New (search-aware) | `search` declared | Typeahead |
| Old (pre-search) | `search` declared | Ignores `search`; one menu-open fetch with remaining params → capped default page or empty list (runner convention, Section 1) — degraded but working, no errors |
| New | No `search` | Today's behavior exactly |
| Any | `search.param` missing from query model | Runner-side drift test failure at development time; at runtime pydantic v1 ignores unknown override keys, so the fetch still succeeds unfiltered — never shipped because annotation and query model live in the same runner release |

## Section 6 — Testing

- **gundi-portal** (`ReferenceSelectWidget` tests, mirroring the existing
  suite): typing ≥ `min_chars` triggers a debounced fetch carrying the param;
  below `min_chars` no fetch and the type-to-search placeholder shows; stale
  responses are discarded; `$data` + `search` compose (and empty `$data` still
  blocks); annotations without `search` regress nothing; cache key includes
  the query.
- **iNat repo** (TDD, per its established patterns): handler tests over a
  mocked datasource wrapper (label/fallback/rank/truncated/empty-q); taxa
  coercion matrix (legacy comma-string, list, empty, scalar); drift-test
  extension for `list_taxa` and the `search.param` assertions; existing
  pull-events tests keep passing with the joined-string call site.
- **cdip**: nothing new; PR #461's execute-authorization tests already cover
  the invocation path.

## Rollout

1. This spec merges to cdip main (docs only).
2. gundi-portal ships the widget change (inert until an annotation declares
   `search`).
3. The iNat runner ships `list_taxa` + the taxa reshape + annotation; on
   re-registration, taxa becomes a typeahead multi-select in portals running
   the new widget and a degraded-but-working field elsewhere.

Order matters only between 2 and 3 for UX polish (shipping 3 first gives old
widgets the degraded dropdown — harmless). Related open item carried over from
the original RFC, unaffected by this design: `$data` resolution semantics from
a primitive array element (the iNat and cmore repos assume resolution starts
at the containing array).

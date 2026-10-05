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
annotation; without it, existing behavior is unchanged.

With `search` declared:

- **No auto-fetch** on mount or menu open. The menu placeholder reads "Type at
  least N characters to search" (localized), N = `min_chars`.
- **Input-driven fetch**: input changes at or above `min_chars` debounce
  (~300 ms) into a fetch whose `config_overrides` are
  `{...resolvedParams, [search.param]: inputText}`.
- **Latest-request-wins**: a response renders only if it answers the
  complete current request — resolved params *and* query. Any change to
  either (new input text, or a `$data` dependency changing while the text
  stays the same) invalidates every in-flight request immediately, before
  any debounce, and the new request is refetched. Matching on input text
  alone is not enough: the same text can have requests in flight for two
  different parent values.
- **Caching**: client-side cache keyed on the complete request —
  `(integration_id, action, merged config_overrides)`, i.e. the resolved
  params plus `{search.param: query}` — honoring `cache_ttl_seconds`. Keying
  on the merged overrides (not on the query text alone) keeps two fields that
  reuse one action with different `search.param` names from colliding.
- **Unchanged**: free-text entry (`allow_free_text`), cold-start loading
  escalation copy, provider-target (`target: "provider"`) union-and-dedupe,
  fetch-failure degradation to plain text with retry.
- **Saved-value labels (known gap, deferred)**: because there is no menu-open
  fetch, a stored opaque ID renders as the raw ID with no label and no
  warning badge (the badge remains gated on a successful fetch, which will not
  have happened). A future `resolve` block — an annotation-declared lookup of
  options by stored value — is the designed fix; it is out of scope here.

## Section 3 — cdip (this repo)

**Search contract: no code change.** The execute proxy
(`ActionTriggerView.execute`) already passes `config_overrides` through
verbatim, and PR #461 authorizes reference-action execution for config
editors. Typeahead traffic is just more frequent execute calls; the widget's
debounce, `min_chars` gate, and TTL cache bound the rate. No server-side rate
limiting is added now — revisit only if runner load or activity-log volume
shows a real problem. This document lives in cdip because the platform owns
the contract; the search implementation lands in gundi-portal and the
integration repos.

**Saved-data normalization for the iNat `taxa` reshape: required.** Changing
a field's published type (string → array, Section 4) breaks existing saved
configurations on the portal side, not just the runner side.
`IntegrationCreateUpdateSerializer.validate` calls
`action.validate_configuration(...)` (plain `jsonschema.validate` against the
registered schema) for each entry in the request's `configurations` list,
before the runner ever sees the data. A PATCH that omits `configurations`
(e.g. renaming the connection) skips this. But any request that includes the
`pull_events` configuration resubmits its whole `data` object, stored `taxa`
included. Once re-registration publishes the array schema, an integration
whose stored config still holds `{"taxa": "123,456"}` therefore fails
validation whenever that configuration is saved — including an operator
changing only an unrelated field such as `days_to_load`. The runner's
coercing pre-validator cannot help; it runs too late.

cdip therefore ships an idempotent management command that rewrites stored
values for one (integration type, action, field):

```
python manage.py normalize_config_field_to_list \
    --integration-type <inat-type-value> --action pull_events --field taxa [--dry-run]
```

- Splits comma-separated strings on `,`, strips whitespace, drops empties
  (`"123, 456"` → `["123", "456"]`; `""`/`"  "`/`",,"` → key removed, matching
  the runner's existing "blank means no filter" semantics); wraps scalar
  leftovers in a one-element list; leaves values that are already lists
  untouched.
- Writes through the model (`save()`) so `ChangeLogMixin` records the
  change in the activity log like any other edit (v2 `IntegrationConfiguration`
  has no django-simple-history tracking, so there is no historical record); `--dry-run` prints the
  before/after per configuration without writing.
- Scoped by flags rather than hard-coded to iNat, because any future
  string → array reshape for a dropdown hits the same validation wall.

It is run immediately after the runner's re-registration (Rollout step 4).
Not a Django data migration: migrations run on cdip deploy, which is not
ordered with runner re-registration, and normalizing before the array schema
is published would make those configs fail the *old* string schema instead.
In the window between re-registration and the command run, saves of
un-normalized configs fail with a schema error rather than corrupting data;
the runner's string-coercing pre-validator keeps scheduled pulls working
throughout, since pulls read stored config without jsonschema validation.

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
- **cdip**: nothing new for the search path (PR #461's execute-authorization
  tests cover it). For the normalization command: the conversion matrix
  (comma-string with spaces, blank/commas-only, scalar, already-a-list,
  missing key, other integration types/actions untouched, `--dry-run` writes
  nothing, second run is a no-op); and the end-to-end regression — register
  the string schema, save `{"taxa": "123,456", ...}`, re-register the action
  with the array schema, run the command, then update the integration via the
  v2 API with a request that includes the `pull_events` configuration
  while changing only an *unrelated* field in it and assert it validates and persists
  `["123", "456"]`. The same test asserts that without the command the update
  is rejected, pinning down why the step exists.

## Rollout

1. This spec merges to cdip main (docs only).
2. gundi-portal ships the widget change (inert until an annotation declares
   `search`).
3. cdip ships `normalize_config_field_to_list` (any time before step 4).
4. The iNat runner ships `list_taxa` + the taxa reshape + annotation; on
   re-registration, taxa becomes a typeahead multi-select in portals running
   the new widget and a degraded-but-working field elsewhere. **Immediately
   after re-registration**, run the command (`--dry-run` first) against the
   environment's iNat integrations. The runner's conditional
   `required`/`then` branch must also move from
   `{"type": "string", "pattern": ...}` to `{"type": "array", "minItems": 1}`
   so a blank list still counts as "no taxa".

Order between 2 and 4 matters only for UX polish (shipping 4 first gives old
widgets the degraded dropdown — harmless). Step 3 must precede 4, and the
command run must follow re-registration directly. Related open item carried over from
the original RFC, unaffected by this design: `$data` resolution semantics from
a primitive array element (the iNat and cmore repos assume resolution starts
at the containing array).

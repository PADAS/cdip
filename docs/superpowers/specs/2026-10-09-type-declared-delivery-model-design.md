# Design — integration types declare their delivery model

## Problem

cdip-routing chooses how to deliver to a destination — a legacy in-process
Transformer or a `GundiDelivery` envelope that the destination's action runner
transforms — by destination integration **type**, from its own env setting
`GENERIC_MODEL_DESTINATION_TYPES` (default `["cmore", "generic_webhooks"]`).
The per-integration `additional.generic_model` flag is an opt-in override for
one-off cases.

That works, but the fact lives in the wrong place. The action runner defines
which data model its push actions accept (`GundiDelivery` vs
`MessageTransformedInReach`, …), yet onboarding a new generic-model connector
needs a separate cdip-routing deploy, and forgetting it is silent: routing
takes the legacy path, finds no transformer for the type, and discards the data.

## Goal

The runner declares its delivery model when it self-registers. cdip stores it on
`IntegrationType` and exposes it with the type. cdip-routing reads it from the
destination it already loads. Then no routing deploy is needed for new connectors.

## Model

`IntegrationType.delivery_model`: `CharField(choices=...)`, default `"legacy"`.

| Value | Meaning | Routing publishes |
|---|---|---|
| `legacy` | Routing transforms in-process (ER, SMART, WPS Watch, TrapTagger, Movebank, inReach, …) | `*Transformed*` event / raw dict |
| `generic` | The runner transforms | one `GundiDelivery` per observation |
| `generic_batch` | Like `generic`, and the runner also accepts bundles | `GundiBatchDelivery` for `ObservationsBatchReceived`, `GundiDelivery` otherwise |

An enum (not a boolean) so the bundle capability (see the outbound-webhooks
design in gundi-integration-generic-webhook, `docs/outbound-webhooks.md`) does
not need a second flag. Migration: add the field with default `legacy`, then a
data migration that sets `generic` on `cmore` and `generic_webhooks`, matching
today's routing default.

## API / serializers (`api/v2/serializers.py`)

- `IntegrationTypeIdempotentCreateSerializer` and `IntegrationTypeUpdateSerializer`:
  accept `delivery_model`, optional. **Omitted means unchanged** on update, and
  `legacy` on create. Older runners that don't send it must not reset a value set
  by a newer runner or by an operator.
- `IntegrationTypeFullSerializer`: read-only `delivery_model`, so it reaches
  cdip-routing in `get_integration_details(...).type`.
- Admin: editable on the IntegrationType admin page, for operators.

## gundi-core

Add `delivery_model: Optional[str] = "legacy"` (or an enum) to
`gundi_core.schemas.v2.IntegrationType` (`schemas/v2/gundi.py`). Optional with
a default, so payloads from a cdip that doesn't send it still parse. When the
batch envelope lands, move `GundiBatchDelivery` from the runner into
`gundi_core.events` in the same release.

## cdip-routing precedence (`_uses_generic_model`)

1. `destination_integration.type.delivery_model in {"generic", "generic_batch"}` → generic
2. `type.value in settings.GENERIC_MODEL_DESTINATION_TYPES` → generic (transition; delete once every
   generic connector declares it)
3. `additional.generic_model` truthy → generic (one-off opt-in, admin-only)
4. otherwise legacy

A type that declares `legacy` but is still listed in the env setting stays generic during the
transition. That keeps the env setting a safe rollback lever, and removing the env entry is the
explicit switch-off. Bundles go only to `generic_batch` (no env fallback): a runner without a
`GundiBatchDelivery` handler can't process a bundle.

## Action runners (template + connectors)

`self_registration.py` sends `delivery_model`: `generic_batch` if any registered *or internal* push
action's data model is `GundiBatchDelivery`, else `generic` if any push action's data model is
`GundiDelivery`, else `legacy`. The data model is already known from the handler's annotations
(the same introspection `/push-data` routing uses), so connectors don't configure it by hand.

## Release order

1. gundi-core: field + (later) `GundiBatchDelivery`. Additive; release.
2. cdip: migration + serializers + admin, with the data migration matching today's env default.
   Deploy. Existing runners don't send the field, so nothing changes.
3. cdip-routing: bump gundi-core and add precedence step 1. Deploy. Behavior unchanged, because steps 1
   and 2 agree for cmore and generic_webhooks.
4. Action-runner template, then connectors: send `delivery_model` on registration.
5. After every generic connector has re-registered: drop the env list (step 2).

Each step is backward compatible with the previous deployment of the others.

## Security and tenant isolation

- Only superusers / service accounts can write IntegrationTypes. `IsOrgAdmin` allows only
  `execute_reference_action` on `integration-types` (`api/v2/permissions.py`), so an org admin can't
  flip a type's delivery model. Keep it that way, and include `delivery_model` in the type-write
  permission tests (superuser allowed; org admin, viewer and other-org user denied).
- The flag is type-wide and changes only the payload *shape*, not where data goes. The topic still
  comes from `additional.topic`, which cdip sets and the v2 write serializer excludes. Do not open
  `additional` to the portal: it holds the routing topic, and an org admin could aim it at any
  topic in the project.
- A wrong value fails closed for tenants. A `legacy` runner that receives a `GundiDelivery` rejects
  it in `/push-data` by `event_type`, and Pub/Sub dead-letters it. Nothing reaches another tenant,
  because the runner resolves configuration from the `destination_id` attribute that routing sets
  from the route.

## Tests

- cdip: serializer create/update with, without and with an invalid `delivery_model`; an update without
  the field keeps the stored value; type-write permission matrix; data migration.
- cdip-routing: the precedence table, parametrized over (type value, env list, additional flag);
  bundle publication only for `generic_batch`.
- Runner template: the registration payload for handlers annotated with each data model.

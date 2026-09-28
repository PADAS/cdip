# Proposal: "Connection" and "Route" — a vocabulary change for the Gundi Portal

**Status:** Proposed
**Date:** 2026-08-21

## Summary

Rename the two core concepts users interact with in the Gundi Portal:

| Concept | Data model | Today's UI term | Proposed UI term |
|---|---|---|---|
| Gundi's link to an external system (EarthRanger, SMART, a tracker vendor, …) | `Integration` | Integration | **Connection** |
| The relationship that moves data from one system to others | `Route` | Connection | **Route** |

The one-line version:

> **A Connection is Gundi's link to an external system; a Route moves data from one Connection to others.**

If that sentence is immediately understandable — and we believe it is — that is itself the argument.

## The problem

Users misunderstand the word "Connection" as we use it today. In the current UI, a
"Connection" is a view of a provider integration together with its destinations and
routing rules — a *relationship between systems*. But the word naturally suggests the
*link to a single system* ("my EarthRanger connection"), which is what we call an
"Integration." Both words are doing the wrong job:

- **"Integration" is abstract.** Users read it as a process or a project ("we're
  working on an integration"), not a concrete thing they own and configure.
- **"Connection" implies a symmetric pipe between two peers.** What we actually show
  is one provider fanning out data to several destinations — directional and
  one-to-many. The word fights the mental model instead of teaching it.

## The proposal

### "Connection" for the system link

"Connection" is concrete and possessive: *my EarthRanger connection*, *the SMART
connection is down*. It answers the question users actually ask — "which system does
this talk to?" — and it makes "connect" available as the verb for linking Gundi to an
external system.

### "Route" for the data-moving relationship

1. **It is already the truth in our system.** The data model object that implements
   this relationship is literally called `Route`, and the API exposes "routing
   rules." Adopting it in the UI means the word a user sees, the word support says,
   the word the API returns, and the word in the code are all the same word. Every
   vocabulary mismatch between those layers is a future support ticket; this rename
   removes a whole class of them rather than adding one.

2. **It is directional.** Data in Gundi flows one way: from a provider out to
   destinations. "Route" carries direction for free — data travels *along* a route,
   *from* somewhere *to* somewhere.

3. **It handles one-to-many gracefully.** A "connection to three things" is awkward;
   a route with multiple destinations, or three routes from one source, both read
   naturally.

4. **It is a verb as well as a noun.** UI copy like "Route your EarthRanger data to
   SMART" teaches the product's core action every time the word appears.

5. **It matches the wider ecosystem.** Tools our users encounter (Workato, Zapier,
   network equipment, even Google Maps) use "connection" for the credentialed link to
   a system and route/flow-like words for where things go. We would be moving toward
   the common convention, not inventing a private one.

## Anticipated objections

**"Didn't we already try 'Route'?"** Yes — and it failed in isolation, not on its
merits. It was never paired with a concrete word for the system link, so users had no
stable anchor for either concept. This proposal fixes the pair, not one word.

**"Won't changing the meaning of 'Connection' confuse existing users?"** Users are
not attached to the current meaning — the ongoing confusion is the evidence. The new
meaning matches what most people already assume the word means, so for many users
this is less a change than a correction.

## Rollout considerations

- **API naming will lag the UI.** The `/v2/connections` endpoint currently returns
  what this proposal calls Routes. The UI rename should not pretend the API flips at
  the same time; plan for aliasing or a deliberate v-next rename.
- **Docs and support material need a coordinated sweep.** A semantic swap works as a
  clean break, not a gradual drift — the announcement, the docs, and the UI should
  change together.
- **Glossary first.** Publish the one-line definition above in the portal help and
  onboarding material before or alongside the UI change.

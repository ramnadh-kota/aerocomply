# ADR-010 — Aircraft Configuration Is a Derived As-Of View, Never a Stored Snapshot

## Status
Proposed (part of Aviation Ontology v1.0 — pending CTO approval)

## Context
The CTO's ontology brief requires AeroComply to eventually answer "what configuration did this aircraft have at a specific point in time," with a worked example of an engine changing from Engine X to Engine Y on a specific date. Every installation-type fact in the ontology (engine, component) is naturally a time-bounded interval (installed_at/removed_at), not a point-in-time value.

## Decision
"Aircraft Configuration" is not a stored entity or a mutable "current state" field anywhere in the schema. It is always a derived result of an as-of query across the installation-interval tables (`EngineInstallation`, `ComponentInstallation`) plus the aircraft's variant and (future) modification state, evaluated at whatever timestamp the caller needs — "now" for a live applicability evaluation, or an arbitrary past timestamp for historical reconstruction. `ApplicabilityAssessment.data_version` captures a hash/marker of this derived snapshot at evaluation time, so a specific historical assessment's inputs remain reproducible without needing to store the snapshot itself.

## Alternatives Considered
- **A mutable `current_configuration` snapshot table/JSON blob on `Aircraft`, updated on every installation change**: rejected — this is a second, denormalized representation of exactly the same facts already captured in the installation-interval tables, and it can drift out of sync with them (a missed update path, a bug, a manual data fix) in a way that would silently corrupt every future applicability assessment computed against it. This is precisely the dual-authoritative-state problem ADR-002 already ruled out for Postgres/Neo4j, recurring here inside Postgres itself if we're not careful.
- **Storing a full configuration snapshot at every `ApplicabilityAssessment`**: rejected as the *storage* mechanism (though the *concept* of "what configuration was used" is still captured, via `data_version`) — a full snapshot per assessment duplicates data that's already reconstructable from the interval tables, and duplicating it doesn't add reproducibility beyond what a content-hash-style `data_version` already provides at much lower storage cost.

## Consequences
- Every "what configuration did aircraft X have" question — live or historical — is answered by the same query shape (domain invariant #19), which is a correctness benefit: one code path, not two (a "live" path and a separate "historical" path that could diverge in behavior).
- Correctness of every configuration-derived answer depends entirely on the installation-interval invariants (#7–#10, especially the no-overlap exclusion constraints) actually holding — this ADR's design makes those constraints load-bearing for compliance correctness, not just data hygiene, which should raise their implementation priority accordingly in M1.
- Performance: an as-of query requires scanning installation history rather than reading one row; acceptable at M1 fleet scale, and indexable (`(aircraft_id, position, installed_at, removed_at)`), but worth monitoring as fleet/history size grows — no premature caching layer is proposed now.

## Reversal Conditions
Reconsider only if as-of query performance becomes a measured bottleneck at real fleet scale — the correct escalation at that point is a *read-side cache* (e.g., a materialized view refreshed from the interval tables, itself still derived and rebuildable) rather than a hand-maintained mutable snapshot, to avoid reintroducing the dual-authority risk this ADR exists to prevent.

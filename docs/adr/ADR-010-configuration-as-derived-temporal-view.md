# ADR-010 — Aircraft Configuration Is a Derived As-Of View, With a Non-Authoritative Per-Assessment Snapshot for Reproducibility

## Status
Proposed (part of Aviation Ontology v1.0 — pending CTO approval)

## Context
The CTO's ontology brief requires AeroComply to eventually answer "what configuration did this aircraft have at a specific point in time," with a worked example of an engine changing from Engine X to Engine Y on a specific date. Every installation-type fact in the ontology (engine, component) is naturally a time-bounded interval (installed_at/removed_at), not a point-in-time value.

## Decision
"Aircraft Configuration" is not a stored entity or a mutable "current state" field anywhere in the schema. It is always a derived result of an as-of query across the installation-interval tables (`EngineInstallation`, `ComponentInstallation`) plus the aircraft's variant and (future) modification state, evaluated at whatever timestamp the caller needs — "now" for a live applicability evaluation, or an arbitrary past timestamp for historical reconstruction.

**Amendment (CTO review, post-v1.0)**: the original version of this ADR proposed relying on `ApplicabilityAssessment.data_version` (a hash/marker) as the *complete* reproducibility mechanism, with no stored record of what the hash was actually computed over. The CTO's review correctly rejected this as insufficient — a bare hash lets you *detect* that a recomputation differs from the original, but does not let you *see* what the original configuration actually was without re-deriving it, and provides no artifact to inspect when auditing a historical decision. The design is amended to add an immutable `configuration_snapshot` (a structured manifest — variant, registration, installed engines by position, installed components by position, and the as-of timestamp used) stored directly on the `ApplicabilityAssessment` row, with `data_version` now defined precisely as the content hash *of that stored snapshot*. The snapshot is captured once, at evaluation time, and — like every other field on an `ApplicabilityAssessment` row — never subsequently edited.

**This snapshot is explicitly not a second authoritative source.** The pipeline is:
```
Authoritative configuration history (EngineInstallation, ComponentInstallation, RegistrationHistory, Aircraft)
        ↓ (as-of query, at evaluation time)
As-of configuration
        ↓ (fed into)
Rules engine
        ↓ (records what it was given, verbatim, as a byproduct of running)
Immutable configuration_snapshot (on the ApplicabilityAssessment row)
        ↓ (content-hashed as)
data_version
```
The snapshot is a **record of what was evaluated for one specific assessment**, not a claim about what is currently or was ever "true" about the aircraft independent of that assessment. Nothing ever reads the snapshot to answer "what is aircraft X's configuration" — that question is still answered exclusively by the as-of query against the interval tables, every time, including when re-verifying an old assessment's reproducibility (the check is: does re-running the as-of query at the assessment's original timestamp produce the same manifest as the stored snapshot? — the interval tables remain the sole arbiter of truth; the snapshot is the thing being checked against them, not a competing source of it).

## Alternatives Considered
- **A mutable `current_configuration` snapshot table/JSON blob on `Aircraft`, updated on every installation change**: rejected — this is a second, denormalized representation of exactly the same facts already captured in the installation-interval tables, and it can drift out of sync with them (a missed update path, a bug, a manual data fix) in a way that would silently corrupt every future applicability assessment computed against it. This is precisely the dual-authoritative-state problem ADR-002 already ruled out for Postgres/Neo4j, recurring here inside Postgres itself if we're not careful. **This alternative remains rejected after the CTO's amendment above** — the crucial difference between this (rejected) mutable, aircraft-level, continuously-updated snapshot and the (adopted) per-assessment `configuration_snapshot` is that the latter is write-once, scoped to one immutable assessment row, and never read back as "the current state of the aircraft" — it cannot drift, because nothing ever updates it after creation and nothing ever queries it as a source of present-tense truth.
- **`data_version` as a bare hash with no accompanying stored manifest** (the ADR's original v1.0 proposal): rejected per the CTO's review — sufficient to *detect* a reproducibility break, insufficient to *audit* one, since there would be nothing human-readable to inspect without re-deriving the historical as-of query by hand. Superseded by the amended decision above.

## Consequences
- Every "what configuration did aircraft X have" question — live or historical — is answered by the same query shape (domain invariant #19), which is a correctness benefit: one code path, not two (a "live" path and a separate "historical" path that could diverge in behavior).
- Correctness of every configuration-derived answer depends entirely on the installation-interval invariants (#7–#10, especially the no-overlap exclusion constraints) actually holding — this ADR's design makes those constraints load-bearing for compliance correctness, not just data hygiene, which should raise their implementation priority accordingly in M1.
- Performance: an as-of query requires scanning installation history rather than reading one row; acceptable at M1 fleet scale, and indexable (`(aircraft_id, position, installed_at, removed_at)`), but worth monitoring as fleet/history size grows — no premature caching layer is proposed now.
- Storage: one `configuration_snapshot` manifest per `ApplicabilityAssessment` row (bounded by assessment volume, not by aircraft-days or a continuously-growing history), a materially smaller and more predictable cost than the rejected continuously-updated aircraft-level snapshot would have been.
- FOUNDATION.md §4b's `applicability_assessments` schema sketch (predating this ontology) does not yet list a `configuration_snapshot` column — like `subject_type`/`subject_id` from ADR-008, this is a planned addition to be made when the real M1 migration is written, not a silent contradiction of the M0-approved schema; both additions should land in the same migration.

## Reversal Conditions
Reconsider only if as-of query performance becomes a measured bottleneck at real fleet scale — the correct escalation at that point is a *read-side cache* (e.g., a materialized view refreshed from the interval tables, itself still derived and rebuildable) rather than a hand-maintained mutable snapshot, to avoid reintroducing the dual-authority risk this ADR exists to prevent.

# ADR-003 — Neo4j as Rebuildable Derived Knowledge Graph

## Status
Accepted

## Context
Configuration-change-driven reassessment ("this component changed — which ApplicabilityRules and Aircraft does that affect?") is fundamentally a multi-hop graph traversal. Doing this well in Postgres requires either expensive recursive CTEs or heavy denormalization. But per ADR-002, Postgres must remain the sole source of truth, so any second store must never become an independent ledger.

## Decision
Neo4j holds a graph projection of Postgres entities (§5 of FOUNDATION.md), synced asynchronously via an outbox pattern: writes commit to Postgres first, then a background process propagates graph-relevant changes to Neo4j. Neo4j is fully rebuildable from Postgres at any time (a rebuild job re-derives all nodes/relationships) and is never queried as the authority for a compliance decision — only for identifying *candidates* (e.g., "which rules might be affected"), which the rules engine then re-evaluates against Postgres data.

## Alternatives Considered
- **No graph database; model traversals in Postgres with recursive CTEs**: rejected for MVP-forward reasons — workable at small scale but the query complexity and performance degrade exactly as fleet/rule volume grows, and the domain is explicitly graph-shaped (§Aviation Knowledge Graph in FOUNDATION.md).
- **Neo4j as a second primary store (synchronous dual-write)**: rejected — reintroduces the dual-write consistency risk ADR-002 exists to avoid; outbox + async sync + full rebuildability is the standard pattern for keeping a derived store safely decoupled.

## Consequences
- Any Neo4j downtime or lag degrades only graph-query features (reassessment-candidate lookup), never core correctness.
- Requires an outbox table/process and a periodic reconciliation job to catch missed sync events — added operational component, but bounded in scope (§16 risk: "Postgres/Neo4j drift").
- Complex graph reasoning (impact analysis) becomes tractable and fast, versus recursive SQL.

## Reversal Conditions
Reconsider if sync lag or operational cost of running Neo4j outweighs its query benefit before configuration-change-triggered reassessment (a deferred v0.1 feature) is actually built — at that point, evaluate whether Postgres recursive queries suffice for actual observed graph depth/fanout before investing further in the graph layer.

# ADR-002 — PostgreSQL as Source of Truth

## Status
Accepted

## Context
AeroComply must answer regulatory and audit questions years after the fact — "what did we know, what did we decide, and why" — with legally defensible traceability. It also needs graph-shaped queries (impact analysis, reassessment triggers) that relational joins handle poorly at scale. Two candidate stores (PostgreSQL, Neo4j) could each plausibly hold "the" data.

## Decision
PostgreSQL is the single system of record for all transactional, tenant, regulatory, and audit data (§4/§4a/§4b of FOUNDATION.md). Every entity, every version, every assessment lineage row is written to Postgres first, inside ACID transactions. Neo4j (ADR-003) is populated only from Postgres, asynchronously, and is never a required read path for correctness-critical operations.

## Alternatives Considered
- **Neo4j as primary store**: rejected — graph databases are weaker for the strict schema/constraint enforcement, transactional guarantees, and mature migration tooling that immutable regulatory/audit history demands; also weaker ecosystem support for Alembic-style versioned migrations.
- **Dual-primary (write to both, whichever succeeds is truth)**: rejected outright — this creates exactly the dual-write consistency problem the architecture is designed to avoid; there must be one arbiter of truth for compliance-critical data.

## Consequences
- All correctness/audit guarantees rely on Postgres constraints, transactions, and migrations — well-understood tooling (Alembic) and operational maturity.
- Graph-shaped queries (multi-hop impact analysis) are more verbose in SQL than they would be in Cypher for some cases; mitigated by Neo4j as a read-optimized derived index (ADR-003), not by forcing those queries into Postgres.
- Any Neo4j outage or staleness never blocks correctness-critical writes (assessments, evidence, audit events) — only degrades graph-query features.

## Reversal Conditions
Reconsider if graph-shaped queries become the dominant workload and their SQL implementation becomes an unmaintainable bottleneck even after indexing/materialized-view optimization — at that point, evaluate promoting Neo4j to a co-primary for specific read paths only, never for writes.

# Digital Asset & Component Twin — Architecture (H6)

**The Digital Twin is a derived, evidence-linked representation of
authoritative Kota Aerospace domain data. PostgreSQL remains the system of
record.**

## Core principle

H6's entire design is a consequence of one decision, stated explicitly in
the spec and taken literally here: **the twin does not duplicate
authoritative data.** `app/services/digital_twin_service.py` contains
**zero** new authoritative tables. Every function in it calls an existing
domain service — `asset_service`, `hums_service`,
`readiness_intelligence_service` — and assembles the results. There is no
`TwinAsset`, no `HUMSDigitalTwinState`, no `HUMSTwinSnapshot`, no
`HUMSTwinEvent` table. The two new schema files this milestone adds
(`app/schemas/digital_twin.py`) are **response shapes**, not persisted
models.

This is not a shortcut — it is the architecturally correct answer to H6's
own stated risk (spec sections 53/56): a persisted "twin state" that could
drift from the authoritative records it summarizes would need a
reconciliation engine to detect and repair that drift. By never persisting
twin state in the first place, **every twin read is already a fresh
rebuild from authoritative data** — the classic twin-state-drift problem
is sidestepped by construction, not solved after the fact.

## What already existed and was reused, not duplicated

The H0/H6 audit found `app/services/asset_service.py` already implements
almost exactly the aggregation surface H6 asks for:
`get_asset_configuration`, `get_asset_components`, `get_asset_utilization`,
`get_asset_maintenance`, `get_asset_findings`, `get_asset_compliance`,
`get_asset_readiness` — all pre-existing, all backing the current
`assets/[id]` frontend page. H6's job was almost entirely to:

1. Call these existing functions.
2. Add the ONE thing they didn't yet know about: H3/H4/H5 HUMS state
   (`hums_service.get_asset_health_intelligence`,
   `list_asset_diagnostics`, `list_asset_prognostics`).
3. Assemble it all into one `DigitalTwinAssetSnapshot`.

Component genealogy similarly reuses the **existing**
`ComponentInstallation` model (H1/M17.2C) — querying every installation
span for a `component_id` across every asset it's ever been on already
answers "where has this component been?" without inventing a new lineage
table.

## Component hierarchy — a documented scope boundary, not an oversight

The spec's target diagram shows `Aircraft → Engine → Compressor → Turbine
→ Gearbox → Sensors`. The H0/H4/H6 audits all confirm the same fact:
`Component` (`app/models/component.py`) has **no `parent_component_id`**.
This codebase can represent `Asset → Component` (flat, one level) and
nothing deeper. H4's fault-isolation documentation already established the
same limitation for diagnostic isolation; H6 inherits it for the same
reason. `DigitalTwinComponentNode` is therefore flat by design — fabricating
a deeper hierarchy the database cannot actually represent would produce a
UI that lies about what Kota actually knows.

## Snapshot composition

```
DigitalTwinAssetSnapshot
├── identity          <- Asset row (L1)
├── configuration      <- asset_service.get_asset_configuration (L2)
├── usage               <- asset_service.get_asset_utilization (L5)
├── health              <- hums_service.get_asset_health_intelligence (H3, L7)
├── diagnostics[]        <- hums_service.list_asset_diagnostics (H4, L8)
├── prognostics[]         <- hums_service.list_asset_prognostics (H5, L9)
├── maintenance          <- asset_service.get_asset_maintenance + get_asset_findings (L10/L11)
├── compliance            <- asset_service.get_asset_compliance (L12)
├── readiness              <- readiness_intelligence_service.get_asset_readiness_intelligence (L13)
└── generated_at
```

Every sub-section that could fail independently (health/readiness — both
wrap external evaluation that could raise) is wrapped so a failure in one
section never breaks the whole snapshot; it instead reports
`availability: "DATA_UNAVAILABLE"` (readiness) or `null` (health) rather
than a fabricated value or a 500 for the entire endpoint.

## Consistency, never silent correction

Real data-integrity issues can happen (a migration bug, a manual DB fix
gone wrong, a race condition in an install/remove flow). H6 spec section
41 requires these be detected, not silently ignored or auto-corrected.
`digital_twin_service.check_asset_consistency` runs a small, real set of
checks:

- **`SENSOR_COMPONENT_REFERENCE`**: a `HUMSSensor.component_id` pointing at
  a component not currently listed on the asset.
- **`DUPLICATE_OPEN_INSTALLATION`**: more than one `ComponentInstallation`
  row with `removed_at IS NULL` for the same component (should be
  impossible given the existing partial unique index, checked anyway as a
  defense-in-depth data-integrity assertion).
- **`INSTALLATION_ASSET_MISMATCH`**: a component's open installation
  record points at a different asset than `Component.asset_id` says.

These return `DigitalTwinConsistencyWarning` rows to a human reviewer —
`check_asset_consistency` never writes anything, never "fixes" the
mismatch itself.

## Timeline — live aggregation, not a persisted event log

`get_asset_timeline` is a bounded UNION over several existing tables' own
timestamps (`Asset.created_at`, `ComponentInstallation.installed_at/
removed_at`, `HUMSDiagnosticCandidate.detected_at`,
`HUMSPrognosticRecord.calculated_at`, `Finding.discovered_at`,
`WorkOrder.created_at`), each capped at `TIMELINE_PER_SOURCE_LIMIT` (15)
rows, merged and sorted, capped overall at `TIMELINE_TOTAL_LIMIT` (50).

**Why no `HUMSTwinEvent` table** (spec section 26 explicitly invites
skipping this if the existing architecture can represent it cleanly): a
new event-log table populated by writing a row every time something
interesting happens elsewhere would be a second, parallel history that
could itself drift from the records it's summarizing — the exact
architectural risk H6's core principle exists to avoid. The existing
tables' own timestamp columns already ARE that history.

## Graph (Neo4j) — not implemented, and why

The H0/H4/H6 audits all confirm `app/graph/` is an empty stub — no Neo4j
integration exists anywhere in this codebase. H6 spec section 12 makes
graph projection conditional ("if Neo4j is already available... if
asynchronous infrastructure does not exist, implement a clean synchronous
projection boundary... do not introduce Kafka/Celery/etc. merely for H6").
Given no existing graph infrastructure and no current consumer that needs
graph-native traversal (every genealogy/hierarchy query this milestone
needs is a straightforward bounded SQL query), building a Neo4j
synchronization pipeline for H6 alone would be net-new infrastructure
disproportionate to the actual requirement. Documented extension point for
a future milestone if a genuine graph-native use case (e.g. deep
multi-hop "which findings trace back through which components across
which assets" queries at fleet scale) emerges.

## Async boundary

No background-job infrastructure exists in this codebase (same
observation H2–H5 already made). Every twin read runs synchronously; there
is no queue, no event bus, no async projection step. Because nothing is
persisted, there is also no "twin projection lag" to design around — the
snapshot is always as current as the underlying H1–H5/MRO/compliance/
readiness data itself.

## Performance

The snapshot endpoint makes a bounded number of calls to already-optimized
existing services (each already indexed/bounded from its own milestone) —
never raw telemetry, never an unbounded scan. See
`docs/DIGITAL_TWIN_LIFECYCLE.md` for the component-tree and timeline
query-count characteristics.

## Security

`DIGITAL_TWIN_READ` is a single permission gating the whole aggregated
view (see `app/core/permissions.py`'s comment for why one permission
rather than requiring all five-plus underlying domain permissions
individually). No `DIGITAL_TWIN_WRITE` exists — every mutation
(component install/remove, HUMS diagnostic confirm/reject, work order
state changes) goes through its existing, already-audited endpoint.
Tenant isolation is enforced the same way every underlying service already
enforces it (organization_id filtering) — the twin adds no new isolation
boundary to get wrong, because it introduces no new authoritative table.

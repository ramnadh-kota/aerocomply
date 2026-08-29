# AeroComply M1 Scope Boundary v1.0

This divides the Aviation Ontology into what must exist for the first useful product (M1 Core), what advanced compliance intelligence needs next (M2), and what is explicitly future (M3+). The goal is a working, honest product at M1 — not a complete aviation ontology implemented at once, which the CTO's directives have consistently warned against (cf. FOUNDATION.md's original MVP-scope discipline).

## M1 Core — required for AeroComply's first useful product

**Organizations & identity** (mostly exists from M0):
- `Organization` with `org_type` discriminator (ADR-007)
- Existing M0 auth/RBAC/multi-tenancy — unchanged

**Aircraft:**
- `AircraftType`, `AircraftVariant`, `Aircraft`
- `RegistrationHistory` (interval table — needed from day one, since even a single re-registration event breaks a naive "registration on Aircraft" design)

**Engines:**
- `EngineType`, `Engine`, `EngineInstallation`
- Engine as an independent `ApplicabilityAssessment` subject (ADR-008) — the polymorphic `subject_type` is core, even if engine-specific applicability rules are initially few in number, because retrofitting this later is exactly the schema-break pattern the CTO's directives ask us to avoid

**Components:**
- `Component`, `ComponentInstance`, `ComponentInstallation` (ADR-009)
- Serialization discriminator (`requires_serialization`) — core, because it's what prevents fabricating false traceability

**Regulatory domain (extends existing M0-reserved schema):**
- `RegulatoryAuthority`, `RegulatoryDocument`, `RegulatoryRequirement` — already designed in FOUNDATION.md/ADR-006; M1 is where these get real migrations and CRUD
- `ApplicabilityRule`, `ApplicabilityCondition` (the condition tree is new-in-M1 detail, decomposing the previously-abstract `predicate jsonb` into addressable, explainable nodes)

**Applicability & compliance:**
- `ApplicabilityAssessment` with system/human/final separation — already designed (ADR-005); M1 implements it against real aircraft/engine data
- The deterministic rules engine itself, evaluating `ApplicabilityCondition` trees against an as-of aircraft/engine configuration snapshot

**Evidence:**
- `Evidence` with the core evidence types (`MAINTENANCE_RECORD`, `UPLOADED_DOCUMENT`, `STRUCTURED_RECORD_REFERENCE`, `REGULATORY_DOCUMENT`) — OEM_DOCUMENT and INSPECTION_RECORD as evidence *types* exist in the enum but their dedicated structured entry workflows can wait for M2
- `MaintenanceRecord` (minimal — date, description, referenced aircraft/component; see explicit scope confirmation below)

### Explicit confirmation: MaintenanceRecord is not a maintenance management system

The CTO's review specifically asked us to confirm M1 does not build a full maintenance management system under the `MaintenanceRecord` label. Confirmed: `MaintenanceRecord` in M1 has exactly the fields needed to serve as (a) a configuration-change input signal (e.g., "this record documents that Modification M was embodied on this date") and (b) a linkable `Evidence` source for an `ApplicabilityAssessment` — date, description, a reference to the aircraft/component it concerns, and an optional file attachment. It explicitly does **not** include: work order management, task/discrepancy tracking, labor/parts costing, scheduling or forecasting of future maintenance, technician sign-off workflows, or a maintenance-program/task-card library. Those are the actual components of a maintenance management system (the kind of product an MRO's own operational software provides) and are permanently out of AeroComply's product scope, not merely deferred to a later milestone — AeroComply consumes maintenance records as compliance-relevant *evidence*, it does not manage maintenance operations. If a future integration need arises (e.g., ingesting records from a customer's existing maintenance-management system), that is a data-ingestion feature, not a reason to grow `MaintenanceRecord` into an operational system in its own right.

**Temporal model:** the interval-table pattern (ADR-010, TEMPORAL_MODEL.md) — this is not an optional add-on, it is how M1's core tables are shaped from the start.

## M2 — needed for advanced compliance intelligence

- **Modification / STC tracking** as a first-class entity (currently representable only indirectly via `RegulatoryRequirement.references_requirement_id` and configuration snapshots) — needed once applicability rules commonly need to express "excluded if modification X embodied" as a structured, queryable fact rather than free text in a rule's `type_metadata`.
- **Service Bulletin dedicated workflow** — the `requirement_type = SB` row shape already exists (ADR-006); M2 adds the manufacturer-recommended-vs-mandated review workflow and OEM-document-specific evidence entry UI.
- **Life-Limited Part (LLP) cumulative life tracking** — cycles/hours-since-new tracked on `ComponentInstance` independent of any single installation, life-limit thresholds, and alerting as a limit approaches. Deferred because it is a materially different (and higher-stakes) tracking domain from ordinary component installation, and half-implementing it in M1 risks a false sense of coverage worse than not having it yet.
- **Configuration-change-triggered reassessment** — automatically identifying and queuing reassessment candidates when an installation event changes an aircraft's configuration in a way that intersects an `ApplicabilityRule`'s `APPLIES_TO` graph edges (Neo4j-driven, per FOUNDATION.md's original Aviation Knowledge Graph design). M1 supports on-demand evaluation only; the trigger/orchestration layer is M2.
- **AMC/GM structured applicability** — these are non-binding (per the glossary's explicit warning) and need their own, deliberately different, non-mandatory applicability semantics rather than reusing the AD-shaped binding-obligation model as-is.
- **Inspection record and OEM document dedicated structured entities** (beyond the generic `Evidence.evidence_type` enum values already reserved for them in M1).

## M3+ — future capability

- **Regulatory document ingestion automation** (parsing/extraction pipeline) beyond the M1 manual-entry-with-review-queue baseline already designed in FOUNDATION.md §11.
- **Multi-authority cross-validation** — automatically reconciling an adopted/validated requirement (e.g., India DGCA's adoption of an FAA AD) against its originating document, surfacing discrepancies.
- **Leasing/ownership tracking** as a domain distinct from operator (the ontology's glossary already distinguishes them; M3 gives ownership its own entity and lease-return-condition workflows).
- **Full Neo4j configuration-graph-driven "what-if" impact analysis** (e.g., "if we install this modification fleet-wide, which currently-applicable requirements become excluded").
- **AI-assisted rule drafting** (still human-reviewed before activation, per ADR-004 — this is an authoring aid, never a decision path).

## Explicitly deferred, not merely "later" — concepts we deliberately do NOT model yet, and why

| Concept | Why deferred | What we do instead in M1 |
|---|---|---|
| Modification/STC as first-class entity | Adds real complexity (approval basis, applicability exclusions) before we've proven the core AD/engine/component chain works end-to-end | `type_metadata` on `RegulatoryRequirement` can carry ad hoc modification-exclusion text for M1's first rules; not queryable as structured data yet. **A rule's `ApplicabilityCondition` tree may still contain a `MOD_EXCLUSION` leaf (it is representable — see [AVIATION_ONTOLOGY.md §7](AVIATION_ONTOLOGY.md)) but M1 has no structured data source to resolve it against. Per domain invariant #23, this must evaluate to `system_result = INSUFFICIENT_DATA`/`REVIEW_REQUIRED`, never a silent assumption that the modification is absent.** |
| Life-Limited Part life tracking | Materially different, higher-stakes tracking domain (safety-critical cumulative life, not just installation presence) | `ComponentInstance` exists and is LLP-tracking-ready in shape, but no life-counter fields or limit-checking logic ships in M1 |
| Configuration-change-triggered auto-reassessment | Requires the Neo4j graph-traversal layer to be built and proven first | M1 supports on-demand `/applicability/evaluate` only, as already specified in FOUNDATION.md |
| Full ownership/leasing entity | Not required to answer the core "does X apply to Y" product question | `Organization.org_type = LESSOR` exists as a role, but no lease-specific data model |
| AMC/GM applicability semantics | Fundamentally non-binding, needs deliberately different (not reused) applicability logic to avoid the correctness hazard flagged in the glossary | `requirement_type` enum reserves the values; no evaluation logic exists for them yet |

## Non-goals restated (already established, not reopened by this ontology)

Per the CTO's original MVP scope and every M0 architecture decision: no LLM-as-decision-engine (ADR-004), no dual-authoritative state between Postgres and Neo4j (ADR-002/003), no silent AI-driven compliance-status changes (ADR-005) — this ontology extends the domain model, it does not revisit any of these standing architectural commitments.

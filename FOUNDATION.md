# AeroComply — Engineering Foundation Document
Version 0.2 (Approved, amended per CTO directive 2026-08-29)

**Core Engineering Principle:** *AeroComply must be deterministic before it is intelligent.*

```
User/Aviation Data → Structured Data → Rules Engine → System Determination
                                                            → AI Explanation
                                                            → Human Decision → Final Compliance Status
```

NOT: `User Data → LLM → Compliance Decision`. The LLM is never the authoritative compliance decision engine. See [ADR-004](docs/adr/ADR-004-llm-not-decision-engine.md).

---

## 1. System Architecture

AeroComply is a modular monolith at MVP stage (not microservices — premature at this scale), organized into clearly separated internal layers so it can be split into services later without a rewrite.

```
                         ┌─────────────────────────┐
                         │   Next.js Frontend (SSR) │
                         └────────────┬─────────────┘
                                      │ HTTPS/JSON (REST)
                         ┌────────────▼─────────────┐
                         │   FastAPI Application     │
                         │  ┌──────────────────────┐ │
                         │  │ API Layer (routers)  │ │
                         │  ├──────────────────────┤ │
                         │  │ Service Layer        │ │
                         │  ├──────────────────────┤ │
                         │  │ Rules Engine         │ │  ← deterministic, no LLM
                         │  ├──────────────────────┤ │
                         │  │ Knowledge Graph Client│ │
                         │  ├──────────────────────┤ │
                         │  │ AI/RAG Explanation    │ │  ← advisory only
                         │  ├──────────────────────┤ │
                         │  │ Document Intelligence │ │
                         │  └──────────────────────┘ │
                         └──┬───────┬───────┬────────┘
                            │       │       │
                  ┌─────────▼─┐ ┌───▼────┐ ┌▼─────────┐
                  │PostgreSQL │ │ Neo4j  │ │  Redis   │
                  │(system of │ │(graph  │ │(cache/   │
                  │ record)   │ │reasoning)│ queue)  │
                  └───────────┘ └────────┘ └──────────┘
                            │
                     ┌──────▼──────┐
                     │ S3 storage  │
                     │ (evidence,  │
                     │ documents)  │
                     └─────────────┘
```

**Key principle:** PostgreSQL is the system of record and source of truth for all transactional/audit data. Neo4j is a derived, rebuildable reasoning index over the same entities — never the sole store of truth. This avoids dual-write consistency nightmares: writes go to Postgres first (in a transaction), then an outbox/event mechanism propagates graph-relevant changes to Neo4j asynchronously.

## 2. Component Architecture

| Component | Responsibility | Must NOT do |
|---|---|---|
| **Document Intelligence** | Parse regulatory documents/ADs/SBs (PDF, XML) into structured candidate fields (applicability text, effectivity dates, referenced part numbers) for human review | Auto-publish structured rules without human confirmation |
| **Structured Regulatory Data** | Postgres tables holding confirmed, versioned `RegulatoryDocument`, `AirworthinessDirective`, `ApplicabilityRule` records | Store unverified/raw extraction as if authoritative |
| **Deterministic Rules Engine** | Evaluates `ApplicabilityRule` predicates against structured `Aircraft`/`Engine`/`Component` data → produces result + reasoning trace | Call an LLM to decide APPLICABLE/NOT_APPLICABLE |
| **Aviation Knowledge Graph (Neo4j)** | Answers "what's connected to what" queries efficiently (impact analysis, reassessment triggers) | Hold data not also present in Postgres |
| **AI Explanation/RAG Layer** | Turns rules-engine output + retrieved source text into a plain-language explanation; answers copilot questions with citations | Originate compliance verdicts; state uncertain things as fact |

Layer boundary is enforced in code: the AI layer only ever receives already-computed `ComplianceAssessment` objects and read-only retrieval context. It has no write path to compliance tables.

## 3. Domain Model (MVP-justified subset)

### Core abstraction chain (amended per CTO directive)

The domain model is built around **RegulatoryRequirement**, not AD. AD/SB/Regulation/Rule/AMC/GM/SIB/mandatory-notice are all *types* of `RegulatoryRequirement`, distinguished by a `requirement_type` discriminator, not by separate tables. This lets new regulatory-source types be added by adding an enum value and type-specific metadata (jsonb), never a schema migration to the core chain.

```
RegulatoryAuthority → RegulatoryDocument → RegulatoryRequirement → ApplicabilityRule → ApplicabilityAssessment
```

`RegulatoryDocument` is the published artifact (a PDF/XML with provenance — see §4a). `RegulatoryRequirement` is the specific obligation extracted from that document (a document may contain many requirements, e.g. an AD with multiple applicability paragraphs). This split is what lets one AD later reference/spawn related SB requirements without restructuring: `RegulatoryRequirement` supports a `references` self-relation (`AD → SB → Maintenance Action` becomes `RegulatoryRequirement(AD) --REFERENCES--> RegulatoryRequirement(SB)`), and `ComplianceRequirement`/`MaintenanceRecord`/`Evidence` already hang off assessments regardless of which requirement type triggered them. No SB-specific table is needed to preserve this chain later.

### Included in v0.1, with justification

- **Organization** — tenant root; required for multi-tenancy from day one.
- **User**, **Role** — RBAC is a stated requirement; needed for any real usage.
- **AircraftType** — needed to anchor applicability rules that apply by type/model.
- **Aircraft** — the core subject of assessment.
- **Engine**, **Component**, **ComponentInstallation** — many requirements apply to engines/components, not airframes; without install history you cannot determine current applicability by serial number.
- **RegulatoryAuthority** — distinguishes FAA/EASA/etc.; requirements and documents are authority-scoped.
- **RegulatoryDocument** — the published artifact, versioned, with full provenance (§4a). Only AD is populated with real content in v0.1; the schema is source-type-agnostic from day one.
- **RegulatoryRequirement** — the generic obligation entity (`requirement_type = AD` for v0.1; `SB | REGULATION | RULE | AMC | GM | SIB | NOTICE | OTHER` reserved in the enum but unused in v0.1). Replaces the previously-proposed standalone `AirworthinessDirective` table.
- **ApplicabilityRule** — the structured, machine-evaluable predicate that drives the rules engine. Heart of the MVP.
- **ComplianceRequirement** — the "what action is required" derived from a requirement applying (e.g., recurring inspection interval).
- **ApplicabilityAssessment** — the persisted, append-only, versioned output of `/applicability/evaluate`, now explicitly separating `system_result` / `human_decision` / `final_status` (§4b/§5 amendments).
- **Evidence** — files/records supporting an assessment or compliance claim; core to the evidence-first principle.
- **MaintenanceRecord** — minimal structured record (date, action, referenced component) needed as an input signal to assessments and as evidence, and as the future anchor point for `AD → SB → Maintenance Action → Aircraft Configuration → Evidence`.
- **AuditEvent** — required for traceability/compliance of the system itself (who did what, when), including every human decision/override (§5).

### Deferred (explicitly out of scope for v0.1, architecturally pre-wired)

- **ServiceBulletin-specific workflow** — SB *content* is representable today as a `RegulatoryRequirement` with `requirement_type='SB'` and a `references` link from its originating AD; only the SB-specific review/approval workflow UI and manufacturer-vs-mandated distinction logic are deferred. No schema change is required to turn v0.1's SB rows from inert to active.
- **Modification**, **Repair** — deferred; `ComponentInstallation` already supports the linkage point (`Aircraft Configuration`) SBs will eventually mutate.
- **Finding** — QA/audit finding workflow deferred; MVP only needs assessments + evidence.
- **Task** — work-assignment/workflow layer deferred; MVP surfaces "action required" as a field on the assessment.
- **Notification** — deferred; no real-time alerting in v0.1, dashboard is pull-based.

## 4. PostgreSQL Schema Proposal

All tenant tables carry `organization_id` (see §9). Timestamps are `timestamptz`, IDs are `uuid`.

```sql
-- Tenancy & Identity
organizations(id, name, created_at)
roles(id, name, permissions jsonb)               -- seeded, global catalog
users(id, organization_id, email, hashed_password, full_name, is_active, created_at)
user_roles(user_id, role_id, organization_id)

-- Aviation reference data (mostly organization-scoped for tenant-entered fleet data;
-- regulatory catalog data is global/shared, org_id nullable = global)
regulatory_authorities(id, code, name)             -- FAA, EASA, ...
aircraft_types(id, manufacturer, model, type_certificate_no)
engines(id, aircraft_id, manufacturer, model, serial_number, position)
components(id, part_number, description, manufacturer)
component_installations(id, aircraft_id, component_id, serial_number,
                         installed_at, removed_at, position)

-- Fleet
aircraft(id, organization_id, registration, serial_number, aircraft_type_id,
         manufacture_date, status, created_at, updated_at)

-- Regulatory content (§4a: provenance is first-class, version history preserved)
regulatory_documents(id, regulatory_authority_id, doc_type, doc_number, title,
                      revision, publication_date, effective_date, source_url,
                      retrieved_at, content_hash, language, raw_storage_key,
                      supersedes_id, superseded_by_id, source_status,
                      -- source_status: DRAFT | PUBLISHED | SUPERSEDED | WITHDRAWN
                      status, created_at)
                      -- UNIQUE (regulatory_authority_id, doc_number, revision):
                      -- each revision is its own immutable row, never overwritten.
                      -- "what did we have at time T" = documents WHERE retrieved_at <= T
                      -- AND (superseded_by_id IS NULL OR superseded revision's
                      -- effective_date > T).

regulatory_requirements(id, regulatory_document_id, requirement_type,
                         -- requirement_type: AD | SB | REGULATION | RULE | AMC | GM
                         --                    | SIB | NOTICE | OTHER  (AD populated in v0.1)
                         requirement_number,   -- e.g. AD number
                         effective_date, compliance_time,
                         references_requirement_id,  -- self-FK: AD -> SB linkage etc.
                         type_metadata jsonb,  -- type-specific fields, schema-free
                         supersedes_id, superseded_by_id, created_at)

-- Applicability & compliance
applicability_rules(id, regulatory_requirement_id, rule_version, predicate jsonb,
                     -- predicate: structured, deterministic condition tree,
                     -- e.g. {"aircraft_type_id": "...", "engine_model": "...",
                     --       "serial_range": [...]}
                     description, effective_date, status, created_at)
compliance_requirements(id, applicability_rule_id, action_description,
                         recurring_interval, created_at)

-- §4b/§5: Immutable, versioned assessment history with explicit
-- system/human/final separation. Never UPDATE a row's outcome fields;
-- a re-evaluation or a human decision always INSERTs a new row referencing
-- the prior one via previous_assessment_id, forming a linked history per
-- (aircraft_id, regulatory_requirement_id).
applicability_assessments(
  id, organization_id, aircraft_id, regulatory_requirement_id, applicability_rule_id,
  previous_assessment_id,             -- self-FK; NULL for the first assessment in a lineage
  -- SYSTEM DETERMINATION
  system_result,                      -- APPLICABLE | NOT_APPLICABLE | REVIEW_REQUIRED | INSUFFICIENT_DATA
  confidence, reasoning jsonb,
  rule_version, regulatory_document_version, data_version,
  -- data_version: hash/version marker of the aircraft snapshot used
  evaluated_by_engine_version, evaluated_at,
  -- HUMAN REVIEW / DECISION (nullable until a human acts)
  human_decision,                     -- ACCEPTED | OVERRIDDEN | PENDING | NULL
  human_decision_by, human_decision_at,
  override_reason, override_evidence_id,
  -- FINAL
  final_status,                       -- ACTION_REQUIRED | NO_ACTION | REVIEW_REQUIRED | INSUFFICIENT_DATA
  human_review_required,
  change_reason,                      -- REGULATORY_REVISION | CONFIG_CHANGE | COMPONENT_CHANGE
                                       -- | RULE_CHANGE | NEW_EVIDENCE | DATA_CORRECTION | NULL (initial)
  assessment_version, created_at
)
-- "what changed between assessments" = diff current row against
-- previous_assessment_id row, surfaced via change_reason + reasoning delta.

-- Evidence & maintenance
maintenance_records(id, organization_id, aircraft_id, performed_at, description,
                     component_id, regulatory_requirement_id, storage_key, created_at)
evidence(id, organization_id, applicability_assessment_id, maintenance_record_id,
         type, storage_key, description, uploaded_by, created_at)

-- Audit
audit_events(id, organization_id, user_id, action, entity_type, entity_id,
             metadata jsonb, created_at)
```

Indexes: `(organization_id)` on every tenant table; `(aircraft_id, regulatory_requirement_id, created_at desc)` on `applicability_assessments` for latest-status/lineage lookups; `(previous_assessment_id)` for history-chain traversal; `(regulatory_authority_id, doc_number, revision)` unique on `regulatory_documents`; GIN index on `applicability_rules.predicate`.

Migrations via Alembic, one migration per logical change, reviewed like code.

## 5. Neo4j Graph Model

Nodes mirror Postgres primary entities (same UUIDs as `id` property — never re-derived), relationships model traversal-heavy queries Postgres joins would make expensive:

```
(:Aircraft {id})-[:OF_TYPE]->(:AircraftType {id})
(:Aircraft)-[:HAS_ENGINE]->(:Engine)
(:Aircraft)-[:HAS_COMPONENT_INSTALLATION]->(:ComponentInstallation)-[:INSTALLS]->(:Component)
(:RegulatoryDocument)-[:DEFINES]->(:RegulatoryRequirement)
(:RegulatoryRequirement)-[:REFERENCES]->(:RegulatoryRequirement)   -- e.g. AD -> SB
(:ApplicabilityRule)-[:EVALUATES]->(:RegulatoryRequirement)
(:ApplicabilityRule)-[:APPLIES_TO]->(:AircraftType|:Engine|:Component)
(:ApplicabilityAssessment)-[:ASSESSES]->(:Aircraft)
(:ApplicabilityAssessment)-[:EVALUATED_AGAINST]->(:ApplicabilityRule)
(:ApplicabilityAssessment)-[:SUPERSEDES]->(:ApplicabilityAssessment)   -- history lineage
(:ApplicabilityAssessment)-[:SUPPORTED_BY]->(:Evidence)
(:Evidence)-[:SOURCED_FROM]->(:RegulatoryDocument)
```

Purpose in MVP: given a component/engine change, find all `ApplicabilityRule`s whose `APPLIES_TO` target intersects the changed configuration — this becomes the trigger list for reassessment. The graph is rebuildable at any time from Postgres (source of truth); it is a read-optimized index, not a second ledger.

## 6. API Specification (MVP)

Base path `/api/v1`. Auth: Bearer JWT, `organization_id` embedded in token claims and enforced server-side on every query (never trust client-supplied org id).

**Core endpoint:**

```
POST /api/v1/applicability/evaluate
Request:
{
  "aircraft_id": "uuid",
  "regulatory_requirement_id": "uuid"
}

Response: 200
{
  "assessment_id": "uuid",
  "previous_assessment_id": "uuid | null",
  "system_result": "APPLICABLE" | "NOT_APPLICABLE" | "REVIEW_REQUIRED" | "INSUFFICIENT_DATA",
  "confidence": 0.97,
  "reasoning": [
    { "step": "rule_matched", "rule_id": "uuid", "detail": "..." },
    { "step": "data_point", "field": "engine.model", "value": "...", "source": "aircraft_record" }
  ],
  "regulatory_source": {
    "document_id": "uuid", "requirement_id": "uuid", "requirement_type": "AD",
    "requirement_number": "...", "document_revision": "...", "citation_url": "..."
  },
  "aircraft_data_used": { "aircraft_type_id": "...", "engine_ids": [...], "component_installation_ids": [...] },
  "rule_version": "...", "regulatory_document_version": "...", "data_version": "...",
  "required_action": "string | null",
  "evidence": [ { "evidence_id": "uuid", "type": "...", "description": "..." } ],
  "human_decision": "ACCEPTED" | "OVERRIDDEN" | "PENDING" | null,
  "final_status": "ACTION_REQUIRED" | "NO_ACTION" | "REVIEW_REQUIRED" | "INSUFFICIENT_DATA",
  "human_review_required": true,
  "change_reason": "REGULATORY_REVISION" | "CONFIG_CHANGE" | "COMPONENT_CHANGE" | "RULE_CHANGE" | "NEW_EVIDENCE" | "DATA_CORRECTION" | null,
  "assessment_version": "engine-1.2.0",
  "created_at": "iso8601"
}
```

Note: this endpoint always produces a **system determination**; `human_decision`/`final_status` start `PENDING`/mirroring the system result until a human acts. A separate endpoint records the human decision:

```
POST /api/v1/applicability/assessments/{assessment_id}/decision
Request: { "decision": "ACCEPTED" | "OVERRIDDEN", "final_status": "...", "reason": "string (required if OVERRIDDEN)", "evidence_id": "uuid | null" }
```

This always inserts a new `applicability_assessments` row (`previous_assessment_id` = the one being decided on) rather than mutating the system row — the system determination is immutable once written (§5, ADR-005).

Supporting endpoints: `GET /aircraft`, `GET /aircraft/{id}`, `GET /regulatory-documents/{id}`, `GET /regulatory-requirements/{id}`, `GET /applicability/assessments?aircraft_id=` (returns current + full lineage), `GET /applicability/assessments/{id}/diff` (diff against `previous_assessment_id`), `POST /evidence`, `GET /evidence/{id}`, `POST /ai/explain` (takes an `assessment_id`, returns AI-generated plain-language explanation, clearly labeled and non-authoritative), `GET /dashboard/summary`.

`human_review_required=true` whenever confidence < threshold, predicate has an unresolved/ambiguous branch, or `INSUFFICIENT_DATA`/`REVIEW_REQUIRED` result. The AI layer has no path to set `human_decision` or `final_status` (§5, §7).

## 7. Repository Structure

```
aerocomply/
  backend/
    app/
      api/v1/            # routers only, thin
      services/          # orchestration/business logic
      rules_engine/       # deterministic predicate evaluator, pure functions, heavily unit-tested
      graph/              # Neo4j client + sync from Postgres outbox
      ai/                 # RAG/explanation layer, isolated, read-only DB access
      document_intel/     # ingestion parsers, human-review queue
      models/             # SQLAlchemy models
      schemas/            # Pydantic request/response
      db/                 # session, migrations (alembic/)
      core/               # config, security, logging
    tests/
      unit/
      integration/
    alembic/
  frontend/
    app/                  # Next.js app router
      (dashboard)/
      aircraft/
      regulations/
      compliance/
      evidence/
      copilot/
      reports/
      settings/
    components/
    lib/
    tests/
  infra/
    docker-compose.yml
    migrations-ci/
  docs/
    FOUNDATION.md
    adr/                  # architecture decision records
```

## 8. Security Model

- Auth: JWT (short-lived access + refresh), password hashing via argon2/bcrypt.
- RBAC enforced at the service layer via a permission-check decorator, not just UI hiding; roles map to explicit permission strings (e.g. `compliance:assess`, `evidence:upload`).
- All queries scoped by `organization_id` pulled from the authenticated token, applied as a mandatory filter in the repository layer (never optional).
- File uploads (evidence, regulatory PDFs) go to S3-compatible storage with per-object tenant-prefixed keys and signed URLs, never public buckets.
- All mutating actions logged to `audit_events`.
- Secrets via environment/secret manager, never in repo.

## 9. Multi-Tenancy Strategy

Shared database, shared schema, `organization_id` column on every tenant-scoped table (row-level isolation) — chosen over schema-per-tenant or DB-per-tenant for MVP simplicity and easier cross-tenant regulatory-catalog sharing (regulatory documents/ADs are global reference data, not tenant-owned). Enforcement: a repository-layer base class injects the `organization_id` filter automatically; Postgres Row-Level Security (RLS) policies added as defense-in-depth once the app-layer path is proven, using a session-set `app.current_org_id`. Global tables (`regulatory_authorities`, `regulatory_documents`, `regulatory_requirements`, `applicability_rules`) are shared across tenants by design — every org sees the same regulatory truth; only `aircraft`, `applicability_assessments`, `evidence`, `maintenance_records`, `audit_events` are tenant-owned.

## 10. AI Architecture

Strict separation: the AI layer is invoked **after** the rules engine has already produced a `ApplicabilityAssessment`'s `system_result`, and it has no path to `human_decision`/`final_status` (§5, ADR-005). Its jobs:

1. **Explanation**: given a computed assessment (system result, reasoning steps, cited rule/requirement/document), generate a plain-language narrative citing exactly those inputs — grounded generation, not free generation.
2. **Copilot Q&A (RAG)**: retrieval over stored regulatory document text + the user's own assessments/evidence, answering questions with inline citations back to `RegulatoryDocument`/`RegulatoryRequirement`/`ApplicabilityAssessment` records.
3. **Investigation assistance**: summarize, compare across assessments/lineage, and identify missing information (e.g. "no evidence linked to this assessment") — always presented as assistance, never as a status change.

Guardrails enforced in code (not just prompting):
- AI responses are tagged by category in the API response: `verified_fact`, `system_conclusion`, `ai_interpretation`, `uncertain` — the frontend renders these with distinct visual treatment.
- The AI has no database write access to `applicability_assessments` (`system_result`, `human_decision`, or `final_status`), `applicability_rules`, `regulatory_requirements`, or anything feeding the rules engine.
- Every AI response referencing a regulation must resolve to an actual `regulatory_document_id`/`regulatory_requirement_id` in Postgres; if retrieval finds nothing, the AI must say so rather than fill the gap.
- The AI must never certify an aircraft, issue a CRS, or override an authorized engineer — enforced by omission: no such write path exists for the AI service identity.

## 11. Regulatory-Document Ingestion Architecture

Pipeline: raw file uploaded to S3 → `document_intel` parser extracts structured candidates (doc number, revision, dates, applicability text spans, referenced type/part numbers) → candidates land in a review queue table (`status='pending_review'`) → a Compliance/CAMO Manager confirms or edits → confirmation writes an immutable, versioned `RegulatoryDocument` row plus derived `RegulatoryRequirement`/`ApplicabilityRule` rows → triggers the outbox → Neo4j sync. Every ingested document captures full provenance (§4a: authority, doc number, revision, publication/effective dates, source URL, retrieval timestamp, content hash, language, supersedes/superseded_by, source status) so "what did AeroComply know at time T" is always answerable. No auto-publish path exists from parser output to authoritative tables.

## 12. Applicability-Engine Architecture

Pure, deterministic, versioned function: `evaluate(rule.predicate, aircraft_snapshot) -> (system_result, confidence, reasoning[])`. Predicate is a structured JSON condition tree (type/model/serial-range/engine/component matchers, boolean combinators) — no code generation, no LLM in this path. `aircraft_snapshot` is assembled by the service layer from Postgres at evaluation time (current type, engines, installed components) and hashed into `data_version` for reproducibility. The engine is versioned (`assessment_version`/`evaluated_by_engine_version`) so historical assessments remain reproducible/auditable even as rule logic evolves; each engine version is unit-tested against a fixture library of known aircraft/rule combinations before deployment. The engine only ever writes the SYSTEM DETERMINATION fields of a new `applicability_assessments` row — it never touches `human_decision`/`final_status` on an existing row (§5).

## 13. Test Strategy

- **Rules engine**: exhaustive unit tests per predicate operator + fixture-based scenario tests (known aircraft configs × known rules → expected result), since this is the core compliance-correctness surface.
- **API**: integration tests against a real Postgres test database (testcontainers), covering tenant-isolation (cross-org access must fail), auth/RBAC boundaries, and the full `/applicability/evaluate` contract.
- **AI layer**: tests assert citation presence and category tagging, not "correctness" of prose — golden-response tests for grounding, not generation quality.
- **Graph sync**: tests verify Neo4j state is derivable/rebuildable from Postgres (idempotent sync).
- **Frontend**: component tests (RTL) for assessment/evidence views ensuring uncertainty/human-review indicators always render when applicable; e2e (Playwright) for the login → aircraft → evaluate → view assessment path.
- CI runs migrations + full suite on every PR; no merge without green rules-engine tests.

## 14. MVP Scope (v0.1)

- Org/user/RBAC auth
- Aircraft, engine, component, component-installation CRUD (manual entry, no external feed integration)
- Regulatory document ingestion with human-in-the-loop review (`RegulatoryRequirement.requirement_type = AD` populated; other types reserved in the enum)
- Applicability rules authored/confirmed by humans, evaluated deterministically
- `/applicability/evaluate` endpoint + persisted, versioned, immutable `ApplicabilityAssessment` history with system/human/final separation
- `POST /applicability/assessments/{id}/decision` for the human decision step (§5)
- Evidence upload/linking
- Dashboard (fleet count, applicable/action-required/review-required/overdue counts — computed from `applicability_assessments.final_status`, "recent regulatory changes" from `regulatory_documents.publication_date`, "missing evidence" as assessments with zero linked evidence)
- AI copilot: explain-an-assessment + basic RAG Q&A over ingested documents
- Full audit logging of mutations, including every human decision/override

## 15. Deferred Functionality

- SB-specific review/approval workflow UI and manufacturer-vs-mandated distinction logic (the `RegulatoryRequirement.requirement_type='SB'` row shape and `AD → SB` reference chain already exist — see §3), Modification/Repair ledger, Finding workflow, Task/workflow engine, Notification/alerting, automated reassessment triggers on config change (graph supports it structurally, but the trigger/orchestration job is deferred), external OEM/regulator data feed integrations, SSO/SCIM, fine-grained field-level permissions, offline/mobile.

## 16. Key Technical Risks

- **Predicate expressiveness**: real AD applicability logic can be more complex than a simple condition tree (date ranges combined with serial exceptions, "unless already modified by SB X"); risk of the JSON predicate schema needing iteration. Mitigate by versioning rules and keeping the evaluator pluggable per operator type.
- **Postgres/Neo4j drift**: outbox-based sync must be reliable; risk of stale graph data. Mitigate with periodic reconciliation job + graph fully rebuildable from Postgres.
- **AI overreach**: prompt/UX must consistently prevent the AI from being read as authoritative. Mitigate with enforced response schema (category tags) at the API level, not just prompt instructions.
- **Document parsing accuracy**: OCR/extraction from AD/SB PDFs is inherently noisy. Mitigated structurally by mandatory human review before anything becomes authoritative — parsing quality affects reviewer workload, not correctness.
- **Multi-tenancy leakage**: single missed `organization_id` filter is a severe bug class. Mitigate with repository-layer enforcement + RLS as defense-in-depth + integration tests specifically targeting cross-tenant access.

## 17. Development Milestones (amended sequence, per CTO directive)

1. **M0 — Engineering Foundation**: repo structure, Docker/dev environment, FastAPI + Next.js foundations, PostgreSQL + migrations, config management, auth, RBAC, multi-tenancy, structured logging, error handling, API versioning, health checks, testing framework, linting/formatting, basic CI, security baseline.
2. **M1 — Aviation Domain Model**: Organization/User/Role, AircraftType/Aircraft/Engine/Component/ComponentInstallation, RegulatoryAuthority/RegulatoryDocument/RegulatoryRequirement/ApplicabilityRule/ApplicabilityAssessment schemas + migrations + CRUD, frontend list/detail screens.
3. **M2 — Regulatory Ingestion**: document upload, provenance capture (§4a), parser candidate extraction, human review queue, confirmation → authoritative `RegulatoryDocument`/`RegulatoryRequirement` rows.
4. **M3 — Rules Engine**: deterministic predicate evaluator, ApplicabilityRule authoring, versioning, fixture-based test library.
5. **M4 — Applicability API**: `/applicability/evaluate`, `/applicability/assessments/{id}/decision`, immutable assessment history + lineage/diff endpoints, assessment detail screen with system/human/final states visible.
6. **M5 — Evidence Intelligence**: Evidence upload/linking, evidence↔assessment traceability, dashboard aggregates, missing-evidence surfacing.
7. **M6 — AI Explanation Layer**: explanation endpoint + basic RAG copilot, category-tagged responses, frontend copilot screen.

Do not build deferred product features (§15) before these seven foundations are stable. Each milestone ends with an explicit report before the next begins — no automatic progression.

---

## Human Decision Boundary (first-class domain concept)

Lifecycle, enforced as distinct fields/states rather than a single mutable status column:

```
SYSTEM DETERMINATION  →  HUMAN REVIEW  →  HUMAN DECISION  →  FINAL COMPLIANCE STATUS
   (system_result,          (surfaced          (human_decision:         (final_status:
    confidence,               when human_        ACCEPTED |               ACTION_REQUIRED |
    reasoning)                review_required)    OVERRIDDEN |             NO_ACTION |
                                                   PENDING)                REVIEW_REQUIRED |
                                                                           INSUFFICIENT_DATA)
```

Example: system says `APPLICABLE` at confidence 0.96; a Compliance Manager reviews and `ACCEPTS`, setting `final_status = ACTION_REQUIRED`. Or: system says `APPLICABLE`; an authorized engineer `OVERRIDES` with a documented reason (e.g. "component already replaced per SB-1234, evidence attached") and a linked `evidence_id`, setting `final_status = NO_ACTION`.

Rules:
- `system_result` is written once by the rules engine and never mutated.
- `human_decision`/`human_decision_by`/`human_decision_at`/`override_reason` are written only by an authenticated, authorized human user via `POST /applicability/assessments/{id}/decision` — never by the AI service identity, never as a side effect of an explanation request.
- An `OVERRIDDEN` decision requires a non-empty `override_reason`; supporting evidence is required whenever the override changes `final_status` away from what `system_result` would imply.
- Every decision call writes an `AuditEvent` capturing user identity, timestamp, and reason.
- The AI may be asked to *summarize* an assessment or *flag* that human review is pending, but has no code path that can write `human_decision` or `final_status`.

## Architecture Decision Records

Six ADRs formalize the decisions above; each follows Context / Decision / Alternatives Considered / Consequences / Reversal Conditions:

- [ADR-001 — Modular Monolith Architecture](docs/adr/ADR-001-modular-monolith.md)
- [ADR-002 — PostgreSQL as Source of Truth](docs/adr/ADR-002-postgresql-source-of-truth.md)
- [ADR-003 — Neo4j as Rebuildable Derived Knowledge Graph](docs/adr/ADR-003-neo4j-derived-graph.md)
- [ADR-004 — LLM Is Not the Compliance Decision Engine](docs/adr/ADR-004-llm-not-decision-engine.md)
- [ADR-005 — Human Decision Boundary and Auditability](docs/adr/ADR-005-human-decision-boundary.md)
- [ADR-006 — Regulatory Requirement as Core Domain Abstraction](docs/adr/ADR-006-regulatory-requirement-core-abstraction.md)

## M0 Verification-Gate Addenda (2026-08-29)

### Request Tracing
Implemented in [backend/app/core/request_context.py](backend/app/core/request_context.py): `RequestContextMiddleware` assigns/propagates a `request_id` (from `X-Request-ID` or generated) and binds it into structlog contextvars for the request's lifetime, so every log line — not just a manually-annotated one — carries `request_id` and `endpoint`. `bind_request_identity()` is called from `get_current_user` (app/core/deps.py) once a bearer token is decoded, adding `organization_id`/`user_id` to that same context. The completion log line additionally carries `status_code` and `duration_ms`. This satisfies the five required fields (request_id, organization_id, user_id, endpoint, status_code, duration) without threading them through every function signature.

### Audit Immutability
`audit_events` is enforced append-only at the **database** level, not merely by application convention: migration `0002_audit_events_immutability` adds a Postgres trigger (`reject_audit_event_mutation`) that raises on any `UPDATE` or `DELETE` against the table, regardless of which credential or code path attempts it. [tests/integration/test_audit_immutability.py](backend/tests/integration/test_audit_immutability.py) exercises both paths and expects the DB to reject them. The application layer independently never issues update/delete against this table (`app/services/audit_service.py` is insert-only).

### PostgreSQL RLS Readiness (confirmed, not implemented)
The schema and access pattern were checked against RLS adoption without an application rewrite:
- Every tenant-owned table already carries a plain `organization_id` column (§9) — RLS policies attach directly to that column with no schema change.
- The application already never trusts a client-supplied `organization_id` (it's read only from the JWT in `get_current_user`) — adding `SET app.current_org_id = ...` at the start of each request's DB session and a matching `USING (organization_id = current_setting('app.current_org_id')::uuid)` policy per table is additive: it doesn't change any existing query, it only adds a second enforcement layer beneath the app-layer filter.
- Global/shared tables (regulatory catalog data) simply get no RLS policy, or an `ALL ROLES` read policy — no conflict with tenant-owned tables using RLS.
- **Confirmed**: adding RLS is a migration + a session-variable-setting hook in `get_db_session`, not an application rewrite. Deferred to a later milestone per your explicit instruction not to over-engineer M0.

### Refresh-Token Security (current state + roadmap)
**Current (M0) implementation**: refresh tokens are stateless signed JWTs (`type: refresh`, 7-day expiry, HS256), validated only by signature + expiry in `app/core/security.py` / `app/services/auth_service.refresh_access_token`. There is **no server-side session record** — meaning:
- No revocation: a leaked/stolen refresh token remains valid until it naturally expires; there is no way to invalidate it early.
- No rotation: calling `/auth/refresh` repeatedly with the same refresh token is not detected or prevented (no reuse-detection).
- No session tracking: the system cannot answer "what active sessions does this user have" or "log out all devices."

**Roadmap (not implemented in M0, by design — flagged here per your instruction to document rather than build now)**:
1. **Token rotation**: on each `/auth/refresh` call, issue a new refresh token and invalidate the old one (store a hash + `family_id` server-side; detect reuse of an already-rotated token as a signal of compromise).
2. **Revocation**: a `refresh_tokens` table (`id`, `user_id`, `token_hash`, `family_id`, `issued_at`, `expires_at`, `revoked_at`) — checking this table on every refresh call turns the current pure-JWT scheme into a hybrid (JWT for access tokens, opaque/DB-tracked for refresh tokens), which is the standard pattern.
3. **Session tracking**: once refresh tokens are DB-backed, "active sessions" and "log out everywhere" become simple queries/updates against that table.
4. **Expiration**: already implemented (7 days); rotation makes the effective exposure window per-token much shorter in practice.

This is intentionally deferred — the fix is well-understood and additive (a new table + a lookup on refresh), not an architecture change, so it does not block M0 sign-off but must not be forgotten before production traffic.

## Assumptions

- Initial regulatory scope is FAA ADs (extensible to EASA later); rule predicates are authored/reviewed by humans, not auto-generated.
- Single-region deployment for MVP; no multi-region/DR requirement yet.
- "Evidence" in MVP means uploaded documents/records, not live sensor/telemetry data.

---

Per the stated development method, this document is a proposal awaiting your approval before any implementation begins. Flag anything you want changed — schema fields, entity scope, API shape, or milestone order — and I'll revise before we start M0.

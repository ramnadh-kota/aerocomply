# DEVELOPER 2 — MILESTONE D2-2 ARCHITECTURAL & IMPLEMENTATION SPECIFICATION
## Compliance Obligation & Evidence Digital Thread

**Platform:** KOTA Aerospace / AeroComply  
**Author:** Developer 2 (Compliance, Rules, Applicability, Evidence & Intelligence Lead)  
**Milestone:** D2-2 — Compliance Obligation + Evidence Digital Thread  
**Date:** September 2026  
**Status:** IMPLEMENTED & VERIFIED  

---

## 1. Domain Model

Milestone D2-2 establishes the authoritative digital thread linking regulatory mandates to verified physical and technical evidence:

```
REGULATORY REQUIREMENT
          ↓
  APPLICABILITY RULE
          ↓
APPLICABILITY EVALUATION (Kleene 3-Valued Logic & Immutable Snapshot)
          ↓
COMPLIANCE OBLIGATION (Idempotent per Asset/Aircraft)
          ↓
   REQUIRED ACTION
          ↓
  EVIDENCE ARTIFACTS
          ↓
VERIFICATION WORKFLOW (Independent Inspector / Authorized Signoff)
          ↓
   COMPLIANCE STATE (Deterministic Determinant)
```

### Core Entities

1. **`ComplianceObligation`** (`backend/app/models/compliance.py`):
   - Represents: *"Requirement X applies to Asset Y and must be satisfied."*
   - Table: `compliance_obligations`
   - Attributes:
     - `id`: UUID (Primary Key)
     - `organization_id`: UUID (Tenant isolation)
     - `requirement_id`: UUID (FK -> `regulatory_requirements.id`)
     - `rule_id`: UUID | None (FK -> `applicability_rules.id`)
     - `asset_id`: UUID | None (FK -> `assets.id`)
     - `aircraft_id`: UUID | None (FK -> `aircraft.id`)
     - `applicability_evaluation_id`: UUID | None (FK -> `applicability_evaluations.id`)
     - `status`: `ComplianceState` enum (10 deterministic lifecycle states)
     - `priority`: `Priority` enum (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`)
     - `due_date`: Date | None
     - `recurrence`: String | None (e.g. `P1Y`, `P100H`, `P500C`)
     - `responsible_role`: String | None (e.g. `CHIEF_INSPECTOR`, `MAINTENANCE_ENGINEER`)
     - `responsible_user_id`: UUID | None
     - `required_action`: Text (Action mandated by the authority or standard)
     - `evidence_requirements`: JSONB (List of required evidence type specifications)
     - `completed_at`: Timestamp | None
     - `verified_at`: Timestamp | None
     - `notes`: Text | None
     - `created_at`, `updated_at`: Timestamps

2. **`Evidence`** (`backend/app/models/evidence.py`):
   - First-class polymorphic domain model linking evidence to any technical record.
   - Table: `evidence`
   - Extended Attributes:
     - `compliance_obligation_id`: UUID | None (FK -> `compliance_obligations.id`)
     - `regulatory_requirement_id`: UUID | None (FK -> `regulatory_requirements.id`)
     - `asset_id`: UUID | None (FK -> `assets.id`)
     - `aircraft_id`: UUID | None (FK -> `aircraft.id`)
     - `component_id`: UUID | None (FK -> `components.id`)
     - `inspection_requirement_id`: UUID | None (FK -> `inspection_requirements.id`)
     - `finding_id`: UUID | None (FK -> `findings.id`)
     - `work_order_id`: UUID | None (FK -> `work_orders.id`)
     - `task_id`: UUID | None (FK -> `tasks.id`, nullable for standalone compliance evidence)
     - `title`: String(255)
     - `description`: Text
     - `evidence_type`: String(64) (`INSPECTION_RECORD`, `MAINTENANCE_RECORD`, `NDT_REPORT`, `CERTIFICATE`, `LOGBOOK_ENTRY`, `OEM_DOCUMENT`, `OTHER`)
     - `source`: String(255) (e.g. `NDT Hangar Lab 4`, `FAA Form 8130-3`, `EASA Form 1`)
     - `captured_at`: Timestamp | None
     - `verification_status`: String(32) (`UNVERIFIED`, `VERIFIED`, `REJECTED`)
     - `verifier_user_id`: UUID | None (FK -> `users.id`)
     - `verified_at`: Timestamp | None
     - `verification_notes`: Text | None
     - `rejection_reason`: Text | None
     - `provenance`: JSONB | None

---

## 2. Data Relationships & Schema Migration

Migration **`0047_compliance_obligations_and_evidence_thread.py`** is fully additive and reversible:

### Idempotency & Tenant Safety
- Unique partial indexes ensure at most one active obligation per requirement/asset pair:
  - `uq_compliance_obligations_org_req_aircraft`: `(organization_id, requirement_id, aircraft_id)` where `deleted_at IS NULL AND aircraft_id IS NOT NULL`
  - `uq_compliance_obligations_org_req_asset`: `(organization_id, requirement_id, asset_id)` where `deleted_at IS NULL AND asset_id IS NOT NULL`
- Foreign keys with `ondelete="CASCADE"` or `ondelete="SET NULL"` enforce integrity while preventing orphan records.
- Verified reversibility: `alembic downgrade -1` followed by `alembic upgrade head` cleanly transitions schema forward and backward with zero data corruption.

---

## 3. Compliance State Machine

Deterministic 10-state lifecycle:

| State | Semantic Trigger / Invariant |
|---|---|
| `NOT_EVALUATED` | Requirement assigned or rule exists, but evaluation not yet executed against configuration snapshot. |
| `NOT_APPLICABLE` | Evaluated with Kleene `FALSE` — requirement is deterministically excluded for this asset configuration. |
| `PENDING` | Evaluated `APPLICABLE`, pending schedule or preliminary initiation. |
| `DUE` | Evaluated `APPLICABLE`, future due date or active inspection requirement. |
| `OVERDUE` | `due_date < current_timestamp` and required action/evidence is not yet verified. |
| `IN_PROGRESS` | Technical work initiated, evidence attached, but pending independent verification. |
| `BLOCKED` | **Aerospace Invariant #23**: Missing configuration data produced Kleene `UNKNOWN` (`INSUFFICIENT_DATA`), or technical prerequisite is blocked. |
| `REVIEW_REQUIRED` | Evaluated with `REVIEW_REQUIRED` or human override flagged for authorized review. |
| `COMPLIANT` | Required action completed AND all required evidence verified and accepted. |
| `NON_COMPLIANT` | Evidence rejected, due date expired without accomplishment, or requirement failed. |

### Critical Invariants
1. **`UNKNOWN` MUST NEVER BE TREATED AS FALSE (Invariant #23)**: If configuration parameters cannot be verified (e.g. engine model unknown), the state transitions to `BLOCKED` with detailed missing data explanations. It never silently declares the asset `NOT_APPLICABLE`.
2. **Rejected Evidence Precludes Compliance**: If any attached evidence record is in `REJECTED` status, the obligation is immediately marked `NON_COMPLIANT` with the rejection reason recorded as an active blocker.
3. **Dual Gate Completion**: An obligation only reaches `COMPLIANT` when both the technical action is marked complete AND all evidence requirements have at least one matching `VERIFIED` record.

---

## 4. Applicability Engine Integration

The D2-2 obligation service integrates directly with the D2-1 applicability engine:

- Endpoint: `POST /api/v1/compliance/obligations/{id}/evaluate`
- Workflow:
  1. Retrieves target asset/aircraft configuration snapshot.
  2. Evaluates the condition tree using Kleene 3-valued logic (`TRUE`, `FALSE`, `UNKNOWN`).
  3. Records immutable `ApplicabilityEvaluation` snapshot.
  4. Automatically maps evaluation result:
     - `APPLICABLE` -> Syncs obligation to `DUE`, `OVERDUE`, or `IN_PROGRESS`.
     - `NOT_APPLICABLE` -> Syncs obligation to `NOT_APPLICABLE`.
     - `INSUFFICIENT_DATA` -> Syncs obligation to `BLOCKED`, recording specific missing parameters.
     - `REVIEW_REQUIRED` -> Retains `REVIEW_REQUIRED` until resolved by authorized compliance manager.
  5. Immutability guarantee: Changing aircraft configuration later does not mutate past evaluation records or snapshot reasoning traces.

---

## 5. Evidence Lifecycle & Verification Workflow

```
[Create Evidence]
       ↓
 status: UPLOADED / verification_status: UNVERIFIED
       ↓
┌──────────────────────────────────────┐
│ Verification by Authorized Role      │
│ (COMPLIANCE_MANAGER / ORG_ADMIN)     │
└──────────────────────────────────────┘
       ├── Verify → verification_status: VERIFIED / status: ACCEPTED → Obligation evaluates for COMPLIANT
       └── Reject → verification_status: REJECTED / status: REJECTED → Obligation forced NON_COMPLIANT
```

- **Role Authorization**: Verification and Rejection endpoints enforce `Permission.COMPLIANCE_ASSESS` or `Permission.REGULATION_WRITE`. Ordinary viewers and technicians cannot verify their own evidence.
- **Audit Logging**: Every verification and rejection event generates an immutable audit log entry capturing the verifier ID, timestamp, and notes/rejection reason.

---

## 6. Traceability & Explainability

Every compliance obligation provides complete explainability via `GET /api/v1/compliance/obligations/{id}/traceability`, answering the 7 core questions:

1. **WHY does this requirement apply?**
   - References rule code, title, evaluation result (`APPLICABLE`), evaluation timestamp, and Kleene condition reasoning trace.
2. **WHAT action is required?**
   - Specific action text, priority, due date, recurrence, and responsible role.
3. **WHAT evidence is required?**
   - List of mandated evidence type specifications.
4. **WHAT evidence has been provided?**
   - List of all attached evidence records with titles, sources, types, and capture dates.
5. **HAS it been verified?**
   - Explicit boolean `is_verified`, along with individual verification statuses, verifier names, and timestamps.
6. **WHY is the current compliance state what it is?**
   - Human-readable narrative detailing the exact deterministic derivation.
7. **WHAT is blocking compliance?**
   - Explicit list of active blockers (e.g. `"REJECTED: Ultrasonic scan curves fail ASTM standard"`, `"Missing verified evidence: INSPECTION_RECORD"`, `"Action incomplete"`).

---

## 7. APIs

| Method | Path | Summary | Permission / Entitlement |
|---|---|---|---|
| `GET` | `/api/v1/compliance/overview` | Fleet-wide compliance KPIs & overview | `COMPLIANCE_READ` + `compliance_intelligence` |
| `GET` | `/api/v1/compliance/obligations` | List obligations with status/asset filters | `COMPLIANCE_READ` + `compliance_intelligence` |
| `POST` | `/api/v1/compliance/obligations` | Create compliance obligation | `COMPLIANCE_ASSESS` + `compliance_intelligence` |
| `GET` | `/api/v1/compliance/obligations/{id}` | Get obligation details | `COMPLIANCE_READ` + `compliance_intelligence` |
| `PATCH` | `/api/v1/compliance/obligations/{id}` | Update obligation action/dates/status | `COMPLIANCE_ASSESS` + `compliance_intelligence` |
| `POST` | `/api/v1/compliance/obligations/{id}/evaluate` | Run applicability engine & sync state | `COMPLIANCE_ASSESS` + `compliance_intelligence` |
| `GET` | `/api/v1/compliance/obligations/{id}/traceability` | 7-question explainability response | `COMPLIANCE_READ` + `compliance_intelligence` |
| `GET` | `/api/v1/compliance/obligations/{id}/evidence` | List evidence attached to obligation | `COMPLIANCE_READ` + `compliance_intelligence` |
| `POST` | `/api/v1/compliance/obligations/{id}/evidence` | Attach evidence to obligation | `COMPLIANCE_ASSESS` + `compliance_intelligence` |
| `POST` | `/api/v1/evidence/{id}/verify` | Verify evidence record | `COMPLIANCE_ASSESS` + `compliance_intelligence` |
| `POST` | `/api/v1/evidence/{id}/reject` | Reject evidence record with reason | `COMPLIANCE_ASSESS` + `compliance_intelligence` |

---

## 8. Security & Multi-Tenancy

- **Tenant Isolation**: Every database query is tenant-scoped (`organization_id == current_user.organization_id`). Cross-tenant requests return `404 Not Found` without disclosing record existence.
- **RBAC Enforcement**: Read operations require `Permission.COMPLIANCE_READ`. Mutating actions require `Permission.COMPLIANCE_ASSESS` or `Permission.REGULATION_WRITE`.
- **Feature Entitlements**: Endpoints verify active subscription plan features (`compliance_intelligence` and `compliance_management`).
- **Suspended Organizations**: Blocked at token verification; suspended tenant users are denied access.

---

## 9. Frontend Production Implementation

1. **Compliance Overview** (`frontend/app/(app)/compliance/page.tsx`):
   - Fleet-wide KPI grid: Applicable Requirements, Due Obligations, Overdue, Compliant, Blocked, Review Required, Deterministic Compliance Rate.
   - Interactive obligations table with status filters (`ALL`, `DUE`, `OVERDUE`, `IN_PROGRESS`, `COMPLIANT`, `NON_COMPLIANT`, `BLOCKED`, `REVIEW_REQUIRED`).
   - Links to Obligation Detail digital thread view.

2. **Obligation Detail View** (`frontend/app/(app)/compliance/obligations/[id]/page.tsx`):
   - 6-Stage Digital Thread pipeline visualizer.
   - Applicability intelligence card with Kleene 3-valued reasoning trace.
   - Blocker analysis card highlighting active blockers.
   - Required evidence gates table.
   - Attached evidence list with inline "Verify" and "Reject" workflows.
   - Modal dialogs for attaching new evidence and submitting rejection reasons.

3. **Evidence Detail View** (`frontend/app/(app)/compliance/evidence/[id]/page.tsx` and `frontend/app/(app)/evidence/[id]/page.tsx`):
   - Comprehensive evidence metadata and source system provenance.
   - Linked digital thread entities (Obligation, Requirement, Aircraft, Component, Work Order, Task).
   - Verifier audit details, notes, and rejection explanations.
   - Verification approval and rejection action buttons.

---

## 10. Developer 1 Integration Points

- **Aircraft & Asset Linking**: Uses Developer 1's `Aircraft` and generic `Asset` models. References `registration`, `msn`, and `aircraft_type`.
- **Component Linking**: Links to `Component` and `ComponentInstallation` for serialized sub-assembly applicability and evidence tracking.
- **Work Order & Task Linking**: Evidence model links to Developer 1's `WorkOrder` and `Task` entities without modifying or duplicating them.
- **Backward Compatibility**: `work_order_service.create_task` and `update_task` maintain backward-compatibility with optional `actor_user_id = None`.

---

## 11. Known Limitations & Next Steps

- **Document File Storage**: Evidence records currently store metadata, provenance, and S3 storage keys. Presigned multi-file upload for standalone compliance attachments is handled via existing `/evidence-files` endpoints.
- **Recurring Obligation Generation**: When an obligation with recurrence (`P1Y`) resolves to `COMPLIANT`, automatic creation of the next cycle's obligation can be triggered via scheduled cron or task completion hook in Milestone D2-3.
- **Next Recommended Milestone**: D2-3 — Inspection Intelligence, Finding Correlation & Automated Readiness Gates.

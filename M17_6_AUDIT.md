# M17.6 Readiness Audit — Inspection / Evidence / Compliance / Readiness

Read-only audit. No code, migrations, or config were changed. This file is the only artifact produced.

## 1. Git State

```
Current branch: main
Your branch is ahead of 'origin/main' by 5 commits.
nothing to commit, working tree clean
```

```
git log --oneline -10
f31dbe4 feat(drone): add battery and component maintenance lifecycle
5cfd6d1 test(drone): harden battery and component lifecycle integration
3155f42 feat(drone): add battery and component lifecycle UI
b1e26cb feat(drone): add battery and component lifecycle APIs
41cf849 chore(m17.2a): fix ruff import-order and line-length violations
eddae03 fix(deploy): normalize DATABASE_URL scheme to psycopg 3 dialect
0ff40fd M17.2A: Add serialized component lifecycle foundation
0ca5df6 feat: add drone operations foundation
49e3231 feat: migrate mro relationships to assets
bc4086b feat: add facilities foundation
```

`git diff --stat` produced no output — no uncommitted changes anywhere in the tree. M17.5 (`f31dbe4`) is confirmed committed and is `HEAD`. No other uncommitted work was found or touched.

## 2. Existing Architecture Summary

| Domain | What exists | Files |
|---|---|---|
| **Inspection** | Single `InspectionRequirement` model covering both plain checklist review (`required=False`) and RII/Required-Inspection-Item (`required=True`), with a server-enforced independence rule (inspector must not be a technician who uploaded evidence for the same task). Full lifecycle service + REST API. | `backend/app/models/inspection_requirement.py`, `backend/app/services/inspection_service.py`, `backend/app/api/v1/inspections.py`, `backend/app/schemas/inspection.py` |
| **Checklist** | No separate "Checklist" model exists. The `required=False` branch of `InspectionRequirement` *is* the checklist-review path (see `inspection_requirement.py:11-25` docstring). No distinct checklist-template/checklist-item persistence exists server-side (that only exists as frontend mock data, `frontend/lib/mock/checklists.ts`). | `backend/app/models/inspection_requirement.py:11-25` |
| **Evidence** | `Evidence` (status lifecycle record) + `EvidenceFile` (physical object-storage metadata, S3/MinIO-backed, with presigned download and soft-delete) + a separate reconciliation service for DB/storage drift. Real upload/download/delete flow is implemented and wired to `StorageService`. | `backend/app/models/evidence.py`, `backend/app/services/evidence_service.py`, `backend/app/services/evidence_file_service.py`, `backend/app/services/evidence_reconciliation_service.py`, `backend/app/api/v1/evidence.py`, `backend/app/schemas/evidence.py` |
| **Compliance** | `RegulatoryRequirement` (a single citable requirement — explicitly **not** a rules engine, see `compliance.py:20-29`) + `ComplianceAssessment` (a manually recorded/overridable per-aircraft determination). CRUD + override + per-aircraft analytics (status counts only). | `backend/app/models/compliance.py`, `backend/app/services/compliance_service.py`, `backend/app/api/v1/compliance.py`, `backend/app/schemas/compliance.py` |
| **Requirements/Applicability** | Three separate, non-overlapping requirement concepts exist (see §12): `MaintenanceRequirement`/`MaintenanceRequirementApplicability` (interval-driven due-status engine, aircraft/asset/battery/component applicability), `PartRequirement` (parts-availability tracking per task/work order), and `RegulatoryRequirement`/`ComplianceAssessment` (citable regulation + manual assessment). There is no unified "Requirement" base class or condition-tree applicability engine. | `backend/app/models/maintenance_requirement.py`, `backend/app/models/part_requirement.py`, `backend/app/models/compliance.py` |
| **Readiness / ReleaseReadiness** | Two independent readiness concepts exist, not one: (a) `release_readiness_service.get_release_readiness_for_work_order` — work-order-level, aggregates Task execution_state + Evidence gate + InspectionRequirement gate into `EVIDENCE`/`INSPECTION`/`TASK_EXECUTION` blockers; (b) `readiness_service.evaluate_deployment_readiness` — drone/asset-level "deployment readiness" (battery status, overdue maintenance, failed inspection, drone active status). These are different domains (MRO work-order release vs. drone flight-readiness) that happen to share the word "readiness" — see §12. | `backend/app/services/release_readiness_service.py`, `backend/app/services/readiness_service.py`, `backend/app/api/v1/release_readiness.py`, `backend/app/schemas/release_readiness.py` |
| **Audit** | Generic `AuditEvent` model + `record_audit_event`/`list_audit_events` service, used consistently by inspection/evidence/compliance/part-requirement services as an in-transaction side-write (no separate commit). Platform-level read exposed via a separate `platform.py` endpoint (not in scope list, referenced only). | `backend/app/services/audit_service.py:17-94` |

## 3. Capability Matrix — Inspection

| Capability | Status | Location | Notes |
|---|---|---|---|
| Create inspection requirement (checklist or RII) | COMPLETE | `inspection_service.py:210-237`, `POST /inspections` (`inspections.py:21-35`) | Verifies `task_id`/`work_order_id` belong to caller's org before attaching (`inspection_service.py:221-226`). |
| Get by id (tenant-scoped) | COMPLETE | `inspection_service.py:240-251` | `NotFoundError` if cross-tenant; safe-not-found convention. |
| List by work order | COMPLETE | `inspection_service.py:254-264`, `GET /inspections/by-work-order/{id}` | No pagination — returns full list. |
| State machine (PENDING→COMPLETED/NOT_REQUIRED/REJECTED, REJECTED→PENDING) | COMPLETE | `inspection_service.py:48-70`; unit-tested `test_inspection_lifecycle.py:35-59` | Terminal states enforced; illegal skip/self-transition rejected. |
| RII independence enforcement | COMPLETE | `inspection_service.py:82-118`; tested `test_inspection_lifecycle.py:96-142`, `test_inspection_completion_identity_api.py:64-152` | Independence derived from `Evidence.uploaded_by_user_id` on the same task — explicitly a best-effort heuristic (no `assigned_technician` field exists), documented as such. Skips the check when no evidence exists yet (cannot fabricate a technician). |
| Cross-tenant `inspector_user_id` guard | COMPLETE | `inspection_service.py:34-46`; tested `test_inspection_completion_identity_api.py:93-113` | Explicit membership check before attribution. |
| Completion gate helper for downstream aggregation | COMPLETE | `inspection_service.py:73-79`, consumed by `release_readiness_service.py:44-47,130-141` | |
| Checklist templates / checklist items (distinct from RII) | MISSING (backend) / FRONTEND ONLY (mock) | `frontend/lib/mock/checklists.ts`, `frontend/components/maintenance/ChecklistPanel.tsx` | No backend model/table; only the mock/demo layer models multi-item checklists. |
| RII/Inspection UI wired to real API | PARTIAL | `frontend/lib/api/inspections.ts` exists and is real-mode, but `frontend/app/(app)/maintenance/inspections/page.tsx` and `[id]/page.tsx` were not confirmed to consume it exclusively (large amount of the app still runs on `frontend/lib/mock/*`) | Needs direct verification per-page; flagged PARTIAL rather than asserted. |
| Pagination on list endpoints | MISSING | `inspections.py:50-59` | Returns unbounded list — consistent with rest of platform (audit_service is the only paginated list found, §7). |

## 4. Capability Matrix — Evidence

| Capability | Status | Location | Notes |
|---|---|---|---|
| Create evidence (tenant + task ownership check) | COMPLETE | `evidence_service.py:113-135` | Cross-tenant task_id → `NotFoundError`; tested `test_tenancy_isolation.py:191-207`. |
| Status lifecycle (REQUIRED→UPLOADED→SUBMITTED→AWAITING_REVIEW→ACCEPTED/REJECTED, REJECTED resubmit) | COMPLETE | `evidence_service.py:31-53`; unit-tested `test_evidence_lifecycle.py` (10 tests) | |
| Completion-gate semantics (`ACCEPTED` only) | COMPLETE | `evidence_service.py:56-59` | Consumed correctly by `release_readiness_service.py:108`. |
| Physical file upload (bounded read, content-type allowlist, SHA-256 checksum, tenant-namespaced storage key) | COMPLETE | `evidence.py` (API) `114-236`; `evidence_file_service.py:84-139` | Allowlist is 3 MIME types (`evidence.py:41`); size cap via `evidence_max_upload_bytes` setting. |
| Presigned download URL (short-lived, server-controlled TTL) | COMPLETE | `evidence.py:258-312` | No client-controlled `expires_in`; only STORED files downloadable (409 otherwise). |
| Soft-delete file (storage delete + DB status, audit event) | COMPLETE | `evidence.py:315-393`; `evidence_file_service.py:271-321` | Storage delete happens before DB mutation; explicit handling of the "deleted from storage but DB commit failed" desync case (logged, not silently swallowed). |
| Cross-tenant / cross-parent file scoping (file must belong to *this* evidence AND *this* org) | COMPLETE | `evidence_file_service.py:197-220` | Verified via code read — two-hop check, not a single `evidence_file_id` lookup. |
| DB/storage reconciliation (drift detection + narrow auto-repair) | COMPLETE (operational tool, not tenant-facing) | `evidence_reconciliation_service.py` (355 lines); tested `test_evidence_reconciliation_service.py` | Only one auto-repair case (`DELETED`+object-still-exists); everything else is `MANUAL_REVIEW`. Invoked via a standalone script, not an HTTP endpoint — by design (module docstring, lines 9-20). |
| Evidence "required" flag per task (distinct rows for required-but-not-yet-uploaded) | MISSING | `models/evidence.py` has no boolean `required` column | `release_readiness_service.py:14-17` explicitly documents this gap: "every existing Evidence row is treated as required... a task with zero Evidence rows is not, by itself, an evidence blocker." This means release-readiness cannot currently detect "evidence that was never even requested." |
| Pagination on evidence-file listing | MISSING | `evidence.py:239-255` | Full list returned; ordered but unbounded. |
| Frontend real-mode wiring | COMPLETE (client layer) | `frontend/lib/api/evidence.ts`, `evidenceFiles.ts`; `frontend/components/evidence/EvidenceFilesPanel.tsx`, `RealTaskGatePanel.tsx` | These are explicitly named "Real*" components, implying a parallel mock-mode path still exists elsewhere in the app (`frontend/lib/mock/evidence.ts`, `evidenceRecords.ts`) — see §12/§15. |

## 5. Capability Matrix — Compliance

| Capability | Status | Location | Notes |
|---|---|---|---|
| Create/list/get `RegulatoryRequirement` (tenant-scoped) | COMPLETE | `compliance_service.py:18-74`; `compliance.py` API `21-61` | |
| Create `ComplianceAssessment` (validates aircraft + requirement ownership) | COMPLETE | `compliance_service.py:77-112` | Also resolves `asset_id` via `resolve_asset_id` for the Phase-1B asset-repointing compatibility column (`compliance.py` model `58-62`). |
| Get/list assessments (by id, by aircraft) | COMPLETE | `compliance_service.py:115-153` | |
| Override with reason + audit trail | COMPLETE | `compliance_service.py:156-185`; gated by distinct `COMPLIANCE_DECIDE` permission (separate from `COMPLIANCE_ASSESS`) | |
| Per-aircraft analytics (status counts) | COMPLETE, deliberately narrow | `compliance_service.py:188-202` | Explicitly documented as the "honest, directly-countable version" — no confidence scores, no condition-tree factors (module docstring `188-195`). |
| Applicability rules engine (AND/OR/NOT over aircraft-type/MSN-range/engine-type) | MISSING (explicitly deferred, not attempted) | `compliance.py` model docstring `20-29` | Documented as "a genuine rules-engine build, not a persistence slice" and deliberately not faked. Frontend mock (`frontend/lib/mock/types.ts` `ApplicabilityCondition`/`ApplicabilityRule`) models this but has no backend equivalent. |
| Regulatory document ingestion (AI/automated regulation parsing) | MISSING (explicitly out of scope, confirmed via `docs/FULL_SYSTEM_AUDIT.md` reference in `frontend/lib/api/compliance.ts:6-12`) | — | Frontend client's own comment states `backend/app/services/ai/tools.py` documents applicability rules as "NOT backend-resident." |
| Cross-tenant get requirement | COMPLETE (tested) | `test_compliance_service.py:189` `test_get_requirement_cross_tenant_raises` | |
| Pagination | MISSING | `compliance.py` API `38-46` | Full list. |

## 6. Capability Matrix — Readiness

| Capability | Status | Location | Notes |
|---|---|---|---|
| Work-order release readiness (Evidence/Inspection/Task-execution blockers) | COMPLETE, explicitly partial in scope | `release_readiness_service.py:58-151`; API `GET /work-orders/{id}/release-readiness` (`release_readiness.py` API, 23 lines) | Module docstring (`release_readiness_service.py:28-32`) explicitly states authorization sign-off and parts/material availability blockers are NOT implemented, and returns a `data_completeness` string saying so on every response (`release_readiness_service.py:51-55,149`). |
| Drone/asset deployment readiness (battery, overdue maintenance, failed inspection, active status) | COMPLETE, separate feature | `readiness_service.py:35-80` | Not exposed under `/work-orders/.../release-readiness`; used by drone-domain callers (module docstring references a future Lisa AI tool, line 3-4). No dedicated REST endpoint was found in the 5 files listed under §7 — likely called internally (e.g. by `drone_service`/AI tools) rather than via a public route in this router set. |
| Parts/material availability as a readiness blocker | MISSING (from release_readiness) / PARTIAL (data exists elsewhere) | `part_requirement.py` model tracks `SHORT`/`AVAILABLE`/etc. per work order, but `release_readiness_service.py` never queries `PartRequirement` | The data needed to add a `MATERIAL` blocker category already exists (`PartRequirement.status`); it's simply not wired into `get_release_readiness_for_work_order`. |
| Authorization/sign-off blocker | MISSING | — | No model tracks a distinct "release sign-off" beyond Task execution_state; documented gap (`release_readiness_service.py:29-31`). |
| Pagination / list of readiness across many work orders | MISSING (not applicable — single-resource GET only) | — | |

## 7. API Inventory

| METHOD | PATH | PURPOSE | AUTH/PERMISSION | TENANT SCOPING | PAGINATION | STATUS CODES | IMPL STATUS |
|---|---|---|---|---|---|---|---|
| POST | `/inspections` | Create inspection requirement | `INSPECTION_WRITE` | `organization_id` from JWT only (`inspections.py:30`); task/work_order ownership verified in service | N/A (single create) | 201 | COMPLETE |
| GET | `/inspections/{id}` | Get one requirement | `INSPECTION_READ` | org-scoped lookup, `NotFoundError`→404 on cross-tenant | N/A | 200/404 | COMPLETE |
| GET | `/inspections/by-work-order/{work_order_id}` | List for work order | `INSPECTION_READ` | org-scoped filter | none — full list | 200 | COMPLETE |
| POST | `/inspections/{id}/transition` | Transition status (incl. RII completion) | `INSPECTION_WRITE` (no separate sign-off permission — noted explicitly in code comment `inspections.py:67-72`) | requirement re-fetched org-scoped before mutation | N/A | 200/409 (illegal transition)/400 (bad status) | COMPLETE |
| POST | `/regulatory-requirements` | Create requirement | `REGULATION_WRITE` | org from JWT | N/A | 201 | COMPLETE |
| GET | `/regulatory-requirements` | List | `REGULATION_READ` | org-scoped | none | 200 | COMPLETE |
| GET | `/regulatory-requirements/{id}` | Get one | `REGULATION_READ` | org-scoped | N/A | 200/404 | COMPLETE |
| POST | `/compliance-assessments` | Create assessment | `COMPLIANCE_ASSESS` | org-scoped, verifies aircraft + requirement ownership | N/A | 201 | COMPLETE |
| GET | `/compliance-assessments/{id}` | Get one | `COMPLIANCE_ASSESS` (read-side reuses the assess permission — no separate `COMPLIANCE_READ`) | org-scoped | N/A | 200/404 | COMPLETE — but see §8 RBAC note |
| POST | `/compliance-assessments/{id}/override` | Override determination | `COMPLIANCE_DECIDE` | org-scoped | N/A | 200/404 | COMPLETE |
| GET | `/aircraft/{id}/compliance-assessments` | List for aircraft | `COMPLIANCE_ASSESS` | org-scoped | none | 200 | COMPLETE |
| GET | `/aircraft/{id}/compliance-analytics` | Status-count aggregate | `COMPLIANCE_ASSESS` | org-scoped | N/A | 200 | COMPLETE |
| POST | `/evidence` | Create evidence record | `EVIDENCE_WRITE` | org from JWT, task ownership verified | N/A | 201 | COMPLETE |
| GET | `/evidence/{id}` | Get one | `EVIDENCE_READ` | org-scoped | N/A | 200/404 | COMPLETE |
| POST | `/evidence/{id}/transition` | Transition status | `EVIDENCE_WRITE` (no separate review permission, noted `evidence.py:77-80`) | org-scoped | N/A | 200/409/400 | COMPLETE |
| POST | `/evidence/{id}/files` | Upload file | `EVIDENCE_WRITE` + rate limit (60/60s) | evidence resolved org-scoped before storage call | N/A | 201/415/413/502 | COMPLETE |
| GET | `/evidence/{id}/files` | List files | `EVIDENCE_READ` | two-hop org+parent scoping | none — full list | 200 | COMPLETE |
| GET | `/evidence/{id}/files/{file_id}/download` | Presigned download URL | `EVIDENCE_READ` | two-hop org+parent scoping | N/A | 200/409 (not STORED)/502 | COMPLETE |
| DELETE | `/evidence/{id}/files/{file_id}` | Soft-delete file | `EVIDENCE_WRITE` | two-hop org+parent scoping | N/A | 204/409/502 | COMPLETE |
| POST | `/part-requirements` | Create | `PART_WRITE` | org from JWT; part/work_order/task ownership verified | N/A | 201 | COMPLETE |
| GET | `/part-requirements/{id}` | Get one | `PART_READ` | org-scoped | N/A | 200/404 | COMPLETE |
| GET | `/part-requirements/by-work-order/{work_order_id}` | List | `PART_READ` | org-scoped | none | 200 | COMPLETE |
| PATCH | `/part-requirements/{id}` | Partial update | `PART_WRITE` | org-scoped | N/A | 200/404 | COMPLETE |
| GET | `/work-orders/{id}/release-readiness` | Aggregate readiness | `AIRCRAFT_READ` (note: not a PART_*/EVIDENCE_*/INSPECTION_* permission — see §8) | org-scoped work order lookup | N/A | 200/404 | COMPLETE, narrow scope (§6) |

No REST endpoint exposes `readiness_service.evaluate_deployment_readiness` in this router set — it appears to be an internal service called by drone/AI code, not a directly-routed HTTP capability in the files audited.

## 8. RBAC Map

| Permission | Endpoint(s) | Service | Frontend control | Notes |
|---|---|---|---|---|
| `INSPECTION_READ` / `INSPECTION_WRITE` | all `/inspections/*` | `inspection_service.py` | `frontend/lib/api/inspections.ts` (no gating helper found — no frontend role-based hide/show analogous to evidence's `canWriteEvidenceFiles`) | **Gap (LOW):** unlike `evidenceFiles.ts:101-112`, there is no `EVIDENCE_WRITE_ROLES`-style UX-hint constant for inspection write — not a security issue (backend still enforces `require_permission`), just a UX inconsistency worth normalizing. |
| `EVIDENCE_READ` / `EVIDENCE_WRITE` | all `/evidence/*` | `evidence_service.py`, `evidence_file_service.py` | `frontend/lib/api/evidenceFiles.ts:101-112` (`EVIDENCE_WRITE_ROLES` UX hint, explicitly documented as non-authoritative) | Good pattern: comment explicitly disclaims the frontend check as a UX hint only (line 96-100). |
| `REGULATION_READ` / `REGULATION_WRITE` | `/regulatory-requirements*` | `compliance_service.py` | `frontend/lib/api/compliance.ts` | |
| `COMPLIANCE_ASSESS` | create/get/list assessment, analytics | `compliance_service.py` | | **Gap (MEDIUM):** `GET /compliance-assessments/{id}` (a read) requires `COMPLIANCE_ASSESS` (an assess/write-flavored permission) rather than a read permission (`compliance.py` API line 85). There is no distinct read-only compliance permission, so any role without `COMPLIANCE_ASSESS` (e.g. a hypothetical pure-viewer role) cannot even read an assessment it's entitled to see. Not a privilege-escalation risk (it's overly restrictive, not overly permissive) but is an inconsistency versus the read/write split used everywhere else (Evidence, Inspection, Part). |
| `COMPLIANCE_DECIDE` | override assessment | `compliance_service.py` | | Correctly separated from `COMPLIANCE_ASSESS` — a role could theoretically assess without being allowed to override, or vice versa; role table (`permissions.py:157-169`) grants both together to `COMPLIANCE_MANAGER` only. |
| `PART_READ` / `PART_WRITE` | `/part-requirements/*` | `part_requirement_service.py` | | Consistent read/write split. |
| `AIRCRAFT_READ` | `GET /work-orders/{id}/release-readiness` | `release_readiness_service.py` | `frontend/lib/api/release-readiness.ts` | **Gap (LOW/MEDIUM):** gating a work-order/evidence/inspection aggregate view behind `AIRCRAFT_READ` rather than a permission that actually names the underlying data (Evidence/Inspection/Task) means any role with fleet-visibility-only intent (`AIRCRAFT_READ`) can see evidence/inspection blocker descriptions it might not otherwise be granted to view directly via `/evidence` or `/inspections` (those need `EVIDENCE_READ`/`INSPECTION_READ`). Checked role table (`permissions.py` roles 129-244): every role that has `AIRCRAFT_READ` in this codebase also already has `EVIDENCE_READ` and `INSPECTION_READ`, so in the *current* role table this is not exploitable — but it is a latent inconsistency if a narrower role is added later without also reviewing this endpoint's permission choice. |
| No RBAC endpoint found to be missing a `require_permission` dependency | — | — | — | Every route read in `inspections.py`, `compliance.py`, `evidence.py`, `part_requirements.py`, `release_readiness.py` has an explicit `Depends(require_permission(...))`. No unauthenticated or unguarded route found in this set. |

## 9. Tenant Isolation

Good patterns actually found (code-verified):

- `organization_id` is **never** accepted from the request body in any of the 5 routers — always taken from `current_user.organization_id` (e.g. `inspections.py:30`, `evidence.py:53`, `compliance.py:31`, `part_requirements.py:27`).
- Every "get by id" service function filters by `(id, organization_id)` in the same `WHERE`, never a bare `.get(id)` — e.g. `inspection_service.py:243-247`, `evidence_service.py:139-143`, `compliance_service.py:118-123`, `part_requirement_service.py:82-87`.
- Nested-parent cross-tenant checks are explicit and tested: creating `Evidence` against a foreign-tenant `task_id` is verified to fail both when reading (`evidence_service.py:120-124`) and is covered by `test_tenancy_isolation.py:191-207 test_cross_tenant_cannot_create_evidence_against_foreign_task` — a nested-ID IDOR attempt.
- `EvidenceFile` carries its own `organization_id` in addition to the FK to `Evidence`, specifically as defense-in-depth against a future join-less query (model docstring `evidence.py:79-87`), and every file lookup filters on both `organization_id` AND parent `evidence_id` (`evidence_file_service.py:197-220`) — a file cannot leak across sibling Evidence rows even within the same tenant.
- `_assert_user_in_organization` (`inspection_service.py:34-46`) explicitly defends against attributing an RII completion to an arbitrary `inspector_user_id` from another org — confirmed tested (`test_inspection_completion_identity_api.py:93-113 test_explicit_inspector_from_other_org_rejected`).
- `PartRequirement` create verifies `part_id`, `work_order_id`, and (if given) `task_id` all belong to the caller's org before insert (`part_requirement_service.py:41-49`).

Gaps / things not fully verified:

- **`ComplianceAssessment.asset_id`** is populated via `resolve_asset_id(aircraft)` (`compliance_service.py:92`) from an already tenant-verified `aircraft` — this path was traced and looks correct, but `asset_resolution.resolve_asset_id`'s own internals were not read in this pass; flagged for completeness rather than as a confirmed defect.
- **No count/pagination leakage risk found** — because none of these 5 endpoint groups implement pagination at all (§7), there is no "total count leaks cross-tenant data" pattern to check; the risk here is unbounded-list DoS/perf, not tenant leakage (see §13).
- **Release readiness** (`release_readiness_service.py:61-67`) resolves `WorkOrder` org-scoped first, then filters all subsequent `Task`/`Evidence`/`InspectionRequirement` queries by both `organization_id` and the now-verified `work_order_id`/`task_ids` list (`release_readiness_service.py:69-129`) — correct chain, no gap found.
- Tenant isolation test file (`test_tenancy_isolation.py`) explicitly covers evidence (both direct get and nested create) and compliance assessment get, but **does not have a test for cross-tenant inspection requirement get/transition, part-requirement get, or release-readiness get** in the grep result obtained (only `test_cross_tenant_cannot_get_assessment` and the two evidence tests appear in this file). This is a **coverage gap**, not a demonstrated vulnerability — the service-layer code for those paths follows the identical `(id, organization_id)` pattern as evidence, but it is untested at the cross-tenant/API level for Inspection, PartRequirement, and ReleaseReadiness specifically.

## 10. Source of Truth Map

```
Flight (flight_service, not read in this pass)
   |
   v  (asset utilization accrual — not verified in this pass; out of audited file set)
Asset / Aircraft  ---------------------------------------------------------+
   |                                                                       |
   v                                                                       v
MaintenanceRequirement --> MaintenanceRequirementApplicability     ComplianceAssessment
   |            (aircraft_id | asset_id | battery_id | component_id)   (aircraft_id + asset_id,
   v                                                                     requirement_id -> RegulatoryRequirement)
MaintenanceAccomplishment (proof of performance; due-status engine reads
   ONLY this, never work-order status alone — maintenance_requirement.py:79-84)
   |
   v  (work_order_id, optional link — maintenance_requirement.py:116-117)
WorkOrder --> Task
                |-----------------> InspectionRequirement (task_id | work_order_id)
                |-----------------> Evidence (task_id) --> EvidenceFile (evidence_id)
                |-----------------> PartRequirement (task_id | work_order_id, part_id)
                v
   release_readiness_service.get_release_readiness_for_work_order(work_order_id)
        reads: Task.execution_state, Evidence(+gate), InspectionRequirement(+gate)
        DOES NOT read: PartRequirement, ComplianceAssessment, MaintenanceAccomplishment
```

Missing/partial links, confirmed by code read:
- **ReleaseReadiness ⇎ PartRequirement**: no query join exists (§6) — parts-short work orders are not reported as blocked.
- **ReleaseReadiness ⇎ ComplianceAssessment**: no join — a non-compliant aircraft does not block its own work order's release readiness.
- **ComplianceAssessment ⇎ MaintenanceRequirement**: separate model families with no FK between them; a regulatory requirement and a maintenance-interval requirement covering the same underlying regulation are not linked (see §12).
- **Flight → Utilization → MaintenanceRequirement**: not traced in this pass (flight/utilization services outside the specified file list); flagged as unverified rather than asserted present or absent.
- **Drone deployment readiness (`readiness_service.py`) is a separate branch entirely**, reading `Battery`, `maintenance_service.has_overdue_maintenance_for_asset`, and `InspectionRequirement` via `WorkOrder.asset_id` — it does not go through `release_readiness_service` at all (§6, §12).

## 11. Existing Test Coverage

| Area | Test file(s) | Coverage confirmed by test-name read |
|---|---|---|
| Inspection state machine (unit) | `backend/tests/unit/test_inspection_lifecycle.py` | Forward transitions, terminal states, illegal skip/self-transition, completion-gate helper, RII independence (empty-executor case, reject same person, allow different person, require an inspector, checklist has no constraint, skip check when no evidence yet) — 12 tests, all pure-logic. |
| Inspection completion identity (integration/API) | `backend/tests/integration/test_inspection_completion_identity_api.py` | "Complete as me" derivation, explicit-inspector-from-other-org rejection, independence-violation rejection, independent-inspector success — 4 tests, real API+DB. |
| Evidence state machine (unit) | `backend/tests/unit/test_evidence_lifecycle.py` | Forward sequence, no-skip, no-backwards, no-self-transition, ACCEPTED terminal, REJECTED reachable/resubmit-not-direct-accept, completion-gate (only ACCEPTED, plain-string input) — 10 tests. |
| Evidence file lifecycle | `test_evidence_file_model.py`, `test_evidence_file_service.py`, `test_evidence_file_upload_api.py`, `test_evidence_file_list_download_api.py`, `test_evidence_file_delete_api.py` | Model/service/API layers each have dedicated files (not individually enumerated here, but presence at all 3 layers confirmed by filename + grep hit). |
| Evidence reconciliation | `test_evidence_reconciliation_service.py` | Present; classification logic is otherwise pure and directly testable per `_classify`'s docstring table. |
| Real storage (S3/MinIO integration) | `backend/tests/real_storage/test_evidence_real_storage.py` + `README.md` | Separate real-storage-backed test tier exists (likely opt-in/marked, not verified whether run in default CI in this pass). |
| Compliance service (integration) | `backend/tests/integration/test_compliance_service.py` | Assessment default-unknown, unknown-requirement-raises, override records reason+actor, analytics counts by status, list scoped to aircraft, **cross-tenant get raises** — 6 tests, includes one tenant-isolation test. |
| Regulatory service | `backend/tests/integration/test_regulatory_service.py` | Present (not enumerated). |
| Part requirement (integration) | `backend/tests/integration/test_part_requirement_service.py` | Available-when-sufficient, short-when-insufficient, unknown-part-raises, list scoped to work order+org, fulfilled-quantity marks fulfilled, recompute short→available, get-not-found — 7 tests. |
| Release readiness (unit) | `backend/tests/unit/test_release_readiness_service.py` | Not-found-when-missing-work-order, zero-blockers-is-ready, task-execution blocker, evidence blocker, inspection blocker, accepted-evidence-and-completed-inspection-do-not-block — 6 tests. |
| Release readiness (integration, full chain) | `backend/tests/integration/test_release_readiness_full_chain.py` | Exactly one test, `test_full_readiness_chain` — a single end-to-end happy/blocked-path test, not a matrix of blocker-combination scenarios at the API layer. |
| Tenant isolation (cross-cutting) | `backend/tests/integration/test_tenancy_isolation.py` | Covers evidence (get + nested-create IDOR) and compliance assessment get. **Does not** (per the grep obtained) cover inspection, part-requirement, or release-readiness cross-tenant access at the API level — see §9. |
| RBAC / permissions (unit) | `backend/tests/unit/test_permissions.py` | Present (not enumerated in this pass; general permission-catalog test, not domain-specific). |

Concrete untested paths observed:
- Cross-tenant GET/transition on `/inspections/{id}` and `/part-requirements/{id}` at the API level (service-layer pattern is correct and consistent with tested paths, but no dedicated test found).
- `GET /work-orders/{id}/release-readiness` cross-tenant access (no test found for this specific endpoint's tenant boundary, only its happy-path chain).
- No test found exercising `readiness_service.evaluate_deployment_readiness` directly by name in the grep results (it may be covered indirectly by `test_drone_maintenance.py`/`test_drone_operations.py`, which were not opened in this pass).
- No frontend test found specifically for `RealReleaseReadinessPanel.tsx` or `RealTaskGatePanel.tsx` (searched by filename only, not for a corresponding `*.test.ts`/`*.test.tsx`; `frontend/tests/evidence-files.test.ts` exists but its coverage of these two "Real" components specifically was not verified line-by-line).
- Concurrency (e.g. two simultaneous transitions racing on the same `InspectionRequirement`/`Evidence` row) has no dedicated test found in this pass.

## 12. Domain Duplication Analysis

| Pair/Set | Verdict | Why |
|---|---|---|
| `MaintenanceRequirement` vs `InspectionRequirement` | **Intentionally separate.** | `MaintenanceRequirement` (`maintenance_requirement.py:26-39`) is an interval-driven (flight-hours/cycles/calendar/battery-cycles/component-hours) recurring due-date rule with its own `MaintenanceAccomplishment` proof-of-performance trail. `InspectionRequirement` (`inspection_requirement.py:33-49`) is a per-task/work-order one-shot sign-off gate (checklist or RII), with no interval/due-date concept at all. They can co-occur (a maintenance requirement's task might also carry an inspection requirement) but model different things — one is "when is this due again," the other is "did an authorized/independent person sign this off." |
| `InspectionRequirement` vs `PartRequirement` | **Intentionally separate, no overlap.** | Different lifecycle vocabularies (`PENDING/COMPLETED/NOT_REQUIRED/REJECTED` vs `REQUIRED/SHORT/AVAILABLE/RESERVED/ORDERED/RECEIVED/FULFILLED/CANCELLED`), different domains (sign-off vs. supply availability). No shared fields beyond the common `task_id`/`work_order_id` linkage pattern. |
| `RegulatoryRequirement`/`ComplianceAssessment` vs `MaintenanceRequirement`/`MaintenanceRequirementApplicability` | **Legitimately separate today, but a real conceptual overlap exists and is undocumented.** | Both are, at bottom, "a rule the fleet must satisfy, with an applicability scope and a recorded outcome." `MaintenanceRequirementApplicability` already models applicability to aircraft/asset/battery/component (`maintenance_requirement.py:42-73`) — i.e., a real (if simple) applicability mechanism — while `RegulatoryRequirement`/`ComplianceAssessment` has **no** applicability model at all (applicability is implicit in "an assessment exists for this aircraft," per the model docstring, `compliance.py:20-29`). A future AD/regulatory-requirement that is also a recurring maintenance task would plausibly need to be represented in both tables today, with no FK linking them — this is the one duplication risk in the "requirements" family worth resolving in M17.6, not because it's a bug, but because nothing currently prevents two independently-tracked, unlinked "is this aircraft compliant with X" records for the same underlying regulation. |
| `release_readiness_service` vs `readiness_service` | **Not a duplicate — a naming collision between two genuinely different features.** | `release_readiness_service.py` answers "can this MRO work order be released" (Evidence/Inspection/Task-execution gates, work-order-scoped). `readiness_service.py` answers "can this drone be dispatched right now" (battery/maintenance/inspection/active-status, asset-scoped, drone-specific per its own docstring lines 1-21). They share zero code and are invoked from different domains, but the near-identical naming (`ReleaseReadiness` vs. `evaluate_deployment_readiness`, both returning a `status: READY/BLOCKED` shape) is a real risk for a future engineer (or M17.6 author) accidentally treating them as the same concept or extending the wrong one. Recommend a naming/documentation pass, not a merge — merging would conflate MRO release semantics with flight-dispatch semantics, which the code correctly keeps apart today. |
| Evidence lifecycle vs EvidenceFile lifecycle | **Intentionally separate**, explicitly documented (`evidence.py:26-42`) — one is the review/acceptance workflow of a record, the other is the physical object-storage state of a file backing that record. No overlap found. |

## 13. Gaps (ranked)

**CRITICAL** — none found. No unauthenticated endpoint, no tenant-scoping bypass, no privilege escalation was found in the code actually read.

**HIGH**
1. `release_readiness_service` never considers `PartRequirement` (materials) or `ComplianceAssessment` (regulatory) blockers — a work order can be reported `READY` while parts are `SHORT` or the aircraft has an open `NON_COMPLIANT`/`REVIEW_REQUIRED` assessment. This is the single biggest "readiness understates risk" gap and is explicitly self-disclosed by the code (`release_readiness_service.py:28-32`, returned in every response's `data_completeness` field) rather than hidden — but it means any consumer of this endpoint (frontend `RealReleaseReadinessPanel.tsx`, or a future AI tool) that doesn't also separately check parts/compliance is working from an incomplete picture.
2. `Evidence` has no `required` boolean — a task that genuinely needs evidence but has zero Evidence rows yet is invisible to release-readiness as a blocker (`release_readiness_service.py:14-17`). This is a correctness gap in the *evidence-required detection*, not just missing categories.

**MEDIUM**
3. Tenant-isolation test coverage gap for Inspection, PartRequirement, and ReleaseReadiness endpoints specifically (§9, §11) — the underlying code pattern is consistent and correct by inspection, but is unverified by a dedicated cross-tenant test the way Evidence and Compliance are.
4. `GET /compliance-assessments/{id}` requires `COMPLIANCE_ASSESS` rather than a read permission (§8) — an RBAC modeling inconsistency (overly restrictive, not overly permissive) versus the read/write split used by Evidence/Inspection/Part.
5. `RegulatoryRequirement`/`ComplianceAssessment` has no applicability linkage to `MaintenanceRequirementApplicability`, risking future duplicate/unlinked compliance records for the same regulation (§12).
6. No pagination anywhere in these 5 routers (§7) — every list endpoint returns a full unbounded result set. Consistent with the rest of the platform per `audit_service.py`'s comment ("No existing platform list endpoint paginates"), so this is a platform-wide pattern, not specific to M17.6's domains — but it is a real scale risk for `/evidence/{id}/files` (potentially many files per evidence record over time) and any org with a large task backlog.

**LOW**
7. No frontend UX-hint permission gating for Inspection write actions (unlike Evidence's `EVIDENCE_WRITE_ROLES`, §8) — cosmetic/UX only, backend still enforces the real permission.
8. `AIRCRAFT_READ` gating the release-readiness endpoint is looser in spirit than `EVIDENCE_READ`/`INSPECTION_READ` gating the underlying data directly, though not currently exploitable given the present role table (§8).
9. No REST endpoint found exposing drone deployment readiness (`readiness_service.evaluate_deployment_readiness`) — may be fully intentional (internal/AI-tool-only), but worth confirming it isn't a forgotten wiring gap.

## 14. Revised M17.6A/B/C/D Scope

This scope assumes the existing models/services/APIs in §2-§7 are correct and complete for what they claim to do, and only targets the gaps in §13. No greenfield rebuild of Inspection/Evidence/Compliance/Readiness is warranted.

**M17.6A — Release-readiness completeness (addresses HIGH #1, #2)**
- Files affected: `backend/app/services/release_readiness_service.py` (add MATERIAL and COMPLIANCE blocker categories; extend `BlockerCategory` Literal in `backend/app/schemas/release_readiness.py`), `backend/app/models/evidence.py` (add nullable `required: bool` column with a safe default matching current behavior), a new Alembic migration for the `evidence.required` column.
- Reuse: `part_requirement_service.list_part_requirements_for_work_order` (already exists, tenant-scoped, work-order-scoped) for the MATERIAL check; `compliance_service.list_assessments_for_aircraft` (needs the work order's `asset_id`/`aircraft_id` — confirm `WorkOrder` carries one; not verified in this pass) for the COMPLIANCE check.
- New models: none required for MATERIAL; none required for the `evidence.required` column (just a new field on the existing model).
- Migration: **yes** — new nullable column `evidence.required` (backfill default consistent with current "every row is required" behavior to avoid changing existing gate semantics silently).
- Tests required: unit tests extending `test_release_readiness_service.py` for MATERIAL/COMPLIANCE blocker presence/absence; integration test extending `test_release_readiness_full_chain.py` to a matrix covering all blocker category combinations; regression test confirming existing EVIDENCE/INSPECTION/TASK_EXECUTION behavior is unchanged.

**M17.6B — Tenant-isolation test hardening (addresses MEDIUM #3)**
- Files affected: `backend/tests/integration/test_tenancy_isolation.py` only.
- Reuse: existing `_two_tenants` helper pattern already in that file (used for evidence/compliance); extend to Inspection (`GET`/`POST transition` on a foreign-tenant `InspectionRequirement`), PartRequirement (`GET`/`PATCH` on a foreign-tenant row), and `GET /work-orders/{id}/release-readiness` on a foreign-tenant work order.
- New models: none. Migration: no.
- Tests required: this phase *is* the tests — no production code change expected unless a real gap is found (in which case the fix belongs in the relevant service, following the exact `(id, organization_id)` pattern already used everywhere else in these domains).

**M17.6C — Compliance/RBAC and applicability linkage (addresses MEDIUM #4, #5)**
- Files affected: `backend/app/core/permissions.py` (introduce `COMPLIANCE_READ` if the product decision is to loosen the read-side; or explicitly document why `COMPLIANCE_ASSESS` is intentionally required for reads and close this as won't-fix), `backend/app/api/v1/compliance.py` (swap the permission dependency on the `GET /compliance-assessments/{id}` route if `COMPLIANCE_READ` is introduced), `backend/app/models/compliance.py` (optional nullable `maintenance_requirement_id` FK on `RegulatoryRequirement` or `ComplianceAssessment` if product wants an explicit link — this is a judgment call for the product owner, not purely technical).
- Reuse: existing `ComplianceAssessment`/`MaintenanceRequirement` models; no new service layer needed beyond wiring the new FK through `compliance_service.create_assessment`.
- Migration: **yes, conditionally** — only if the FK-link sub-scope is approved; the RBAC permission split needs no migration (it's a Python enum + role-table change).
- Tests required: permission-catalog unit test update (`test_permissions.py`); a role-table regression test; if the FK is added, a new integration test verifying an assessment can optionally cite a `MaintenanceRequirement`.

**M17.6D — Readiness naming/documentation and pagination pass (addresses MEDIUM #6, LOW #7-9)**
- Files affected: `backend/app/services/readiness_service.py` (rename or add a module-level docstring cross-reference disambiguating it from `release_readiness_service.py` — purely documentation, e.g. rename the module to `drone_readiness_service.py` if a rename is acceptable, or at minimum a doc comment cross-link both ways), `frontend/lib/api/inspections.ts` (add an `INSPECTION_WRITE_ROLES` UX-hint constant mirroring `evidenceFiles.ts`), and — if pagination is prioritized — `backend/app/api/v1/evidence.py`'s `list_evidence_files`, `inspections.py`'s work-order list, `compliance.py`'s list endpoints, and `part_requirements.py`'s list endpoint, following the `limit`/`offset` pattern already established in `audit_service.list_audit_events` (`audit_service.py:39-94`).
- Reuse: `audit_service.py`'s existing pagination bounds pattern (`AUDIT_LIST_DEFAULT_LIMIT`/`AUDIT_LIST_MAX_LIMIT`) as the template for any new paginated list endpoint.
- Migration: no.
- Tests required: pagination boundary tests (empty, under-limit, over-limit, offset past end) per endpoint touched; a docs-only check for the naming/cross-reference change (no automated test needed).

## 15. Explicitly Deferred / Do-Not-Build List

Already exists — do not rebuild:
- **Checklist-vs-RII distinction** — already fully modeled by `InspectionRequirement.required` (§3). Do not build a separate "Checklist" entity type; the frontend mock `checklists.ts`/`ChecklistPanel.tsx` is demo-only UI and should be pointed at the existing `InspectionRequirement` API (`required=False` rows), not replicated server-side.
- **Evidence upload/download/delete/reconciliation** — fully built (§4). Do not build a second file-storage path or a second reconciliation job.
- **Compliance assessment CRUD + override + analytics** — fully built (§5). Do not build a second "compliance record" model.
- **Release-readiness aggregation scaffolding** — the aggregation *pattern* (pure read-layer that asks existing services for gate status, never re-implementing their rules — `release_readiness_service.py:1-8`) is exactly right and should be extended (M17.6A), not replaced.
- **Audit trail** — `record_audit_event`/`list_audit_events` is generic and already used by every domain in this audit; do not build a domain-specific audit mechanism for Inspection/Evidence/Compliance/PartRequirement.

Out of scope for any near-term M17.6 phase (confirmed via code comments as deliberate, standing decisions, not oversights):
- **Regulatory document ingestion** (AI/automated parsing of regulations into `RegulatoryRequirement` rows) — explicitly deferred per `frontend/lib/api/compliance.ts:6-12`'s reference to `docs/FULL_SYSTEM_AUDIT.md` and `backend/app/services/ai/tools.py`.
- **Condition-tree/applicability rules engine** (AND/OR/NOT over aircraft-type/MSN-range/engine-type) — explicitly deferred per `compliance.py` model docstring (`20-29`) as "a genuine rules-engine build, not a persistence slice."
- **AI/ML-driven compliance interpretation or predictive compliance** — no code found attempting this; `compliance_service.get_compliance_analytics` is explicitly the "honest, directly-countable" version specifically to avoid implying AI-derived confidence scoring exists (`compliance_service.py:188-195`).
- **Telemetry-driven readiness signals** — `readiness_service.py` docstring explicitly defers a "standing assigned pilot" attribute and an "open work order" blocker as ungrounded guesses it refuses to fabricate (lines 15-21); this discipline should be preserved in M17.6, not overridden by adding speculative signals.

## 16. Recommended Next Action

Start with **M17.6A** (release-readiness completeness: add MATERIAL and COMPLIANCE blocker categories, plus the `evidence.required` column) — it is the highest-severity, most self-contained gap (§13 HIGH #1/#2), reuses 100% existing services (`part_requirement_service`, `compliance_service`) with no new models, and directly improves the correctness of a capability (`GET /work-orders/{id}/release-readiness`) that is already live and already consumed by the frontend's `RealReleaseReadinessPanel.tsx`. Do not begin implementation from this audit alone — scope the exact migration and blocker-category wiring in a follow-up design pass first, since `WorkOrder`'s aircraft/asset linkage (needed for the COMPLIANCE blocker join) was not fully traced in this read-only pass and must be confirmed before writing the query.

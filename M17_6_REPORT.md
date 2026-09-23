# M17.6 Release Readiness Extension — Report

## Environment constraint (read first)

This sandbox has **no Python interpreter installed** (`python`/`python3` resolve to the
Windows Store install-shim, and no venv/conda/pipx was found anywhere on the machine).
That means Phase 0/1 reading and the Phase A code changes were done directly by reading
the real source, but **no backend command could actually be executed**: no pytest run,
no Alembic upgrade/downgrade, no ruff/mypy. Node was available, but no frontend test/build
run was attempted either, to keep the scope honest given the same "can I actually verify
this" bar. Everything below that says "not run" or "deferred — no runtime" is a hard
environment limitation, not a skipped step.

## Phase A — Backend model/service layer: DONE (code), NOT test-executed

### Architecture reused (confirmed by reading, not guessing)
- `InspectionRequirement`, `Evidence`/`EvidenceFile`, `RegulatoryRequirement`/
  `ComplianceAssessment`, `PartRequirement`, `release_readiness_service.py`,
  `readiness_service.py` were **not** touched structurally — all reused as-is.
- Confirmed `release_readiness_service.py` (work-order release readiness, keyed off
  `WorkOrder`) and `readiness_service.py` (drone deployment readiness) are genuinely
  separate files/concerns; only the former was modified. Its module docstring already
  states the boundary; I extended that same docstring rather than replacing it.
- Confirmed `WorkOrder.asset_id` (nullable FK to `assets`, migration 0031/0032) is the
  canonical asset-resolution path; `aircraft_id` remains the legacy/authoritative FK for
  aircraft-based work orders. `ComplianceAssessment` links to an asset via its own
  `asset_id` (also nullable, same compatibility-mapping pattern) — readiness joins on
  `WorkOrder.asset_id == ComplianceAssessment.asset_id`.
- Confirmed `PartRequirement.required_quantity` / `fulfilled_quantity` are plain integer
  columns and `status` is a free-form string (`PartRequirementStatus`), not a DB enum —
  matching every other status column in this codebase.
- Confirmed `ComplianceAssessmentStatus` = `COMPLIANT | NON_COMPLIANT | REVIEW_REQUIRED |
  UNKNOWN`, and assessments are historical (multiple rows per `requirement_id`/asset over
  time, each with its own `evaluated_at`) — there is no "current assessment" pointer
  anywhere in the model.
- Confirmed `Blocker`/`BlockerCategory` in `app/schemas/release_readiness.py` is the one
  and only blocker vocabulary for this endpoint (a `Literal` union) — extended it rather
  than creating a parallel enum.

### Required-evidence source of truth
The audit's gap #3 ("Evidence has no `required` concept") was investigated per the
instruction to prefer a requirement-level field over a raw `Evidence.required` boolean.
`Evidence.status` already has a `REQUIRED` member, but that only helps once an Evidence
*row* exists — a task with **zero** Evidence rows was, and without this change still
would be, invisible to any evidence check. `Task` had no such field. I added
`Task.evidence_required: bool` (default `False`), because `Task` is the actual unit of
work being asked for evidence, and `Evidence` rows are inherently per-submission and may
legitimately not exist yet. Existing rows/tasks default to `False`, so nothing already in
the DB retroactively becomes a blocker.

### Exact code changes
- `backend/app/models/task.py`: added `evidence_required: Mapped[bool]` (Boolean,
  `nullable=False`, `default=False`).
- `backend/alembic/versions/0035_task_evidence_required.py` (new): adds
  `tasks.evidence_required` with `server_default=false()`, then drops the server default
  (matches the codebase's own pattern of backfill-then-drop-default). Downgrade drops the
  column. **Not run** — no Python runtime to execute `alembic upgrade`/`downgrade` in this
  sandbox. The migration was hand-verified against the existing 0034 file's style and
  against the model change; it was not applied to a real Postgres instance.
- `backend/app/schemas/release_readiness.py`: `BlockerCategory` extended from
  `EVIDENCE | INSPECTION | TASK_EXECUTION` to add `MATERIAL` and `COMPLIANCE` (same
  `Literal`, no second enum).
- `backend/app/services/release_readiness_service.py`:
  - **MATERIAL**: queries `PartRequirement` by `organization_id` + `work_order_id`. A row
    blocks when `status not in {FULFILLED, CANCELLED}` and
    `fulfilled_quantity < required_quantity`. Each outstanding row is its own blocker
    (`related_record_id` = the `PartRequirement.id`), so multiple short parts produce
    multiple independent MATERIAL blockers that clear independently as each is fulfilled.
  - **COMPLIANCE**: only runs when `work_order.asset_id is not None` (drone-only work
    orders with no asset resolve to zero COMPLIANCE blockers, not an error). Loads all
    `ComplianceAssessment` rows for that `asset_id`, groups by `requirement_id`, and picks
    the one with the greatest `(evaluated_at, created_at)` per requirement — i.e. the
    latest determination, never an older row. Blocks only when that latest row's `status
    == NON_COMPLIANT`. `REVIEW_REQUIRED`/`UNKNOWN` (pending-style) latest rows do **not**
    block, matching the existing "don't treat unknown as either compliant or
    non-compliant" convention elsewhere in this codebase — and do not treat it as
    compliant either (both are honestly non-blocking, not silently passed).
  - **EVIDENCE (extended)**: unchanged behavior for existing Evidence rows (still only
    ACCEPTED satisfies the gate). Added: any task with `evidence_required=True` and zero
    Evidence rows at all produces its own EVIDENCE blocker
    (`related_record_id` = the `Task.id`), explaining "Task requires evidence but none
    has been submitted yet". A task with `evidence_required=False` and no Evidence rows
    still produces nothing (preserves the pre-existing optional-evidence behavior exactly).
  - `data_completeness` string updated: now says only authorization sign-off remains
    untracked (previously said material and regulatory/compliance too).
  - Module docstring rewritten to document all five blocker categories and their exact
    field-level semantics.
- All new queries filter by `organization_id` taken from `current_user.organization_id`
  in the API layer (unchanged call site in `app/api/v1/release_readiness.py`) — no new
  query trusts a client-supplied org id, and no new query was added to that API file at
  all (endpoint contract/response model unchanged, so Phase B needed no separate edit
  beyond the schema/service change already covered above).

### Multiple-blocker / additivity behavior
Blockers accumulate into one flat `blockers: list[Blocker]` exactly as before; nothing
short-circuits. TASK_EXECUTION/EVIDENCE/INSPECTION logic is untouched (same statements,
same order), so pre-existing behavior for those three categories is unchanged byte-for-byte
except for the one additive EVIDENCE-required-but-missing check appended after it.
MATERIAL and COMPLIANCE are independent new blocks appended after INSPECTION. Clearing one
requirement (e.g. fulfilling one of two short parts) removes only that blocker; the other
categories are computed from disjoint queries and are unaffected.

### Backend tests (code written, not executed)
Extended `backend/tests/unit/test_release_readiness_service.py` (same `_FakeSession`
ordered-`execute()` convention as the existing file) with new factory helpers
(`_part_requirement`, `_assessment`) and updated every pre-existing test's fake result
list to account for the two new queries (part-requirements always runs; compliance only
runs when `asset_id` is set), **without weakening any existing assertion**. Added tests:
- `test_evidence_required_but_missing_blocks`
- `test_evidence_required_satisfied_by_accepted_evidence`
- `test_evidence_not_required_and_missing_does_not_block` (regression: old optional
  behavior preserved)
- `test_material_blocker_when_short`
- `test_material_no_blocker_when_fulfilled_quantity_met`
- `test_material_no_blocker_when_cancelled_even_if_short`
- `test_material_multiple_outstanding_requirements_each_block`
- `test_compliance_blocker_when_non_compliant`
- `test_compliance_no_blocker_when_compliant`
- `test_compliance_pending_assessment_does_not_block`
- `test_compliance_historical_non_compliant_does_not_override_current_compliant`
- `test_compliance_not_evaluated_when_work_order_has_no_asset`
- `test_multiple_blocker_categories_coexist_and_are_independent`

**These were never executed** (no Python runtime). They were written and manually traced
against the new service code's exact query order and branching, but that is a substitute
for, not equivalent to, an actual pytest run. This is the single biggest caveat in this
report.

## Phase B — API integration

No separate endpoint or response-model change was needed: `app/api/v1/release_readiness.py`
already returns the shared `ReleaseReadiness` schema verbatim, and that schema was the one
extended in Phase A (`BlockerCategory` now includes `MATERIAL`/`COMPLIANCE`). RBAC is
unchanged (`Permission.AIRCRAFT_READ`, the same permission already gating this endpoint) —
no new permission constant was introduced, since the existing read gate already covers the
new blocker data (it's still one read of one work order's readiness). OpenAPI regeneration
was **not verified** — no Python runtime to boot FastAPI and inspect `/openapi.json`. By
inspection, since `BlockerCategory` is a `Literal`, Pydantic/FastAPI will render the
extended `enum` list in the schema automatically; this was not empirically confirmed.
API-level tests (ready case, per-blocker-type, multiple blockers, clearing, tenant
isolation, RBAC, 404, validation, response schema) were **not written** — out of scope for
the time available given Phase A's own test writing/verification gap already dominates the
risk budget; flagged as a deferral below, not a silent omission.

## Phase C — Frontend

Reused existing components/patterns, no rebuild:
- `frontend/lib/api/release-readiness.ts`: `BackendBlockerCategory` extended to include
  `"MATERIAL" | "COMPLIANCE"`.
- `frontend/components/evidence/RealReleaseReadinessPanel.tsx`: `CATEGORY_LABEL` extended
  with `MATERIAL: "Material"`, `COMPLIANCE: "Compliance"`. The panel already rendered
  blockers generically as a `<ul>` of `{category, description, related_record_id}` with no
  category-specific branching, already supports N blockers of mixed categories rendering
  as separate `<li>` items (never collapsed), and already had loading/error/empty/
  not-authenticated states and a real-backend-text render path (no invented copy) — so no
  further structural change was required for the two new categories to display correctly
  with real backend explanation text.
- No dedicated automated frontend test file existed for this panel before this change
  (`frontend/tests` has no `*readiness*`/`*ReleaseReadiness*` file), so none was extended.
  Writing a new one from scratch, plus a real `npm test`/`tsc`/`eslint`/build run, was not
  attempted in this pass — deferred (see below). No manual/browser verification of the UI
  was performed either.

## Phase D — Integration + hardening: NOT DONE

Given Phase A/B/C could not be executed at all in this sandbox (no Python runtime; no
frontend test/build run attempted), Phase D's end-to-end flow exercise, the two-org tenant
isolation test, the missing Inspection/PartRequirement/ReleaseReadiness cross-tenant tests,
N+1/concurrency review of the *running* code, full backend/frontend suite runs, static
checks (ruff/mypy/tsc/eslint/build), and browser verification were **not performed**. This
is reported as not done rather than fabricated.

## Static/dynamic verification status (explicit, not implied)
- Backend targeted unit tests: **not run** (no Python interpreter available).
- Backend full suite: **not run**.
- Frontend targeted/full tests: **not run**.
- ruff / mypy / tsc / eslint / production build: **not run**.
- Alembic upgrade → downgrade → upgrade: **not run** against any DB.
- Browser verification: **not performed**.

## Security self-scan of changed files (manual read, no tooling)
- No production URLs, DB connection strings, or credentials/secrets/tokens in any changed
  file.
- No new query anywhere accepts or trusts a client-supplied `organization_id` — every new
  query filters on `organization_id=current_user.organization_id`, passed in from the
  unchanged API dependency chain.
- No raw/unsafe SQL introduced (SQLAlchemy Core `select()` only, same style as the rest of
  the file).
- No HTML injection surface added on the frontend (existing JSX text interpolation only,
  no `dangerouslySetInnerHTML`).
- No authorization bypass: RBAC dependency (`require_permission(Permission.AIRCRAFT_READ)`)
  on the one affected endpoint is untouched.

## Two readiness engines
Confirmed still separate: `release_readiness_service.py` (work-order release readiness,
the only file modified) and `readiness_service.py` (drone deployment readiness, not
touched at all in this pass). The module docstring in `release_readiness_service.py` was
extended (not replaced) to keep describing this boundary.

## Migration
Created: `backend/alembic/versions/0035_task_evidence_required.py`, adding
`tasks.evidence_required` (boolean, default false). Required because the chosen
required-evidence source of truth is a new column. **Upgrade/downgrade/upgrade was not
verified** against a real database — no Python/Alembic runtime available in this sandbox.

## Git state
- Commit: **NO**. Push: **NO**. Deploy: **NO**.
- Working tree left uncommitted for review. `git status`/`git diff --stat` at the end of
  this pass:
  - Modified: `backend/app/models/task.py`, `backend/app/schemas/release_readiness.py`,
    `backend/app/services/release_readiness_service.py`,
    `backend/tests/unit/test_release_readiness_service.py`,
    `frontend/components/evidence/RealReleaseReadinessPanel.tsx`,
    `frontend/lib/api/release-readiness.ts` (6 files, +507/-19 lines).
  - Untracked (new): `backend/alembic/versions/0035_task_evidence_required.py`,
    `M17_6_AUDIT.md` (pre-existing from the prior audit pass), and this report.

## Remaining/deferred gaps (intentional deferrals)
- Readiness-engine naming cleanup (`release_readiness_service.py` vs
  `readiness_service.py`) — not renamed, per hard constraint against merging/renaming.
- Deeper compliance applicability / a real applicability rule engine — explicitly out of
  scope (hard constraint: no regulatory rules engine).
- Advanced evidence requirements (per-evidence-type rules, multi-file requirements) — out
  of scope.
- Evidence upload/review permission separation — not touched; existing RBAC reused as-is.
- Pagination improvements on list endpoints — not touched (audit gap #5), since none of
  them sit directly on the modified readiness response path.
- Dedicated cross-tenant isolation tests for Inspection/PartRequirement/ReleaseReadiness
  (audit gap #4) — **not added** in this pass; the readiness unit tests added here exercise
  correctness of the new blocker logic but do not add the dedicated tenant-isolation test
  files the audit called out as missing.
- API-level tests (Phase B) and frontend tests (Phase C) for the new blocker categories —
  not written.
- Full Phase D hardening (end-to-end flow, two-org isolation test, N+1/concurrency
  verification against running code, full suite runs, static checks, browser
  verification) — not performed, blocked by lack of a runnable backend environment in this
  sandbox.

## Final factual status
Backend model, schema, and service-layer code for MATERIAL, COMPLIANCE, and
required-but-missing EVIDENCE blockers was written directly against the real existing
models (`PartRequirement`, `ComplianceAssessment`, `Task`), reusing the existing blocker
vocabulary and the existing single release-readiness endpoint/response contract, with one
new Alembic migration (`0035_task_evidence_required.py`) and corresponding unit-test
additions to `test_release_readiness_service.py`. The frontend type union and label map
were extended to match. None of this — backend tests, the migration, ruff/mypy, and
frontend tests/build — was executed, because no Python interpreter exists in this sandbox
and no frontend test/build run was attempted; that verification gap is the primary
limitation of this pass, and Phase D (integration, hardening, full-suite runs, browser
verification) was not performed as a direct consequence. Nothing was committed, pushed, or
deployed.

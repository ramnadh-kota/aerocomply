# M17 Testing Pass Report (2026-09-18)

## Environment
- Backend: Python 3.12.10 venv at `backend/.venv`, project installed via `pip install -e ".[dev]"` (pytest, pytest-asyncio, ruff, mypy present and used).
- `backend/.env` DATABASE_URL confirmed to point at `localhost:55432/aerocomply_dev` (local, not staging/production). Value not printed.
- **Local Postgres is NOT reachable.** Direct `psycopg.connect` to `localhost:55432` timed out. No native Postgres service/binary found on the machine (`Get-Service *postgres*`, `pg_ctl`, `postgres` all absent). `infra/docker-compose.yml` defines the local Postgres service, but **Docker itself is not installed** in this environment (`docker` is not a recognized command in either Git Bash or PowerShell), so it could not be started. Per hard safety rules, no new/remote/cloud database was created as a substitute.
- Consequence: every test, migration step, and OpenAPI check that requires a live DB connection is marked **NOT VERIFIED** below, with the specific reason given. All DB-independent checks (unit tests with fakes/mocks, static analysis, app import/openapi generation, frontend) were run for real and results are exact.

## Git
- HEAD: `f31dbe4` (feat(drone): add battery and component maintenance lifecycle) — M17.5 committed.
- Working tree at start: 6 modified files (M17.6 release-readiness extension) + 3 untracked (`M17_6_AUDIT.md`, `M17_6_REPORT.md`, `backend/alembic/versions/0035_task_evidence_required.py`). No unrelated changes.
- End of pass: same files modified, plus fixes described below (2 ruff line-length fixes in the test file, 1 mypy fix in `release_readiness_service.py`). `frontend/next-env.d.ts` was touched automatically by `tsc`/`next build` (generated, harmless). Nothing committed, nothing pushed.

## Backend Targeted Tests
- `tests/unit/test_release_readiness_service.py` (the M17.6 unit tests, use fakes, no DB): **19 passed, 0 failed** both before and after the mypy fix.
- `tests/unit/` (full unit dir — includes permissions, storage service, etc., no DB): **136 passed, 0 failed**, 12.18s.
- All other named domains (battery/component lifecycle M17.2, flight/utilization M17.3, asset maintenance M17.4, battery-component-maintenance M17.5, part requirement, compliance assessment, evidence, inspection) live only in `tests/integration/` and require a live Postgres connection (session-scoped DB fixture). **NOT VERIFIED — no reachable local Postgres** (see Environment). Collection was confirmed clean: `982/998 tests collected (16 deselected)` via `pytest --collect-only -q -m "not real_storage"`.

## Full Backend
- Ran `pytest -q -m "not real_storage"`: hung indefinitely on DB-connection attempts/timeouts for the integration fixture setup and had to be force-stopped after 2+ minutes with no output. **NOT VERIFIED** — cannot produce real pass/fail/skip/error counts without a reachable database. Do not treat this as a pass.

## Frontend Targeted + Full Tests
- `npx vitest run` (frontend, full suite — no dedicated per-domain split; project has 8 test files total, mostly `tests/ai/`):
  **8 test files passed, 133 tests passed, 0 failed**, duration 2.14s.
- No frontend test files specifically target drone/battery/component/maintenance/readiness/evidence/compliance by name — the existing suite is the Lisa AI matrix and related unit tests. This is the full and only frontend suite; targeted vs. full are the same run.

## Static Checks
- **ruff (backend)**: Initial `ruff check app/ tests/` found 5 E501 errors: 2 pre-existing/out-of-scope (`tests/integration/test_asset_foundation.py:861`, `tests/integration/test_drone_lifecycle_api.py:424,463`), 2 new/in-scope in `tests/unit/test_release_readiness_service.py` (lines 389, 412 — introduced by the M17.6 test additions). **Fixed** the 2 in-scope violations by reformatting the `_part_requirement(...)` calls across multiple lines. Re-ran ruff scoped to all M17.6-touched files: **All checks passed**. The 2 pre-existing violations in unrelated integration test files were left untouched (out of scope, not part of this milestone's diff).
- **mypy (backend)**: `mypy app/models/task.py app/schemas/release_readiness.py app/services/release_readiness_service.py` initially found **5 real errors**, all one root cause: the MATERIAL-blocker loop reused the loop variable name `requirement` (already narrowed to `InspectionRequirement` by the preceding INSPECTION loop) for `PartRequirement` rows, causing an "Incompatible types in assignment" plus two "has no attribute" errors on `fulfilled_quantity`/`required_quantity`. **Fixed** by renaming the loop variable to `part_requirement` in `app/services/release_readiness_service.py` (lines ~190-204). Re-ran: **Success: no issues found in 3 source files**. Re-ran the unit test suite and ruff after the fix — still 19/19 passing, still clean.
- Full-repo mypy/ruff sweep beyond the M17.6 file set was not attempted (out of scope per instructions — only the M17.2-M17.6 diff was to be validated); pre-existing issues elsewhere in the repo were not catalogued.
- **tsc --noEmit (frontend)**: clean, no output/errors.
- **eslint (frontend, `npx eslint .`)**: **0 errors, 54 warnings** (all `react-hooks/set-state-in-effect` "Avoid calling setState() directly within an effect" plus one unused-eslint-disable). One warning is in `components/evidence/RealReleaseReadinessPanel.tsx:47` (`load()` call inside `useEffect`) — confirmed via `git diff` that this line is **pre-existing**, not part of the M17.6 diff (the M17.6 diff to that file only adds two `CATEGORY_LABEL` map entries: `MATERIAL` and `COMPLIANCE`). No new lint errors introduced by M17.6.
- **next build (frontend)**: completed successfully, full route manifest generated, no build errors.

## API / OpenAPI
- Loaded `app.main:app` directly via `.venv` Python (no server process, no DB needed for schema generation) and called `app.openapi()`.
- Confirmed `/api/v1/work-orders/{work_order_id}/release-readiness` is present in `schema['paths']`.
- Confirmed `components.schemas.Blocker.properties.category.enum` == `["EVIDENCE", "INSPECTION", "TASK_EXECUTION", "MATERIAL", "COMPLIANCE"]` — the new MATERIAL and COMPLIANCE blocker categories from M17.6 are correctly exposed in the schema.
- Did not start an actual live server process (uvicorn) since it isn't needed to validate the schema and DB isn't reachable for any request-handling smoke test beyond schema generation.

## Tenant Isolation
- Dedicated cross-tenant test file: `tests/integration/test_tenancy_isolation.py`, covering: aircraft, work order, deferred item, purchase order, assessment, evidence (get + create), and Lisa aircraft-registration resolution. **All of these require DB — NOT VERIFIED this pass.**
- **No dedicated tenant-isolation tests exist** for: release readiness (MATERIAL/COMPLIANCE/EVIDENCE blockers specifically), PartRequirement, ComplianceAssessment-as-used-by-readiness, or Inspection-as-used-by-readiness. This confirms the gap already flagged in `M17_6_AUDIT.md`. Given no reachable DB this session, no new integration test was added (writing an untestable integration test would be worthless busywork); this remains an open gap for whoever validates with a real DB available.

## RBAC
- No dedicated RBAC-only test file per domain; RBAC assertions are embedded inside domain integration tests (`test_ai_tools.py`, `test_assessments_api.py`, `test_battery_component_maintenance.py`, `test_drone_lifecycle_api.py`, `test_drone_maintenance.py`, `test_security_hardening.py`, etc.) plus `tests/unit/test_permissions.py`.
- `tests/unit/test_permissions.py` is DB-free and included in the 136-passed unit run above (real pass).
- All integration-level RBAC assertions: **NOT VERIFIED — no reachable DB.**

## Migration Verification (0035_task_evidence_required)
- **NOT VERIFIED — could not execute `alembic upgrade head` / `downgrade -1` / `upgrade head` against a real database** (no reachable local Postgres).
- Performed static verification instead:
  - `alembic heads` → `0035 (head)`, confirming a single clean head with no branching.
  - Confirmed `down_revision = "0034"` matches the actual prior head (`0034_battery_component_maintenance.py`), so the revision chain is structurally correct.
  - Read the migration body: `upgrade()` adds `tasks.evidence_required` as `Boolean, nullable=False, server_default=sa.false()` (so existing rows backfill to `false` safely), then drops the server default (`alter_column(..., server_default=None)`) so future inserts must rely on the ORM/app-level default rather than a stale DB default. `downgrade()` cleanly drops the column.
  - Confirmed `app/models/task.py`'s `evidence_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)` matches the migration's intent (ORM-level default `False`, matching the backfilled DB value).
  - This is a standard, safe add-nullable-then-tighten-style migration pattern; static review found no defects, but **actual execution against Postgres was never performed this session** and should be done before this ships.

## Concurrency
- 3 concurrency test files exist: `test_flight_concurrency.py`, `test_installation_concurrency.py`, `test_inventory_concurrency.py` — all in `tests/integration/`, all DB-dependent. **NOT VERIFIED — no reachable DB.**

## Security Scan
- `git diff --name-only` files scanned for: hardcoded secrets/passwords/API keys, production DB/URL strings, unsafe SQL string formatting, `dangerouslySetInnerHTML`, client-trusted `organization_id` patterns.
- **No hits on any pattern** in any of the 7 changed files (`task.py`, `release_readiness.py` schema, `release_readiness_service.py`, `test_release_readiness_service.py`, `RealReleaseReadinessPanel.tsx`, `release-readiness.ts`, `0035_task_evidence_required.py`).
- The service's new MATERIAL/COMPLIANCE blocker queries use SQLAlchemy `select(...).where(...)` with bound parameters throughout (no f-string/`.format()`/`%`-interpolated SQL found).
- Frontend files contain no `dangerouslySetInnerHTML` and no client-supplied `organization_id` usage (the readiness panel takes only `workOrderId` as a prop; org scoping happens server-side).

## Browser Verification
- **NOT VERIFIED.** Backend cannot start meaningfully against a real DB (no reachable Postgres), so a true end-to-end browser check of the release-readiness UI against live data was not attempted. No result is fabricated for this section.

## Defects Found (and fixed this session)
1. **Severity: Low-Medium (real regression risk / type-safety hole). Area: `backend/app/services/release_readiness_service.py` (M17.6 MATERIAL blocker logic).**
   Root cause: the new MATERIAL-blocker `for` loop reused the variable name `requirement` from the preceding INSPECTION-blocker loop, where it was typed `InspectionRequirement`. Mypy correctly flagged that reassigning it to `PartRequirement` and then accessing `.fulfilled_quantity`/`.required_quantity` (which don't exist on `InspectionRequirement`) was unsound — a real latent bug pattern (works today only because Python has no runtime type checking here; a future edit could easily break it silently).
   Fix: renamed the loop variable to `part_requirement`. Verified with `mypy` (0 errors, was 5), `ruff` (clean), and `pytest tests/unit/test_release_readiness_service.py` (19/19 passing, same as before the fix — no behavior change).
   Regression test: no new test needed — existing `test_material_no_blocker_when_fulfilled_quantity_met` / `test_material_no_blocker_when_cancelled_even_if_short` (and the other MATERIAL-blocker unit tests) already exercise this exact code path and continued to pass.
2. **Severity: Low (style/lint only). Area: `backend/tests/unit/test_release_readiness_service.py` lines 389, 412 (M17.6 test additions).**
   Root cause: two new `_part_requirement(...)` calls exceeded the 100-char ruff line-length limit.
   Fix: reformatted each call to one-argument-per-line. Verified `ruff check` now passes on the file; tests still 19/19.

## Pre-existing Issues (unrelated to M17.6, not touched)
- `ruff`: 2 pre-existing E501 violations in `tests/integration/test_asset_foundation.py:861` and `tests/integration/test_drone_lifecycle_api.py:424,463` — not part of this diff, left as-is.
- `eslint`: 54 warnings repo-wide, all `react-hooks/set-state-in-effect` (calling setState synchronously in `useEffect`) across `WelcomeTour.tsx`, `GlobalSearch.tsx`, `DataModeContext.tsx`, `lib/mock/ai/alertState.ts`, and `RealReleaseReadinessPanel.tsx:47` (the last one confirmed pre-existing via `git diff`, not introduced by M17.6), plus one unused eslint-disable directive in `tests/ai/lisa-matrix.test.ts`. Zero eslint errors.

## Remaining Gaps
- **No local Postgres could be started or verified this session** (Docker not installed in this environment; no native Postgres service found). This blocks: the full backend integration/regression suite, migration upgrade/downgrade execution against a real schema, tenant-isolation and RBAC integration tests, concurrency tests, and any browser-driven end-to-end verification. All of M17.2-M17.5's integration test coverage and the bulk of M17.6's real-world behavior (against actual DB rows) remain unexercised by this pass.
- No dedicated tenant-isolation test exists yet for release-readiness MATERIAL/COMPLIANCE/EVIDENCE blockers, PartRequirement, or the ComplianceAssessment/Inspection paths used by readiness — confirmed gap, not closed this session (would require a working DB to write and verify a meaningful test, not just an untestable stub).

## Overall Validation
**PASS WITH KNOWN ISSUES.**
Everything that could be verified without a database passed cleanly after two small, real, in-scope fixes (one mypy type-safety fix in the new MATERIAL-blocker code, one lint fix in the new test file): 19/19 M17.6 unit tests, 136/136 backend unit tests, 133/133 frontend tests, clean ruff/mypy on all M17.6 files, clean tsc, 0 eslint errors, successful production build, correct OpenAPI schema exposure of the new MATERIAL/COMPLIANCE blocker categories, a structurally sound migration, and a clean security scan. However, this is explicitly **not** a full validation: the entire integration-test suite (all M17.2-M17.6 DB-backed behavior), the actual migration upgrade/downgrade execution, tenant-isolation/RBAC/concurrency integration tests, and browser end-to-end verification could not be run because no local Postgres was reachable and Docker is not installed in this environment — these are marked NOT VERIFIED, not fabricated as passing.

## Recommended Next Action
Install Docker (or a native Postgres) in this environment and bring up the service already defined in `infra/docker-compose.yml`, then rerun `pytest` (full suite) and `alembic upgrade head` / `downgrade -1` / `upgrade head` against it — that single step unblocks every item currently marked NOT VERIFIED in this report.

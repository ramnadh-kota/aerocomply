# M17 Final Validation Report (2026-09-19)

This pass re-validates the M17.6 release-readiness extension (MATERIAL + COMPLIANCE
blockers, `Task.evidence_required`, migration `0035`) with a **real local PostgreSQL
16 instance** now available, closing every gap the prior DB-free pass
(`M17_TESTING_REPORT.md`, 2026-09-18) had to mark NOT VERIFIED.

## Environment

- Python 3.12.10, `backend/.venv` (pytest, pytest-asyncio, ruff, mypy installed).
- Node v24.19.0 / npm 11.17.0.
- PostgreSQL 16.15, native Windows service `postgresql-x64-16`, listening on
  `localhost:55432` (loopback). `aerocomply_dev` (the app's real dev DB, per
  `backend/.env`) confirmed empty at start (0 rows in `tasks`) and confirmed still
  0 rows at end — never used to run test suites, only for the direct migration
  upgrade/downgrade/upgrade verification below.
- **Test-infra defect found and worked around (not a code regression):**
  `backend/tests/integration/conftest.py` defaults `TEST_DATABASE_URL` to
  `postgresql+psycopg://aerocomply:aerocomply@localhost:5432/aerocomply_test` —
  port 5432, matching `infra/docker-compose.yml`, which is **not** what's running
  locally (native Postgres is on 55432). Confirmed via `psql -p 5432`: connection
  refused, nothing listens there. Without `TEST_DATABASE_URL` set correctly, every
  integration test errors out on fixture setup, and the whole run silently
  crawls for ~18 minutes accumulating 145 fixture errors before finishing. Fix
  applied (environment-only, no code/config file touched): created a new,
  dedicated `aerocomply_test` database on the existing local server
  (`CREATE DATABASE aerocomply_test;` via psql on port 55432, same `postgres`
  user) and exported `TEST_DATABASE_URL=postgresql+psycopg://postgres:***@localhost:55432/aerocomply_test`
  for each test invocation. This is a same-tier, local-only, additive change
  (a second local database, not a substitute engine, not touching `aerocomply_dev`
  or `infra/docker-compose.yml`/`backend/.env`). Recommend fixing the conftest.py
  default or documenting the required env var — flagged, not changed, since it's
  outside the M17.6 diff.
- Docker/Neo4j/Redis/MinIO: still not running (Docker unavailable, needs WSL2 +
  reboot, previously ruled out). No test in the executed suite required them —
  confirmed by the fact the full suite ran to completion with a clear pass/fail
  count and no hangs once `TEST_DATABASE_URL` was corrected.

## Migration Validation — PASS

All commands run directly against `aerocomply_dev` (fresh/empty at migration start).

1. `alembic current` (before): no revision stamped (fresh DB).
2. `alembic upgrade head`: ran all 35 migrations (`0001` → `0035`) cleanly, ending
   at `Running upgrade 0034 -> 0035, M17.6A: add Task.evidence_required.` No errors.
3. Verified via direct `psql \d tasks`: `evidence_required | boolean | not null`
   (no server default shown, matching the migration's backfill-then-drop-default
   pattern) — exactly matches `Task.evidence_required: Mapped[bool]` in
   `backend/app/models/task.py`.
4. `alembic downgrade -1`: ran `0035 -> 0034` cleanly. Re-checked `\d tasks`:
   `evidence_required` column **absent** (confirmed by empty grep). Row count
   before and after: 0 and 0 (table was empty throughout; no data loss possible
   and none occurred).
5. `alembic upgrade head` again: re-ran `0034 -> 0035` cleanly. Re-checked
   `\d tasks`: column present again with the same boolean/not-null shape.
6. `alembic heads`: `0035 (head)` — exactly one head, no branching/divergence.

**Result: full upgrade → downgrade → upgrade cycle verified against a real
database. Single clean head. No defects found.**

## Backend — Targeted Tests (real DB, `aerocomply_test`)

Targeted files for M17.2 (drone/battery/component lifecycle + concurrency), M17.3
(flight/utilization/concurrency), M17.4 (maintenance due/accomplishment), M17.5
(battery/component maintenance), M17.6 (release readiness, part requirement,
compliance, evidence reconciliation, inspection identity), plus tenant isolation:

```
tests/integration/test_drone_lifecycle_api.py
tests/integration/test_drone_operations.py
tests/integration/test_installation_concurrency.py
tests/integration/test_flight_api.py
tests/integration/test_flight_concurrency.py
tests/integration/test_drone_maintenance.py
tests/integration/test_battery_component_maintenance.py
tests/integration/test_release_readiness_full_chain.py
tests/integration/test_part_requirement_service.py
tests/integration/test_compliance_service.py
tests/integration/test_evidence_reconciliation_service.py
tests/integration/test_inspection_completion_identity_api.py
tests/integration/test_tenancy_isolation.py
tests/integration/test_inventory_concurrency.py
tests/unit/test_release_readiness_service.py
```

**Result: `167 passed, 0 failed` in 15.34s.** (First attempt against the wrong
port hung for ~18 minutes and produced 145 fixture errors + 3 failures — that was
the `TEST_DATABASE_URL` defect above, not a real result; discarded once fixed.)

## Backend — Full Suite

`pytest -q -m "not real_storage"` (respecting the existing marker default), real DB:

**Result: `981 passed, 1 failed, 16 deselected` in 92.52s.**

The one failure: `tests/integration/test_aog_recovery_service.py::test_full_supply_chain_progression_updates_blocker_category`
— asserts that after a purchase-order receipt fully satisfies a part shortage, no
`MATERIAL_*`-prefixed blocker remains in `aog_recovery_service.get_recovery_status()`.// `assert not any(c.startswith("MATERIAL") for c in categories)` fails.

**Classification: pre-existing / out-of-scope, not an M17.6 regression.**
`git diff --name-only HEAD` confirms the M17.6 diff touches exactly 7 files
(`task.py`, `release_readiness.py` schema, `release_readiness_service.py`,
its unit test, `RealReleaseReadinessPanel.tsx`, `release-readiness.ts`,
`next-env.d.ts`). The failing test exercises `aog_recovery_service.py`,
`procurement_service.py`, `purchase_order_service.py`, and `receiving_service.py`
— none of which are in that diff, and none of which were read or modified this
session. This is a different blocker-vocabulary path (`aog_recovery_service`'s
own `MATERIAL_AWAITING_APPROVAL` / `MATERIAL_PO_NOT_SENT` / etc. categories) from
the one M17.6 touched (`release_readiness_service.py`'s `MATERIAL` blocker
category). Per instructions, this was left unfixed as a real, small, but
**out-of-scope** defect — fixing it would mean debugging PartRequirement
recompute-on-receipt logic in files this milestone never changed. Verified the
working tree was not altered while investigating this (`git stash`/`git stash pop`
used only to temporarily probe whether the bug predates the M17.6 diff; confirmed
`git status` afterward is identical to before — same 7 modified + 4 untracked
files, nothing lost).

## Backend — Static Analysis

- `ruff check app/`: **All checks passed.** (repo-wide, not just M17.6 files)
- `mypy app/`: **Success: no issues found in 210 source files.** (repo-wide)
- Both fully clean; no pre-existing issues found anywhere in `app/` this pass
  (the two pre-existing `tests/integration/*.py` E501s noted in the prior DB-free
  report are in `tests/`, not scanned by this `app/`-scoped repeat, and were not
  re-touched).
- M17.6-file-scoped `ruff`/`mypy` re-confirmed clean as well (same result as the
  prior DB-free pass, which had already fixed the one mypy loop-variable bug and
  two line-length violations — no new issues found this pass).

## Frontend

- `npx vitest run`: **8 test files passed, 133 tests passed, 0 failed**, 2.36s.
- `npx tsc --noEmit`: clean, no output.
- `npx eslint .`: **0 errors, 54 warnings** (all pre-existing `react-hooks/set-state-in-effect`
  plus one unused eslint-disable directive — identical warning set to the prior
  DB-free pass, confirming no new lint issues from anything done this session).
- `npm run build`: succeeded, full route manifest generated (including
  `/maintenance/release-readiness`), no build errors.

All four match the prior DB-free pass exactly — no regressions introduced by
anything done in this DB-backed pass (no code was changed this session).

## Tenant Isolation

- `tests/integration/test_tenancy_isolation.py`: **8/8 passed** (aircraft, work
  order, deferred item, purchase order, assessment, evidence get/create, Lisa
  aircraft-registration resolution) — all cross-tenant-cannot-access assertions
  now verified against the real DB.
- **Confirmed gap (unchanged from `M17_6_AUDIT.md`):** no dedicated tenant-isolation
  test exists for the release-readiness endpoint itself, `PartRequirement`,
  `ComplianceAssessment`-as-used-by-readiness, or `InspectionRequirement`-as-used-by-readiness.
  Not added this session per instructions (writing one and validating it properly
  is real test-authoring work, not "run what exists").

## RBAC

- `tests/unit/test_permissions.py`: included in the unit run, passing (DB-free).
- Integration-embedded RBAC assertions (`TestFlightRBAC`, `TestMaintenanceRBACAndTenantIsolation`,
  etc.) all passed as part of the 167/167 targeted run and the 981/982-deselected
  full run above — now genuinely DB-verified, not just collected.
- No dedicated RBAC-only file exists per domain; this remains embedded-in-domain-tests,
  as previously noted — a structural gap, not a failure.

## M17.2 — Battery/Component Lifecycle

`test_drone_lifecycle_api.py`, `test_drone_operations.py`,
`test_installation_concurrency.py`: all passed as part of the 167/167 targeted
run. Real DB-backed lifecycle transitions and concurrent-installation guards
verified.

## M17.3 — Flight / Utilization

`test_flight_api.py`, `test_flight_concurrency.py`: all passed (pagination,
detail, tenant isolation, RBAC, validation, utilization-regression subtests, and
the dedicated concurrency test). Real DB-backed.

## M17.4 — Maintenance Due / Accomplishment

`test_drone_maintenance.py`: all passed (applicability linking, usage-based
due/overdue/not-due evaluation, accomplishment interval reset, tenant isolation,
deployment-readiness regression). Real DB-backed.

## M17.5 — Battery/Component Maintenance

`test_battery_component_maintenance.py`: all passed (usage evaluation for both
battery and component, installation-aware usage non-transfer, RBAC + tenant
isolation, validation). Real DB-backed.

## M17.6 — MATERIAL / COMPLIANCE / EVIDENCE

- `tests/unit/test_release_readiness_service.py`: **19/19 passed**, using
  `_FakeSession` — this file is **mock-based, not a real DB session** (confirmed
  by reading the file: `class _FakeSession` at line 36, instantiated in every
  test). It validates the MATERIAL/COMPLIANCE/EVIDENCE blocker *logic* in
  isolation from persistence.
- `tests/integration/test_release_readiness_full_chain.py::test_full_readiness_chain`:
  **passed**, real DB, real HTTP client (`TestClient`) — walks
  TASK_EXECUTION → EVIDENCE → INSPECTION blockers end to end against actual
  Postgres rows created through the real API. This test predates M17.6 and does
  **not** exercise the new MATERIAL/COMPLIANCE categories (no `PartRequirement`
  or `ComplianceAssessment` setup in it) — so MATERIAL/COMPLIANCE behavior is
  verified by the DB-free unit tests' logic correctness, not yet by an
  end-to-end DB-backed HTTP test. This is a genuine, confirmed gap (not fixed
  this session — writing a new integration test is out of "run what exists").
- `tests/integration/test_part_requirement_service.py` (7 tests) and
  `tests/integration/test_compliance_service.py` (6 tests): all passed, real DB
  — these validate the underlying `PartRequirement`/`ComplianceAssessment`
  service layer that `release_readiness_service.py`'s MATERIAL/COMPLIANCE
  blockers read from, just not through the readiness endpoint itself.
- `tests/integration/test_evidence_reconciliation_service.py` (19 tests) and
  `test_inspection_completion_identity_api.py` (4 tests): all passed, real DB.

## Deployment Readiness Integration

`test_release_readiness_full_chain.py` (see above) is the only
end-to-end chain test and it passed. No additional drone→flight→usage→maintenance→readiness
chain test exists in `tests/integration/`; not hand-built this session per
instructions (prioritize running what exists).

## Concurrency / Data Integrity

`test_flight_concurrency.py`, `test_installation_concurrency.py`,
`test_inventory_concurrency.py`: **3/3 passed** against the real DB (all three
ran in 0.57s combined as a standalone re-run, and were also part of the 981-pass
full-suite run).

## Performance / Query Review

No existing test asserts a query count for release-readiness or maintenance-due
evaluation, so this is a **code-review finding, not a measured one** —
explicitly distinguished per instructions:
- `get_release_readiness_for_work_order()` in
  `backend/app/services/release_readiness_service.py` issues exactly 6 `SELECT`s
  total regardless of row counts: work order, tasks, evidence
  (`Evidence.task_id.in_(task_ids)`), inspection requirements
  (`or_(work_order_id==..., task_id.in_(...))`), part requirements, compliance
  assessments. Every blocker-category loop iterates over an already-fetched
  Python list (`for task in tasks`, `for part_requirement in part_requirements`,
  etc.) — no query is issued inside any of these loops. **No N+1 pattern found**
  in this service.

## Browser Smoke Test — NOT VERIFIED

Not attempted. Driving both a live `uvicorn` backend against the real DB and the
frontend dev server together through a browser was out of scope for this pass's
time budget and wasn't explicitly required beyond "if you attempt it" — no
fabricated browser results are reported.

## Security Review

`git diff --name-only HEAD` (same 7 files as the prior pass) re-scanned for
secrets, production references, unsafe SQL, `dangerouslySetInnerHTML`, and
client-controlled `organization_id`. **No hits.** Confirmed by direct code
reading of `release_readiness_service.py` (all queries use bound
SQLAlchemy `select().where()`, no string interpolation) and
`app/api/v1/release_readiness.py` (organization_id comes only from
`current_user.organization_id`, the authenticated session — never from any
request body, query param, or path param — so a client cannot override it for
this endpoint). No new findings beyond the prior pass.

## Git / Environment Audit

- `git status --short`: unchanged from session start — same 7 modified files
  (`backend/app/models/task.py`, `backend/app/schemas/release_readiness.py`,
  `backend/app/services/release_readiness_service.py`,
  `backend/tests/unit/test_release_readiness_service.py`,
  `frontend/components/evidence/RealReleaseReadinessPanel.tsx`,
  `frontend/lib/api/release-readiness.ts`, `frontend/next-env.d.ts`) plus 4
  untracked files (`M17_6_AUDIT.md`, `M17_6_REPORT.md`, `M17_TESTING_REPORT.md`,
  `backend/alembic/versions/0035_task_evidence_required.py`). **No code changes
  were made this session** — this pass was validation-only; the one real defect
  found (`test_aog_recovery_service.py` failure) was diagnosed but intentionally
  left unfixed as out-of-scope.
- `git diff --stat HEAD`: 7 files changed, 518 insertions(+), 21 deletions(-) —
  same as tracked at session start.
- `git log --oneline -8`: HEAD still `f31dbe4` (M17.5). Nothing committed, nothing
  pushed, no destructive git operations performed.
- No secrets found in any file touched or created this session (Postgres password
  never printed to any file, including this report).
- Test-infra note: a new local-only Postgres database `aerocomply_test` now
  exists on the same native Postgres 16 instance (port 55432) alongside
  `aerocomply_dev`. This is additive infrastructure (a second empty/test
  database on an already-local, already-approved server), not a config-file
  change — `infra/docker-compose.yml` and `backend/.env` were not modified.

## Final Status: VERIFIED WITH KNOWN NON-BLOCKING ISSUES

Still NOT VERIFIED / explicitly open, and why:
1. **Browser end-to-end smoke test** — not attempted (time/scope), no fabricated
   result reported.
2. **Neo4j/Redis/MinIO-dependent behavior** — none was found in the executed
   suite (it ran to completion with a clean pass/fail count), but no explicit
   audit was made for whether any *skipped/deselected* test (16 deselected, the
   `real_storage`-marked ones) requires them — those 16 are excluded by the
   existing `-m "not real_storage"` marker, per the same convention the prior
   pass used, and were not run.
3. **MATERIAL/COMPLIANCE blockers at the real-DB, end-to-end HTTP level** — the
   logic is proven correct by 19/19 DB-free unit tests and the underlying
   `PartRequirement`/`ComplianceAssessment` service layers are proven correct by
   their own real-DB integration tests, but no integration test yet drives the
   `/release-readiness` endpoint itself into a MATERIAL or COMPLIANCE blocker
   state through real HTTP + real DB rows (only EVIDENCE/INSPECTION/TASK_EXECUTION
   are covered end-to-end by `test_release_readiness_full_chain.py`). Confirmed
   gap, not closed this session (would be new test-writing, out of "run what
   exists").
4. **Dedicated tenant-isolation/RBAC tests for release-readiness, PartRequirement,
   ComplianceAssessment-via-readiness, Inspection-via-readiness** — confirmed
   absent (same gap `M17_6_AUDIT.md` originally flagged), not added this session.
5. **One pre-existing, out-of-scope test failure**
   (`test_aog_recovery_service.py::test_full_supply_chain_progression_updates_blocker_category`)
   remains unfixed — diagnosed as belonging to files entirely outside the M17.6
   diff; fixing it would be a separate, unrelated milestone's work.

Everything else in scope — migration upgrade/downgrade/upgrade/single-head,
167/167 targeted tests, 981/982 full suite (1 pre-existing/out-of-scope failure),
repo-wide ruff/mypy clean, frontend vitest/tsc/eslint/build all clean and
unchanged from the prior pass, tenant isolation and concurrency tests passing
for real against Postgres, a clean security re-scan, and a verified-clean git
state — is genuinely, not fabricated, **VERIFIED**.

# M20.2 — General Finding/Disposition Backend Domain Model

## 1. Selected milestone

**General Finding/Disposition backend domain model** — the milestone pre-selected in the task instructions (M20.2 in the M20 audit's roadmap), not re-litigated.

## 2. Why it was selected

Per the M20 audit (`M20_AUDIT_AND_ROADMAP.md` §1.3/§1.9), the backend already has a real, well-modeled `AssessmentFinding` table (`backend/app/models/assessment.py:111-134`), but it is scoped exclusively to the compliance-assessment pipeline (always belongs to an `AssessmentSnapshot`). There was no general Finding/Disposition concept usable directly from inspections, work orders, or maintenance tasks, and `frontend/lib/mock/findings.ts` was a disconnected mock concept already rendering on the dashboard. This milestone builds the missing general model first so the Finding→Disposition→Corrective Action→Closure chain — a stated dependency of the compliance/readiness/dashboard/LISA layers — is real before those layers are built on top of it.

## 3. Files/components changed

Backend (new):
- `backend/app/models/finding.py` — `Finding`, `FindingDisposition` models + `FindingSeverity`/`FindingStatus`/`DispositionType` constants
- `backend/app/schemas/finding.py` — request/response Pydantic schemas
- `backend/app/services/finding_service.py` — create/get/list/add_disposition/close_finding, tenant-scoped fetch-or-404, audit events
- `backend/app/api/v1/findings.py` — `/findings` router (create, list, get, add disposition, close)
- `backend/alembic/versions/0036_finding_disposition.py` — migration
- `backend/tests/unit/test_finding_lifecycle.py` — 7 service-level unit tests
- `backend/tests/integration/test_finding_api.py` — 6 API-level integration tests

Backend (modified):
- `backend/app/models/__init__.py` — registers the new models
- `backend/app/api/v1/router.py` — mounts `findings.router`

Frontend (new):
- `frontend/lib/api/findings.ts` — typed REAL-mode API client for `/findings`

Frontend (modified):
- `frontend/app/(app)/aircraft/[id]/page.tsx` — adds an `AircraftFindingsPanel` component to the REAL-data-mode aircraft detail view (list findings for the aircraft, raise a new finding, add a "No Action Required" disposition, close a finding). DEMO mode and every other page/route are untouched.

## 4. Database changes

Migration `0036_finding_disposition` (revises `0035`):
- Creates `findings`: tenant-scoped (`organization_id`), UUID PK, optional FKs to `aircraft`, `assets` (dual aircraft/asset pattern mirroring `WorkOrder`), `components`, `inspection_requirements`, `work_orders`, `tasks`; `title`, `description`, `severity`, `status` (default `OPEN`), `discovered_at`, `discovered_by_user_id`, `responsible_user_id`, `updated_at`. Indexes on `organization_id` and every FK column.
- Creates `finding_dispositions`: tenant-scoped, UUID PK, FK to `findings` and optionally `evidence`; `disposition_type`, `corrective_action`, `evidence_id`, `closed_at`, `closed_by_user_id`.
- Purely additive — no existing table altered.
- **Verified**: `alembic upgrade head` → `alembic downgrade -1` → `alembic upgrade head` all ran clean against local Postgres (`localhost:55432/aerocomply_dev`), confirmed back at `0036 (head)` afterward.
- An initial `alembic revision --autogenerate` run surfaced a large amount of pre-existing, unrelated schema drift (stale NOT NULL/unique-constraint diffs across many older tables) already present in the dev DB before this session — that generated file was discarded and a hand-written, scoped migration was committed instead so this milestone only touches the two new tables.

## 5. API changes

New router `backend/app/api/v1/findings.py`, mounted at `/api/v1/findings`:
- `POST /findings` — create (requires `INSPECTION_WRITE`); `organization_id` always server-derived from the authenticated user, never client-supplied; requires at least one traceable link (aircraft/asset/component/inspection/work-order/task id).
- `GET /findings` — list, filterable by `aircraft_id`, `asset_id`, `work_order_id`, `status` (requires `INSPECTION_READ`).
- `GET /findings/{id}` — detail (requires `INSPECTION_READ`); cross-tenant access returns 404.
- `POST /findings/{id}/dispositions` — add a disposition (requires `INSPECTION_WRITE`); moves `OPEN` → `IN_PROGRESS`; rejects a `CORRECTIVE_ACTION` disposition with no `corrective_action` text; rejects dispositioning an already-`CLOSED` finding.
- `POST /findings/{id}/close` — close (requires `INSPECTION_WRITE`); requires at least one prior disposition; stamps `closed_at`/`closed_by_user_id` on the latest disposition and sets `Finding.status = CLOSED`.

No dedicated `finding:*` permission was added — `INSPECTION_READ`/`INSPECTION_WRITE` were reused since a general finding is raised through the same inspection/maintenance workflows those permissions already gate, matching the codebase's stated precedent of not adding a narrower permission unless nothing existing fits.

## 6. UI changes

Minimal, single-screen wiring as scoped: the aircraft detail page's existing REAL-data-mode branch (`frontend/app/(app)/aircraft/[id]/page.tsx`) now renders a "Findings (live)" panel below the aircraft record card when a user is authenticated. It lists findings for that aircraft from the real backend, supports raising a new finding (title/description/severity), adding a "No Action Required" disposition, and closing a finding — all live API calls, no mock data. DEMO mode, `lib/mock/findings.ts`, and the dashboard's existing (mock) findings usage were not touched, per scope. No new chart library or design-token changes; existing `.ac-card`/`.ac-input`/`.ac-btn`/`StatusBadge` tokens from `globals.css` were reused as-is.

## 7. Existing systems reused

- Dual `aircraft_id`/`asset_id` relationship pattern (from `WorkOrder`/`Component`)
- `entity`-traceability shape and tenant-scoped fetch-or-404 pattern (from `AssessmentFinding`/`InspectionRequirement`)
- `record_audit_event` call convention (from `inspection_service.py`)
- `require_permission(Permission.INSPECTION_READ/WRITE)` RBAC gate (from `inspections.py`)
- `RealDataPanel`/`useDataMode`/`useSession`/`apiRequest` frontend REAL-mode conventions (from `aircraft.ts`/`inspections.ts` API clients and the existing aircraft detail page)

## 8. Tests executed (exact counts)

- Targeted new tests: `pytest tests/unit/test_finding_lifecycle.py tests/integration/test_finding_api.py` → **13 passed** (7 unit + 6 integration), 0 failed.
- Full backend suite: `pytest` (full run, `TEST_DATABASE_URL` pointed at local Postgres `aerocomply_test`) → **1010 passed, 16 deselected, 0 failed** (prior verified baseline was 997 passed; +13 is exactly the new Finding tests — no regressions).
- Full frontend suite: `npx vitest run` → **140 passed** (9 test files), unchanged from the stated 140 baseline — no new frontend test file was added since the new component is thin API-wiring with no existing precedent in this repo for a dedicated component test at that scope; `npx tsc --noEmit` also ran clean (no type errors).

## 9. Browser verification

**Not performed via a real browser this run.** No live dev server / browser tooling was exercised for this milestone. Verification was via:
- Direct Postgres migration execution (`alembic upgrade/downgrade/upgrade`, confirmed via `alembic current`) against local Postgres.
- The full backend integration test suite (`tests/integration/test_finding_api.py`), which exercises the real FastAPI app + real Postgres-migrated schema end-to-end via `TestClient`, including: create → list-scoped-to-aircraft → add disposition → close, tenant isolation (404 across orgs), RBAC/authentication (401 unauthenticated), and audit event verification — this is real HTTP + real DB, not mocked, but it is not a browser session.
- Frontend: `tsc --noEmit` and `vitest run` only; the new `AircraftFindingsPanel` UI itself was not clicked through in a running browser against a live backend in this session.

This is explicitly weaker than the task's preferred verification path and is called out here rather than claimed as done.

## 10. Known limitations

- The frontend panel only supports a "No Action Required" quick-disposition action in the UI (not a full disposition-type picker with corrective-action text entry) — the API supports all three disposition types; the UI exposes one path plus Close, kept intentionally minimal per scope ("proving the capability is real and reachable," not full CRUD UI).
- No dedicated frontend unit/component test was added for `AircraftFindingsPanel` (see §8).
- `Finding.status` transitions are not state-machine-enforced as rigidly as `InspectionRequirement`'s `_ALLOWED_TRANSITIONS` table (e.g. nothing stops adding further dispositions once `IN_PROGRESS`) — acceptable for this slice since Finding's lifecycle is simpler (no analogue to RII independence), but worth tightening if a future milestone needs stricter guarantees.
- No UI browser verification was performed (see §9).

## 11. Explicitly deferred items

- Replacing `lib/mock/findings.ts`'s dashboard usage with the new real model (explicitly out of scope this run; targeted at M20.3 in the roadmap).
- Any dashboard KPI backed by the new Finding model.
- Wiring Findings into drone/asset detail pages or work-order detail pages beyond the one aircraft detail page done here.
- A full disposition-type picker / corrective-action text entry in the UI.
- Navigation, LISA, and any staging/production changes — untouched, per the absolute boundaries.

## 12. Local commit hash

`fad9ae1` — "feat(findings): general Finding/Disposition backend domain model (M20.2)"

---

## BEFORE / AFTER

**Before**: Findings existed only as `AssessmentFinding`, permanently scoped to the compliance-assessment pipeline (never reachable from an inspection or work order directly), plus a disconnected mock (`lib/mock/findings.ts`) rendering on the dashboard with no backend behind it.

**After**: A tenant-scoped `Finding`/`FindingDisposition` pair exists in Postgres (migration `0036`, verified up/down/up), with a full CRUD + disposition/closure API (`/api/v1/findings`, RBAC-gated, audit-logged, tenant-isolated — cross-org access 404s), 13 passing backend tests, and one real, live-data UI surface (the aircraft detail page) proving the capability end-to-end via automated HTTP tests. Full backend suite: 1010/1010 passing (no regressions from the 997 baseline). Full frontend suite: 140/140 passing, typecheck clean.

## Next recommended milestone

**M20.3 — wire the dashboard's existing mock Findings widget to this new real Finding model** (replacing `lib/mock/findings.ts`'s dashboard-only usage), since that is the next item in the roadmap this milestone was explicitly built to unblock.

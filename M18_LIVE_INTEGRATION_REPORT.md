# M18 — Live Backend Integration Report

Date: 2026-09-19
Scope: Milestone M18 — connect existing frontend product screens to the existing backend architecture (no new product functionality, no redesign).
Environment used for all verification in this report: **LOCAL ONLY** — native Postgres 16 service on `localhost:55432` (dev DB `aerocomply_dev`), backend `uvicorn` on `http://127.0.0.1:8001`, frontend `next dev` on `http://localhost:3000`. Staging (`aerocomply-backend-staging.onrender.com`) and production Neon were never touched, queried, or written to.

---

## 0. How this report is organized

Section 1–2 is the full read-only audit (Phases A/B/E) completed earlier this session, before any verification work. Section on "Screen actually wired and verified this round" covers the one slice this session drove end-to-end with a real browser and a real local backend/database. Every other screen listed in Section 1 is **not** touched by this session and must not be read as done.

Two confidence levels are used throughout and must not be conflated:
- **PROVEN (browser/DB verified)** — I drove an actual browser against actual local servers and a real Postgres row, and/or hit the real endpoint with `curl`, and observed the actual response/render.
- **READ (code-verified only)** — I read the source and it appears correct, but I did not execute it this session.

---

## 1. Frontend audit — full mock/live mapping (Phase A)

### 1.1 `frontend/lib/mock/**` inventory
All are TypeScript modules exporting static/demo fixture data (aircraft, assessments, audit log, cannibalization, checklists, components, defects, deferredItems, documentLibrary, engines, evidence, evidenceRecords, finance, findings, inspectorReviews, integrations, kleene, maintenance, maintenanceAccomplishments, maintenanceProgram, maintenanceProjects, maintenanceTasks, organizations, parts, partTraceability, procurement, regulations, reports, roles, search, technicians, types, workOrders, plus an `ai/*` derived-analytics layer built on top of them). Only `frontend/tests/ai/lisa-matrix.test.ts` uses these as a test fixture — every other reference (~90+ files) is inside `frontend/app/**` or `frontend/components/**` render code, i.e. these are live UI data sources today, not scaffolding (Phase E classification below).

### 1.2 `frontend/lib/api/**` inventory (already-existing typed REAL-mode clients)
`drones.ts`, `aircraft.ts`, `compliance.ts`, `inspections.ts`, `workOrders.ts`, `deferred-items.ts`, `evidence.ts`/`evidenceFiles.ts`, `release-readiness.ts`, `technicians.ts`, `parts.ts`, `facilities.ts`, `platform.ts`, `productCatalog.ts`, `purchaseOrders.ts`/`procurementRequests.ts`/`vendors.ts`, `assessments.ts`, `aogRecovery.ts`, `controlCenter.ts`, `dataImport.ts`, `inventory.ts`, `entitlement.ts`/`subscription.ts`, `lisa.ts`/`lisaContext.ts`/`proactive.ts`, `health.ts`, `approvals.ts`/`tasks.ts`/`plan.ts`. Each maps 1:1 to a `backend/app/api/v1/*.py` router; none send `organization_id` from the client (server derives it from the JWT via `get_current_user`/`require_permission`).

### 1.3 Important correction to my own earlier (pre-verification) audit
My initial pass classified several screens as "mock" or "dual, half-done." Reading the actual page components this round showed that is wrong for at least two screens: **Technicians** (`frontend/app/(app)/maintenance/technicians/page.tsx`) and **Deferred Items / MEL** (`frontend/app/(app)/maintenance/deferred/page.tsx`) are **already fully implemented** as dual DEMO/REAL components, gated by `frontend/lib/data-mode/DataModeContext.tsx` (`useDataMode().isReal`, persisted to `localStorage["aerocomply-data-mode"]`, default `DEMO`). Their `Real*List` components already use `useSession()`, the correct typed `lib/api/*` client, `RealDataPanel` for loading/empty/error chrome, and `normalizeApiError`. This existing pattern (established, per in-file comments, across earlier M18/M19/Phase-C work) was written but — as far as I can determine from git history and the absence of any prior browser-driven verification in this repo's test suite — never proven against a live browser + live local Postgres. That gap is what this session closed for one of the two.

### 1.4 Screen-by-screen mapping

| Screen | Source | Backend endpoint | Notes |
|---|---|---|---|
| Drone list/detail, flights, lifecycle timeline, battery/component maintenance | **live** | `drones.py` (full CRUD/lifecycle) | Already integrated (M17.5/17.6) — reference pattern |
| Facilities | **live** | `facilities.py` | |
| Data import | **live** | `data_import.py` | |
| Platform admin (orgs, plans, product catalog, approvals, audit, monitoring) | **live** | `platform.py`, `product_catalog.py`, `entitlements.py` | Fully integrated |
| Compliance regulatory register | **live** | `compliance.py` | |
| Release readiness / task-gate panel (embedded in work-order detail) | **live** | `/work-orders/{id}/release-readiness`, evidence endpoints | |
| Evidence files panel (embedded) | **live** | `/evidence/{id}/files` (list/download/delete) | |
| **Technicians list/detail** | **dual, REAL implemented** (`usersApi`, `technicianQualificationsApi`) | `GET /users`, `GET /technician-qualifications` | Code-verified only this session (not driven in browser) |
| **Deferred Items / MEL** | **dual, REAL implemented and PROVEN this session** | `deferred_items.py` full CRUD + `/aircraft/{id}/deferred-items`, `/fleet/deferred-items` | See Section 3 |
| Aircraft list/detail | **dual** | `aircraft.py` | Code-verified only |
| Maintenance work orders list/detail | **live**, legacy checklist mock in detail sub-panel | `work_orders.py`, `/tasks` | |
| Inspections list | **dual** (mock legacy UI + live `inspectionsApi`) | `inspections.py` | Additive `RealDataPanel` pattern |
| Compliance (main dashboard-style page) | **dual** | `compliance.py` | Additive pattern |
| Parts list | **live**; **Parts detail = mock** | `parts.py`/`part_requirements.py` | Detail not wired |
| Dashboard | **mock** | **MISSING** — no consolidated dashboard/analytics endpoint exists; nearest pieces are `fleet/maintenance-due` and `fleet/deferred-items` | Backend gap |
| Components list/detail | **mock** | **MISSING** fleet-wide `GET /components` (only per-asset `/drones/{id}/components` and single `GET /components/{id}` exist) | Backend gap |
| Release readiness **queue** page (as opposed to the embedded per-work-order panel) | **mock** | No "list release-blocked work orders" endpoint exists | Backend gap |
| Evidence list | **mock** | **MISSING** fleet-wide `GET /evidence` (only `POST`, `GET /{id}`, `/transition`, `/files` exist) | Backend gap |
| Evidence detail | **mock**, and a **genuine domain-model mismatch** (see 1.5) | `GET /evidence/{id}` exists but shape doesn't match the mock UI's model | Not a small extension — flagged, not attempted |
| Maintenance program | **mock** | `maintenance.py` has `/maintenance-requirements` only — program/accomplishment concept unmodeled | Backend gap |
| Compliance pre-audit | **mock** | No dedicated endpoint | Backend gap |
| Procurement (cart, approvals, most pages) | **mock**, `purchase-orders` page = live | `purchase_orders.py`/`procurement.py`/`vendors.py` exist for the modeled parts; cart/approval workflow concepts don't exist server-side | Backend gap for cart/approvals |
| Organization (roles/users/plan/readiness/usage) | `plan` = live; rest = **mock** | `entitlements.py` backs plan; `users.py`/`auth.py` exist but pages not wired | Wiring gap, not a backend gap |
| Control tower | **mock** | No backend equivalent (`control_center.py` only backs `control-center`, a different page) | Backend gap |
| Assessments list/detail | **mock** | `assessments.py` exists; `lib/api/assessments.ts` exists and is unused by these pages | Wiring gap |
| Settings/Notifications/Documents/Integrations/Reports/Automation/Executive/Workspace/Pilot | **mock**, largely static-copy/prototype-labeled | No corresponding backend routes | Out of core M18 scope |

### 1.5 Evidence detail — why it was not swapped
The mock `evidenceRepository` model (`evidenceType`, `sourceLabel`, `applicabilityAssessmentId`, `linkedWorkOrderId`, `linkedPartId`, `uploadedBy`, `verificationStatus`) is a materially different domain shape from the real backend `BackendEvidence` (`id`, `organization_id`, `task_id`, `uploaded_by_user_id`, `status`, `reviewer_user_id`, `rejection_reason`, `created_at` — a task-status lifecycle record, not a document/record-linkage model). Swapping this without a data-model reconciliation would either fabricate fields the backend doesn't have or silently drop the linked-records section. This was read but intentionally not touched.

---

## 2. Backend gaps found (Phase B)

Confirmed **missing** endpoints (not just missing frontend wiring) — each would need new, small, pattern-consistent backend work, not attempted this session per the no-new-architecture boundary:
1. Fleet-wide `GET /components` (only per-asset and per-id single lookups exist in `drones.py`).
2. Fleet-wide `GET /evidence` list-all.
3. A consolidated dashboard/fleet-analytics endpoint (or explicit client-side composition of `fleet/maintenance-due` + `fleet/deferred-items` + others).
4. A "list release-blocked work orders" queue endpoint (the per-work-order `release-readiness` endpoint already exists and is already wired into the work-order detail panel).
5. Maintenance-program/accomplishment concept — unmodeled server-side.
6. Compliance pre-audit — unmodeled server-side.
7. Procurement cart/approvals workflow — unmodeled server-side (PO/vendor pieces do exist).
8. Control-tower — unmodeled server-side (distinct from the already-live `control-center`).

---

## 3. Screen actually wired and verified this round — Deferred Items / MEL

**Important correction from my last message to the coordinator:** I initially proposed treating this as a "replace mock with live client" task. On inspection, `frontend/app/(app)/maintenance/deferred/page.tsx` already contains a complete `RealDeferredItemsList` implementation (REAL branch) alongside the original `DemoDeferredItemsPage` (DEMO branch), switched by `useDataMode()`. **No source code needed to be written or changed** — the gap was that this real implementation had, as far as I could verify, never actually been run end-to-end against a live backend and browser. I made **zero commits** this round because there was no code change to commit; what follows is verification work only.

### 3.1 Local environment actually stood up
- Docker Desktop is unavailable in this sandbox (`Error response from daemon: Docker Desktop is unable to start`) — infra `docker compose up -d` could not be run.
- A **native Windows Postgres 16 service** (`postgresql-x64-16`) was already running and listening on `127.0.0.1:55432`, matching `backend/.env`'s `DATABASE_URL` (`aerocomply_dev`, already migrated to Alembic head `0035`). I connected to it directly (verified via `psycopg`) and used it — this is local Postgres, not staging, not production.
- Backend: `uvicorn app.main:app` started on `127.0.0.1:8001` (matching `frontend/.env.local`'s `NEXT_PUBLIC_API_BASE_URL=http://localhost:8001/api/v1`). Health check: `GET /api/v1/health` → `{"status":"ok"}`.
- Frontend: `npm run dev` (Next.js/Turbopack) started on `http://localhost:3000`, confirmed `200`.
- Neo4j/Redis/MinIO (also in the compose file) were **not** started — not needed for this slice (aircraft/deferred-items endpoints don't depend on them) and not exercised.

### 3.2 Real local test data created (local only, not staging)
- `POST /api/v1/auth/register-organization` → created org **"M18 QA Org"** (`org_id=6eefaa47-7f0e-4662-b579-50d6a61e5aa5`) and admin user `m18qa@example.com` (`ORG_ADMIN` role) — same pattern as `backend/tests/integration/test_auth_flow.py::test_register_login_me_roundtrip`.
- A second org, **"M18 QA Org B"** (`admin: m18qa-b@example.com`), created for the tenant-isolation check in 3.4.
- `POST /api/v1/aircraft` → created aircraft `N18QA1` (msn `MSN-18QA-001`) under Org A.
- `POST /api/v1/deferred-items` → created a deferred item (`MEL-18-QA`, category B, MEL basis) against that aircraft, `approval_required=false`.

### 3.3 Browser-driven E2E — PROVEN
Using the Browser tool against `http://localhost:3000`:
1. Logged in as `m18qa@example.com` via the real `/login` form → real `POST /auth/login` + `GET /auth/me` round trip (not client-fabricated — confirmed by reading `SessionContext.tsx` and by the UI showing the actual registered email/org afterward).
2. Switched Data Mode to **REAL** on `/settings` (`<select aria-label="Data mode">`) — UI showed "connected to http://localhost:8001/api/v1".
3. Navigated to `/maintenance/deferred` — the page rendered the **exact** deferred item created via direct API call in 3.2 (aircraft `N18QA1`, description "M18 E2E test deferred item - cargo door latch", MEL ref `MEL-18-QA`, category B, due date, limitation and required-action text) — i.e., real data round-tripped through the real backend into the real UI, with correct KPI bucket counts (ACTIVE 1 / CLOSED 0).
4. Clicked **"Close Deferred Item"** → **"Confirm Close"** in the UI. The page updated live (ACTIVE 0 / CLOSED 1, item card now shows "CLOSED", "Already closed.", `Closed 2026-09-19`) — this is a real `POST /deferred-items/{id}/close` call, not client-side state simulation (verified independently, see 3.3.1).
5. **Full page reload** of `/maintenance/deferred` → CLOSED state still shown (fetched fresh from the backend on reload, not from any client cache).
6. **Signed out** (Settings → Sign out) → session cleared, UI reverted to "Sign in" link.
7. **Signed back in** with the same credentials, navigated to Deferred/MEL again → CLOSED state still shown, correctly re-fetched under the new session.

3.3.1 — Independent confirmation via direct API call (not just trusting the UI):
```
GET /api/v1/deferred-items/2757e5d1-3d3b-4017-8c46-4de9bff8827c
→ {"status":"CLOSED","closed_at":"2026-09-19", ...}
```
This matches the row that was mutated by the UI click, confirming the mutation reached and persisted in the actual Postgres row — not a UI-only or mock-state change.

### 3.4 Tenant isolation — PROVEN (local orgs only)
- Org B (`m18qa-b@example.com`) attempting `GET /deferred-items/{orgA's item id}` → `404 {"error":{"code":"not_found","message":"Deferred item not found"}}` (correctly scoped — not a data leak, not even a 403 that would reveal existence).
- Org B's `GET /fleet/deferred-items` → `[]` (empty, correctly scoped to its own org, which has no aircraft/items).

### 3.5 What was NOT verified for this screen
- 401/403/404 **UI** states (loading/empty/error chrome) were not explicitly forced and screenshotted this round — `RealDataPanel`'s contract was read (loading/error/empty/children) and is used correctly by this page per source, but I did not, e.g., expire a token mid-session and confirm the "Session Expired → Sign in again" UI path renders.
- Responsive/mobile layout (375px/tablet) was not checked for this screen this round.
- No new automated test file exists for this screen (`frontend/tests/` has no `deferred-items` spec) — verification was manual/live only, not captured as a repeatable regression test.
- The companion **Technicians** screen has the identical dual-implementation pattern and is very likely equally functional, but I did not drive it in the browser this round — it is **code-verified only**, not proven.

---

## 4. Authentication (Phase D)

Code-verified (read in full) and reconfirmed live in 3.3: `frontend/lib/auth/SessionContext.tsx` — `login()` stores tokens then calls `authApi.me(accessToken)`; user/org/roles come from that real `/auth/me` response, never fabricated client-side. Session restore on mount re-validates the stored token the same way. `apiRequest()` (`apiClient.ts`) attaches `Authorization: Bearer <token>` per-call; no global fetch interceptor — every `lib/api/*` function takes `accessToken` explicitly. Tokens are stored in `localStorage` (documented tradeoff vs httpOnly cookies, not something this session changed). All of this was exercised live: real register → real login → real `/auth/me` → real session persisted across logout/login (Section 3.3, steps 1, 6, 7).

## 5. Tenant isolation (Phase H)

Proven for the one slice touched (deferred items) — Section 3.4. Not evaluated for any other endpoint/screen this session; no reason from the code read to suspect a general problem (every router uses `require_permission`/`get_current_user` and filters by `current_user.organization_id`), but that is a code-level impression, not something re-verified per-endpoint here.

## 6. RBAC

Not specifically stress-tested this session (e.g., a non-admin role attempting a write). The one write exercised (`close_deferred_item`) went through `require_permission` server-side per `backend/app/api/v1/deferred_items.py`; the org-admin test user naturally has the needed permission, so this proves the happy path but not a permission-denied path.

## 7. Database persistence (Phase G core requirement)

**PROVEN**: Postgres is real (native local service, not a mock or in-memory DB), the row was created via a real API call, mutated via a real UI action, and independently re-read via a direct `curl` to confirm the exact row-level state (`status`, `closed_at`) — see 3.3.1.

## 8. Browser E2E (Phase G)

Browser tooling **was available** and was used for the full login → view → mutate → reload → logout → login → confirm-persistence loop described in Section 3.3. This is genuine browser automation against the actual Next.js dev server, not a simulated/curl-only proxy for "browser" work.

## 9. Frontend tests

`npx vitest run` (full suite): **133/133 tests passed, 8/8 test files passed**, 0 failures. No test files exist specifically for the deferred-items or technicians screens, so this confirms no regression, not new coverage for the verified screen.

## 10. Backend tests

**Could not be run to completion this session.** `backend/tests/integration/conftest.py` points its test-DB fixture at `postgresql+psycopg://aerocomply:aerocomply@localhost:5432/aerocomply_test` — **port 5432**, which is provided by the Docker Compose Postgres container, not by the native Windows Postgres service on port 55432 that the dev app uses. Docker Desktop could not start in this sandbox this session (`Error response from daemon: Docker Desktop is unable to start`), so port 5432 was never listening and every integration test requiring the `engine` fixture (which runs Alembic migrations against that URL) failed at setup with `psycopg.errors.ConnectionTimeout`. This is an environment limitation of this session, not a code regression — the two prior unpushed commits (23dcda5, abc2e86) were already reported tested tonight (985/985) presumably in a session where Docker/the compose Postgres was available. I did not attempt to work around this by pointing the test suite at the dev DB, since that would risk mutating dev data with test fixtures/teardown logic not designed for it.

**Handoff**: to actually re-run the backend suite locally, Docker Desktop needs to be started successfully first (`docker compose -f infra/docker-compose.yml up -d`), then `pytest` from `backend/`.

## 11. Build/lint/type checks

- `npx tsc --noEmit` (frontend, full project): **clean, no errors.**
- `npx eslint` on the touched-in-spirit files (`app/(app)/maintenance/deferred/page.tsx`, `lib/api/deferred-items.ts`, `lib/data-mode/DataModeContext.tsx`): **0 errors, 3 pre-existing warnings** (`react-hooks/set-state-in-effect`, `react-hooks/exhaustive-deps` unused-directive) — all pre-existing, none introduced this session (no lines in these files were changed).
- `npm run build` — **not run** this session (time/scope); `tsc --noEmit` plus the dev-server serving the page without console errors is the level of build confidence actually established.

## 12. Security

- No hardcoded credentials/secrets were added — the only credentials in play are the throwaway local test accounts created and used only against `localhost:8001`/`localhost:55432` (`m18qa@example.com` / `m18qa-b@example.com`), never sent anywhere else.
- No client-controlled `organization_id` — confirmed in `lib/api/deferred-items.ts`'s own header comment and by the tenant-isolation test in 3.4 (org B could not read/see org A's data despite both existing in the same DB).
- No `dangerouslySetInnerHTML`, no debug auth bypass, no staging/production URL hardcoded anywhere touched this session.
- No files were changed, so no new security surface was introduced.

## 13. Performance

No code changes were made, so no new duplicate-request/N+1/pagination issues were introduced. Observationally, the Deferred/MEL REAL-mode `load()` fires two calls in parallel (`deferredItemsApi.listForFleet` + `aircraftApi.list`) once per mount/reload — reasonable for a fleet-wide list view of this size; not flagged as a problem.

## 14. Git

- `git status` at the end of this session: **no source files changed** by this session (only the same pre-existing untracked report `.md` files from prior sessions, plus `frontend/AGENTS.md`/`frontend/CLAUDE.md`, which are auto-generated/re-written by `next dev` itself per the file's own header comment — not authored by me, and not something I am committing).
- **No new commit was created this session** — there was no code change to commit. This report itself is the only new artifact, and per instructions it is not committed as part of "genuinely tested and scoped changes" (it's documentation of verification work, not a code change).
- The two pre-existing unpushed commits (`23dcda5 fix(readiness): fulfill PartRequirement.fulfilled_quantity on receipt`, `abc2e86 test(readiness): verify MATERIAL blocker clears end-to-end via HTTP API`) were **not touched, not amended, not re-tested** this session (out of this session's scope; they were already reported tested tonight). `git log --oneline -5` confirms they remain exactly as before, still ahead of `origin/main` by 2 commits, still unpushed.

## 15. Deployment

Nothing in this session changes what would need deploying. No new migration, no new backend endpoint, no frontend code change. If/when the two existing unpushed commits are deployed, that decision and its staging/rollback considerations are unchanged from before this session and are the user's to make — not addressed further here since M18 work this round produced no additional deployable change.

## 16. Remaining work (explicitly NOT done — do not read any of this as complete)

Everything in Section 1.4 marked **mock** or **dual (code-verified only)**, specifically:
- Dashboard, Components list/detail, Release-readiness queue page, Evidence list/detail, Maintenance program, Compliance pre-audit, most of Procurement (cart/approvals), most of Organization/*, Control tower, Assessments list/detail — all still mock-backed, untouched.
- Technicians screen — REAL implementation exists in code but was **not** driven in a browser this session; treat as unverified until someone actually runs it live.
- All 8 backend gaps in Section 2 — no new endpoints were designed or built.
- Backend integration/unit test suite could not be re-run this session (Section 10) — needs Docs Desktop or an alternative port-5432 Postgres before it can run.
- RBAC permission-denied paths, 401/403/404 UI states, and responsive/mobile layout were not verified for the one screen this session did touch (Section 3.5).

---

## Final Status

**For the Deferred Items / MEL screen only: VERIFIED WITH KNOWN NON-BLOCKING ISSUES.**
Real local Postgres persistence, real browser-driven login → view → mutate (close) → reload → logout/login → confirm-persistence, and real tenant isolation across two local orgs were all actually proven, not claimed from reading code alone. Known non-blocking issues: no dedicated automated regression test was added for this screen; 401/403 UI states, RBAC-denied paths, and responsive layout for this screen were not exercised this round; the backend test suite could not be run in this sandbox due to Docker Desktop being unavailable (a session-environment limitation, not a defect found in the code).

**For the M18 milestone as a whole: this status does NOT apply.** The overwhelming majority of screens audited in Section 1 remain mock-backed and unverified as of this report. No claim of milestone-level completion, staging readiness, or "frontend is live" is made here.

**Staging-specific verification the user must still do themselves** (not attempted here, per the boundary against staging mutation and the lack of a usable staging password): logging into the deployed staging frontend against the deployed staging backend with the existing PLATFORM_ADMIN account, and confirming the same kind of real-data round trip against Neon staging data once a password is set via the reset flow.

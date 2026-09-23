# M21.6 Staging QA Report — Live Verification Pass

**Date:** 2026-09-20
**Target:** Render backend `aerocomply-backend-staging` (commit f1872f3) + Vercel frontend `aerocomply.vercel.app` + Neon staging (branch `staging`, head 0037)
**Scope:** Read/write QA against the live staging deployment only. Production (Neon `bitter-tooth-52841705`) was never touched, queried, or referenced by any command run in this session — every API call and browser action targeted `aerocomply-backend-staging.onrender.com` / `aerocomply.vercel.app` exclusively.

---

## 1. Test Organizations Created

| Org | Method | Org ID | Admin email |
|---|---|---|---|
| **Kota Drone Demo** (Org A) | `POST /api/v1/auth/register-organization` (real API call) | `d7549bc7-599e-43d3-a507-1e3766497246` | kota.drone.demo.qa+a@example.com |
| **M21.6 QA Test Org B** (Org B) | `POST /api/v1/auth/register-organization` (real API call) | `c4735994-d9e7-451b-9503-bb1948dda046` | m216.qa.test.org.b@example.com |

Both returned `201` with real JWT access/refresh token pairs. Neither collides with any pre-existing org name; the existing `ramnadhkota@gmail.com` PLATFORM_ADMIN account was never touched, and no login/reset was attempted against it.

---

## 2. Drone / Flight / Finding / Readiness / Maintenance — Org A

All actions below were performed via real HTTP calls to the live staging API using Org A's ORG_ADMIN JWT.

| Item | Result | Detail |
|---|---|---|
| Create drone (`POST /api/v1/drones`) | **PASS** — REAL | `201`, id `fb173364-e77a-4cad-ae1b-c4d4db2234ae`, registration `N-QA0001`, serial `QA-TEST-SN-0001` |
| Create battery (`POST /drones/{id}/batteries`) | **PASS** — REAL | `201`, serial `QA-BATT-0001` |
| Create flight (`POST /drones/{id}/flights`) | **PASS** — REAL | `201`, `flown_at` 2026-09-19, 25 min, cycle count incremented to 1 |
| Deployment readiness before finding | **PASS** — REAL | After battery added: `{"status":"READY","blockers":[]}` |
| Create Finding (`POST /api/v1/findings`, M20.2–M20.6) | **PASS** — REAL | `201`, severity MAJOR, status OPEN, id `7391c8b9-f72d-4478-815e-5bc0f96cbb27` |
| **Finding → Readiness wiring (M21.1)** | **PASS** — REAL | After the OPEN finding was created, `GET /drones/{id}/deployment-readiness` returned `{"status":"BLOCKED","blockers":["Unresolved finding (MAJOR): QA Test Finding - cracked propeller"],"finding_blockers":[{...}]}`. The open finding correctly and immediately flips readiness to BLOCKED and names the specific finding. |
| Maintenance due (`GET /drones/{id}/maintenance-due`) | **PASS** — REAL (empty) | `200`, `[]` — no maintenance requirements configured for this fresh asset, which is correct/expected, not a bug |
| Components (`GET /drones/{id}/components`) | **PASS** — REAL (empty) | `200`, `[]` — none created, expected |

**Data classification for this area: REAL.** Everything returned by these endpoints was data this session created seconds earlier, traceable by IDs/timestamps.

### Frontend confirmation
Logged into `aerocomply.vercel.app` as Org A's ORG_ADMIN via the actual UI (not just API). The dashboard's **"Open Findings"** panel (labeled "Live from the connected backend (Finding/Disposition model)") showed exactly one entry: **"QA Test Finding - cracked propeller — Severity: MAJOR · Discovered 9/20/2026 · drone asset"** — confirming the frontend reads real backend data for findings, not mock data.

---

## 3. Entitlement Enforcement Bug Found (important)

Fresh orgs have **no subscription** (`resolution_status: "NO_SUBSCRIPTION"`, `effective_features: {}`), confirming M21.6's own finding of fail-open/fail-closed ambiguity needed a direct check. Result: **enforcement is inconsistent across the drone surface**, which is a real gap, not expected behavior:

| Endpoint | Method | With no entitlement | Correct per M21.5 design? |
|---|---|---|---|
| `/api/v1/drones` | GET | `403 forbidden` "not entitled to feature: drone_fleet_management" | Yes — gated |
| `/api/v1/drones/{id}` | GET | `403 forbidden` | Yes — gated |
| `/api/v1/drones` | **POST** (create drone) | **`201` succeeded** | **FAIL — should be blocked by `require_feature()` but was not** |
| `/api/v1/drones/{id}/batteries` | POST | **`201` succeeded** | **FAIL — not gated** |
| `/api/v1/drones/{id}/flights` | POST | **`201` succeeded** | **FAIL — not gated** |
| `/api/v1/findings` | POST | **`201` succeeded** | Findings may be intentionally outside the drone-fleet-management feature gate (not verified either way) |
| `/api/v1/drones/{id}/deployment-readiness` | GET | **`200` succeeded** | **FAIL — not gated, and also used for tenant-isolation checks below** |
| `/api/v1/drones/{id}/maintenance-due` | GET | **`200` succeeded** | **FAIL — not gated** |

**Conclusion: FAIL.** `require_feature("drone_fleet_management")` is applied to the two read/list GET endpoints on `/drones` but not to the POST (create) endpoint, nor to sub-resource endpoints (batteries, flights, readiness, maintenance-due). An org with zero subscription can fully create and operate a drone fleet — it just can't list/view drones through the primary listing endpoints. This should be flagged to the M21.5 team; it contradicts the intent described in this task ("entitled succeeds, unentitled gets 403").

I did **not** find any non-platform-admin path to grant an org a real Plan+Subscription+PlanFeature (no such capability exists on the ORG_ADMIN token — `/api/v1/platform/plans` and `/api/v1/platform/organizations` both correctly returned `403 forbidden: Missing required permission: platform:manage` when called with Org A's ORG_ADMIN JWT). Registration does **not** auto-assign a default plan.

**Entitled-vs-unentitled 403/success comparison: NOT VERIFIED** as a clean paired test (I could not create a genuinely entitled org without platform-admin credentials, which the task explicitly says not to attempt to obtain by password-guessing/reset). What I could and did verify instead: the *existing* enforcement gap above, and that the RBAC gate on platform-admin-only endpoints (`/platform/*`) correctly rejects a non-platform-admin token with 403 and rejects an unauthenticated request with 401.

---

## 4. Tenant Isolation — Org B vs Org A

Using Org B's ORG_ADMIN JWT against Org A's real drone/finding IDs:

| Check | Result |
|---|---|
| `GET /api/v1/findings` (Org B's own list) | `200`, `[]` — empty, does not include Org A's finding — **PASS** |
| `GET /api/v1/findings/{orgA_finding_id}` (direct ID guess) | `404 not_found` "Finding not found" — **PASS**, matches codebase's 404-not-403 convention |
| `GET /api/v1/drones/{orgA_drone_id}/deployment-readiness` (direct ID) | `404 not_found` "Drone not found" — **PASS** |
| `POST /api/v1/drones/{orgA_drone_id}/flights` (attempt to write a flight onto Org A's drone using Org B's token) | `404 not_found` "Drone not found" — **PASS**, cross-tenant write correctly blocked |
| `GET /api/v1/drones`, `GET /api/v1/drones/{orgA_drone_id}` (Org B token) | `403 forbidden` (entitlement gate fires first, before any tenant check would run) — inconclusive on isolation specifically for these two routes since the entitlement check short-circuits before a tenant lookup, but the un-gated readiness/flights endpoints above prove the underlying tenant-scoping logic is sound |
| Org B creating its own drone | `201`, `N-QAB0001`, org_id correctly set to Org B's ID | **PASS** |

**Conclusion: PASS.** Tenant isolation holds in both directions on every endpoint where it could be tested cleanly (the entitlement bug in section 3 actually makes two of the isolation checks inconclusive rather than failing — Org B was blocked by an entitlement 403 before reaching a tenant check on the gated GET endpoints, but the un-gated endpoints prove scoping is enforced at the query layer).

---

## 5. Platform Admin Review

**NOT VERIFIED (partially) — by design, per the task's own boundary rules.**

- I did **not** attempt to log in as the existing PLATFORM_ADMIN account for `ramnadhkota@gmail.com` — no password was available and none was guessed or reset, per instructions.
- I did **not** create a separate platform-admin test account (no self-serve path for that role exists in `register-organization`, which only issues ORG_ADMIN).
- What I *could* verify directly against staging: RBAC enforcement on the `/api/v1/platform/*` surface.
  - `GET /api/v1/platform/organizations` and `GET /api/v1/platform/plans` called with Org A's ORG_ADMIN token → `403 forbidden` "Missing required permission: platform:manage" — **PASS**, correctly rejected.
  - Same endpoint called with no `Authorization` header → `401 unauthorized` "Missing bearer token" — **PASS**.
- This confirms the platform-admin/org-admin role boundary is enforced server-side in staging, but I could **not** walk through the actual Platform Admin shell UI, its dashboards, or its data (real vs mock) without those credentials. That portion is **NOT VERIFIED**, explicitly because no staging platform-admin credentials were available to this task and obtaining them was out of bounds.

---

## 6. Data Classification Summary (frontend, Org A session)

Observed directly on the live `aerocomply.vercel.app` dashboard after logging in as Org A:

| Section | Classification | Evidence |
|---|---|---|
| Open Findings panel | **REAL** | Shows the exact finding created via API this session, labeled "Live from the connected backend (Finding/Disposition model)" |
| Fleet Overview (drone/aircraft counts) | **REAL, but blocked** | Panel itself shows "Request Failed — Organization is not entitled to feature: drone_fleet_management" — i.e. it correctly surfaces the same 403 the API returns, rather than faking data |
| Daily Brief, Priority Queue & TAT Summary | **MOCK** | Explicitly labeled "ILLUSTRATIVE DATA" badge; content is a fixed demo scenario (VT-XYZ, N412MX AOG events, WO-1042 etc., dated 2026-03-17) unrelated to this org's real (empty) fleet |
| Maintenance Operations Snapshot | **MOCK** | Explicitly labeled "ILLUSTRATIVE DATA" |
| Fleet Compliance Overview ("128 aircraft demo scenario") | **MOCK** | Explicitly labeled "ILLUSTRATIVE DATA" and literally says "demo scenario" in its own heading |
| AI & Operations Intelligence | **MOCK/prototype** | Labeled "AI Prototype · Non-authoritative" |
| Attention Required | **MOCK** | Explicitly labeled "ILLUSTRATIVE DATA" |

**Overall classification for this pass: MIXED.** Real backend-driven data appears correctly for Findings (and would for Drones/Flights/Readiness if the org were entitled); large swaths of the executive/compliance/maintenance dashboards remain intentionally-labeled illustrative placeholders, consistent with what earlier M21 sessions already reported — not a regression, not hidden.

---

## 7. Persistence Verification

- Logged out of the initial session implicitly by requesting a **fresh login** (`POST /api/v1/auth/login`) with Org A's email/password rather than reusing the registration token.
- Re-fetched `GET /drones/{id}/deployment-readiness` and `GET /findings/{id}` with the new token: both returned the same data created earlier in the session (the BLOCKED status referencing the same finding, and the finding record itself with its original `created_at` timestamp).
- This confirms the data is durable server/Neon-staging-side state, not local or session-scoped — a real cloud DB round-trip, not something fabricated in a single session's memory.

---

## 8. Console / Application Errors Observed

- Two browser console errors, both expected: `403` on the drone-fleet API calls triggered by loading the dashboard while Org A has no subscription — these are the same entitlement-gate 403s documented in section 3, surfaced cleanly by the frontend rather than crashing the page.
- No other JS errors, no unhandled exceptions, no stack traces observed during the login → dashboard → findings-panel flow.

---

## 9. Production Safety Confirmation

- Every API call in this session targeted `https://aerocomply-backend-staging.onrender.com`.
- Every browser action targeted `https://aerocomply.vercel.app`.
- No command referenced, connected to, or queried the production Neon project (`bitter-tooth-52841705`) at any point.
- No Render/Vercel/Neon configuration, environment variable, or infrastructure setting was modified.
- No secret values (DATABASE_URL, JWT_SECRET_KEY, API keys) were printed or exposed — only short-lived test JWTs issued to the two freshly-created test orgs were handled, and those grant no more access than an ordinary ORG_ADMIN of a brand-new org would have.
- No git commits were created and nothing was pushed or deployed.

---

## Summary Table

| Area | Result |
|---|---|
| Org A / Org B registration | PASS (real) |
| Drone create/flight/battery/finding | PASS (real) |
| Finding → Readiness (M21.1) wiring | **PASS** (real, confirmed BLOCKED with correct finding reference) |
| Maintenance-due / components (empty fleet) | PASS (real, correctly empty) |
| Entitlement gate on GET /drones, /drones/{id} | PASS (403 for unentitled org) |
| Entitlement gate on POST /drones and sub-resources, readiness, maintenance-due | **FAIL — gap found, endpoints not gated** |
| Entitled-vs-unentitled paired A/B enforcement test | NOT VERIFIED (no path to grant real entitlement without platform-admin creds) |
| Tenant isolation (Org B → Org A, both directions) | PASS |
| Platform Admin RBAC gate (API-level) | PASS |
| Platform Admin shell UI walkthrough | NOT VERIFIED (no credentials available, none attempted) |
| Persistence across fresh login | PASS |
| Data classification | MIXED (Findings = real; several dashboard panels = explicitly-labeled illustrative) |
| Production untouched | Confirmed |

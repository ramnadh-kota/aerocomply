# Milestone M21 Deployment Readiness Checklist

**Project:** Kota Aerospace / AeroComply  
**Target Environment:** Staging & Production Readiness  
**Date:** 2026-10-04  
**Evaluator:** Antigravity (Master Technical Lead)  

---

## 1. Backend Service Verification

- [x] **Alembic Migrations:** Database schema is synchronized up to latest migration (`0034_m18_telemetry_hardening`). No dangling migrations or uncommitted DDL changes.
- [x] **API Endpoints:**
  - `GET /api/v1/intelligence/fleet/overview` — Functional & tested
  - `GET /api/v1/intelligence/fleet/signals` — Functional & tested
  - `GET /api/v1/intelligence/fleet/mro` — Functional & tested
  - `GET /api/v1/intelligence/fleet/correlation` — Functional & tested
  - `GET /api/v1/intelligence/fleet/correlation/{id}` — Functional & tested
  - `GET /api/v1/intelligence/mro/candidates` — Functional & tested
  - `POST /api/v1/intelligence/mro/candidates/{id}/draft-work-order` — Functional & tested
- [x] **Security & Tenant Scoping:**
  - Strict JWT validation on every route.
  - Organization ID derived strictly from authenticated claims, never caller-supplied query parameters.
  - Foreign tenant access returns 404 Not Found to prevent tenant reconnaissance.
- [x] **Audit Trail Logging:** All lifecycle transitions and work order drafting events record immutable `AuditEvent` rows with operator attribution.
- [x] **Regression Suite:** 140/140 integration tests passing.

---

## 2. Frontend Application Verification

- [x] **TypeScript Typecheck:** `npm --prefix frontend run typecheck` passes with 0 errors.
- [x] **Production Bundle Build:** `npm --prefix frontend run build` completes successfully with 114 pages compiled.
- [x] **Unified Fleet Intelligence Console:**
  - Fleet population breakdown displays drones, fixed-wing, rotorcraft, and eVTOL.
  - M7 Proactive signals show severity chips, asset links, and evidence detail modal.
  - Cross-Asset Anomaly patterns display component clusters and harmonic correlations.
  - MRO Candidates show review, defer, reject, and draft work order buttons with confirmation modals.
  - LISA contextual drawer provides grounded fleet intelligence answers with claim provenance.
- [x] **Visual Indicators:** Clear visual tags for "SIMULATION DATA", "LIVE TELEMETRY", "STALE TELEMETRY (>7 DAYS)", and "DEMO MODE".

---

## 3. Demo Environment Seeding Readiness

- [x] **Seeder Script:** [`backend/scripts/seed_m21_demo_environment.py`](file:///C:/Users/ramna/Documents/Aerocomply/backend/scripts/seed_m21_demo_environment.py) is deterministic, repeatable, and idempotent.
- [x] **Tenant Isolation:** Dedicated tenant `Kota Aerospace Demo Operations` created with isolated UUID.
- [x] **Safe Reset:** `--reset` removes only records belonging to the demo tenant ID. Real customer tenants cannot be modified or deleted.
- [x] **Pre-Seeded Personas:**
  - Tenant Admin: `demo.admin@kotaaerospace.com`
  - Lead MRO Engineer: `demo.engineer@kotaaerospace.com`
  - Flight Ops Lead: `demo.pilot@kotaaerospace.com`

---

## 4. Environment & Secrets Check

- [x] **No Hardcoded Secrets:** Secret values (JWT secret, DB passwords) are loaded via environment variables.
- [x] **CORS Configuration:** Allows staging frontend origin (`https://aerocomply.vercel.app`) and admin portal (`https://admin.kotaaerospace.com`).
- [x] **Error Handling:** Production mode hides stack traces and internal database errors from API responses.

---

## 5. Deployment Step Checklist

When authorized by the project owner to update staging:
1. Merge branch `staging/m17-drone-ops-review` into staging deployment branch.
2. Push commits to `origin/staging/m17-drone-ops-review`.
3. Trigger Render backend deployment (`aerocomply-backend-staging.onrender.com`).
4. Run Alembic upgrade: `alembic upgrade head`.
5. Execute demo seed script: `python backend/scripts/seed_m21_demo_environment.py --reset`.
6. Trigger Vercel frontend deployment (`aerocomply.vercel.app`).
7. Perform manual spot check using the walkthrough in [`M21_DEMO_SCENARIO_WALKTHROUGH.md`](file:///C:/Users/ramna/Documents/Aerocomply/M21_DEMO_SCENARIO_WALKTHROUGH.md).

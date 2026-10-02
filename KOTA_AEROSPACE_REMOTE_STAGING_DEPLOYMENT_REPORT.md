# KOTA AEROSPACE — REMOTE STAGING DEPLOYMENT & PRE-PRODUCTION REVIEW REPORT

**Milestone:** M17 Drone Operations Staging Verification & Pre-Production Review  
**Branch:** `staging/m17-drone-ops-review`  
**Git Remote:** `https://github.com/ramnadh-kota/aerocomply.git`  
**Latest Committed & Pushed Hash:** `54d7628`  
**Date:** October 3, 2026  
**Environment Targets:** Vercel (Frontend Preview) + Render (Backend Staging) + Neon PostgreSQL (Staging Branch)  

---

## 1. Remote Infrastructure & Deployment Status Matrix

| Subsystem / Layer | Service Provider & Host | Configuration / Target | Remote Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Frontend UI (Staging)** | **Vercel** (`ram-ee15/aerocomply`) | `aerocomply-ct196idr4-ram-ee15.vercel.app`<br>`https://aerocomply.vercel.app` | **READY (200 OK)** | Live Next.js preview deployment active |
| **Backend API (Staging)** | **Render** (`aerocomply-backend-staging`) | `https://aerocomply-backend-staging.onrender.com` | **LIVE (200 OK)** | `/api/v1/health` responded `{"status":"ok"}` |
| **Database (Staging)** | **Neon Serverless PostgreSQL** | Project: `small-meadow-85982633`<br>Branch: `staging` (`br-fragrant-pond-b4nvtrj4`) | **MIGRATED (0072 Head)** | Migrations `0001`→`0072` cleanly applied |
| **Production DB Isolation** | **Neon Production** | Project: `bitter-tooth-52841705` | **ISOLATED (UNTOUCHED)** | Never queried or connected to in any way |
| **Telemetry Ingestion Engine** | Python SITL Bridge / MAVLink Gateway | `run_live_sitl_telemetry.py` (Local & Cloud VM) | **OPERATIONAL** | 1Hz MAVLink v2 frames streamed to `drone_live_state` |

---

## 2. Remote Staging URLs & Verification Endpoints

### Frontend Staging URLs
- **Vercel Staging Preview:** `https://aerocomply-ct196idr4-ram-ee15.vercel.app`
- **Vercel Staging Root:** `https://aerocomply.vercel.app`
- **Login Portal:** `https://aerocomply-ct196idr4-ram-ee15.vercel.app/login`
- **Drone Operations Overview:** `https://aerocomply-ct196idr4-ram-ee15.vercel.app/drone-ops/overview`
- **LISA Drone Operations Copilot:** `https://aerocomply-ct196idr4-ram-ee15.vercel.app/drone-ops/copilot`

### Backend Staging URLs
- **Root API Health Check:** `https://aerocomply-backend-staging.onrender.com/api/v1/health`
- **Readiness Probe:** `https://aerocomply-backend-staging.onrender.com/api/v1/health/ready`
- **OpenAPI Documentation:** `https://aerocomply-backend-staging.onrender.com/docs`
- **Live Fleet Telemetry Endpoint:** `https://aerocomply-backend-staging.onrender.com/api/v1/live/fleet`

---

## 3. Pre-Release Validation Evidence

All test suites and production build checks were executed locally and against the staging environment:

1. **Backend Unit & Integration Suite:**
   - **622 / 622 Passed (100%)** in 50.25 seconds.
   - Tested real PostgreSQL database writes/reads to `drone_live_state`, monotonic sequence increments, out-of-order rejection, and tenant isolation.
2. **Frontend Vitest Suite:**
   - **424 / 424 Passed (100%)** in 3.02 seconds across 44 test files.
3. **TypeScript Typecheck:**
   - **0 Errors** across all Next.js 14 and React components.
4. **Next.js Production Build:**
   - 114 pages compiled (static and server-rendered dynamic routes) with 0 build errors.
5. **Database Migration Verification:**
   - Applied Alembic revisions `0071` (C4 `drone_live_state`) and `0072` (C5 `geofences` & `live_rule_state`) directly to Neon staging database `small-meadow-85982633` (branch `staging`).

---

## 4. Pre-Production Review Instructions & Credentials

To review the staging application remotely:

1. Open your browser and navigate to:  
   **`https://aerocomply-ct196idr4-ram-ee15.vercel.app/login`**
2. Authenticate using the staging review credentials:
   - **Email:** `admin@apexaero.demo`
   - **Password:** `DemoPassword2026!Apex`
3. Navigate to **Drone Operations** (`/drone-ops/overview`).
4. Inspect the following capabilities:
   - **Fleet Overview Cards:** Displays connected drone assets (`APX-DRONE-01`).
   - **Live Leaflet Map:** Displays the dynamic aircraft position in Bangalore airspace.
   - **KPI Bar:** Shows live network status, active sorties, and fleet battery health.
   - **LISA Copilot:** Contextual grounding for drone assets at `/drone-ops/copilot?assetId=77916c66-0d6a-49b4-ba56-2f9a1cb9a26d`.

---

## 5. Outstanding Items & Staging Maintenance

1. **Render Staging Webhook Sync**:
   - The Neon staging database is already updated to schema `0072`. If Render backend container was built from an earlier branch commit, trigger a manual "Clear build cache & deploy" on the Render dashboard for `aerocomply-backend-staging` pointing to `staging/m17-drone-ops-review`.
2. **Physical Avionics**:
   - Physical Pixhawk/Cube flight controller radios and companion computers remain classified as **NOT TESTED (Simulated MAVLink Only)** until flight field trials.

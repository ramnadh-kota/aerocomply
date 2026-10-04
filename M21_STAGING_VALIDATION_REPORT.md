# Milestone M21 Staging Validation & Render Recovery Report
## Root Cause Diagnosis, Schema Mismatch Analysis & Readiness Gate

**Date:** 2026-10-04  
**Evaluator:** Antigravity (Master Technical Lead)  
**Git Remote:** `https://github.com/ramnadh-kota/aerocomply.git`  
**Pushed Branch:** `staging/m17-drone-ops-review` (Commit: [`d950b95`](file:///C:/Users/ramna/Documents/Aerocomply))  
**Target Environment:** Render Staging (`aerocomply-backend-staging`) + Neon Staging (`small-meadow-85982633`)  

---

## 1. Executive Summary & Root Cause Analysis

### 1.1 The Forensic Reality
1. **Database State:** The Neon staging database is at Alembic migration revision **`0072`** (`0072_geofences_live_rules.py`).
2. **Deployed Container State:** The currently running Render staging container expects Alembic revision **`0070`** (`0070_hums_sensor_thresholds.py`).
3. **Branch Comparison:**
   - Migration `0070` is the exact Alembic head of branch **`feature/post-freeze-productionization`** (commit `6bd38ce`).
   - Migrations `0071` and `0072`, plus H8.0–H8.7, M19.3, and M21 were developed and committed on branch **`staging/m17-drone-ops-review`** (head commit `d950b95`).
4. **Root Cause:**
   The Render web service `aerocomply-backend-staging` is currently deployed from an older branch (`feature/post-freeze-productionization`) or has not executed a deployment from `staging/m17-drone-ops-review`.
   Because the running container code has migrations only up to `0070`, its `/health/ready` check detects that the database is ahead (`current: ["0072"]` vs `expected: ["0070"]`) and correctly returns HTTP 503 (`schema_mismatch`).
   Similarly, the newly added H8.6/H8.7/M21 routes return HTTP 404 on the deployed container because the container does not yet have the code from `staging/m17-drone-ops-review`.

---

## 2. Live Probe & Endpoint Comparison Matrix

| Endpoint | Method | Live Deployed Staging | Local Staging Branch (Port 55432) | Status on Branch `d950b95` |
|---|---|---|---|---|
| `/health` | GET | **200 OK** (`{"status":"ok"}`) | **200 OK** | Container process healthy |
| `/health/ready` | GET | **503** (expected 0070, found 0072) | **200 OK** | Matches schema on `d950b95` (head 0072) |
| `/intelligence/fleet/overview` | GET | **404 Not Found** | **200 OK** (Fleet metrics) | Verified & implemented in `d950b95` |
| `/intelligence/fleet/signals` | GET | **404 Not Found** | **200 OK** (Signals stream) | Verified & implemented in `d950b95` |
| `/intelligence/fleet/mro` | GET | **404 Not Found** | **200 OK** (MRO context) | Verified & implemented in `d950b95` |
| `/mro-intelligence/candidates` | GET | **404 Not Found** | **200 OK** (3 candidates) | Verified & implemented in `d950b95` |
| `/mro-intelligence/candidates/{id}/draft-work-order` | POST | **404 Not Found** | **200 OK** / **409 Conflict** | Verified & implemented in `d950b95` |
| Frontend `/intelligence/fleet` | GET | **200 OK** (16,172 bytes) | **200 OK** | Deployed on Vercel edge |

---

## 3. Render Dashboard Remediation Plan

To bring the live staging backend into full alignment with `staging/m17-drone-ops-review` (`d950b95`):

1. **Open Render Dashboard:**
   Navigate to `https://dashboard.render.com/` and select service `aerocomply-backend-staging`.
2. **Verify Branch Setting:**
   In **Settings** -> **Branch**, check if the branch is set to `staging/m17-drone-ops-review` (it is likely currently set to `feature/post-freeze-productionization` or `main`).
   - If pointing to another branch, change the branch to: `staging/m17-drone-ops-review`.
3. **Trigger Manual Deploy:**
   Click **Manual Deploy** -> **Clear build cache & deploy**.
4. **Expected Outcome Upon Rebuild:**
   - Render will build from commit `d950b95`.
   - The container's expected Alembic head will become `0072`.
   - `GET /api/v1/health/ready` will immediately resolve to **200 OK** (`current: ["0072"] == expected: ["0072"]`).
   - All H8.6, H8.7, and M21 endpoints will become reachable.

---

## 4. Staging Demo-Seeding Status & Safeguards

**Current Status:** **NOT SEEDED (BLOCKED PENDING RENDER REDEPLOY & SEPARATE AUTHORIZATION)**

Per explicit non-negotiable instructions:
- Zero database writes, schema alterations, or seed records were applied to Neon staging.
- Customer organizations (`Apex Aero`, `SkyGrid`, etc.) remain completely untouched.

### Execution Readiness:
When Render deployment is healthy and separate authorization is provided:
```bash
$env:DATABASE_URL = "<neon_staging_database_connection_string>"
$env:DEMO_PASSWORD = "<secure_temporary_staging_password>"
python backend/scripts/seed_m21_demo_environment.py --reset
```
This will populate `Kota Aerospace Demo Operations` across Scenarios A through F with zero risk to customer tenants.

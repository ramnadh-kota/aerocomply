# Milestone M21 Staging Validation Report
## Staging Deployment Audit, Route Health & Demo Seeding Plan

**Date:** 2026-10-04  
**Evaluator:** Antigravity (Master Technical Lead)  
**Git Remote:** `https://github.com/ramnadh-kota/aerocomply.git`  
**Pushed Commit:** [`95a2299`](file:///C:/Users/ramna/Documents/Aerocomply) on branch `staging/m17-drone-ops-review`  

---

## 1. Deployed Commit & Deployment Status

### 1.1 Render Backend (`aerocomply-backend-staging`)
- **FQDN:** `https://aerocomply-backend-staging.onrender.com/api/v1`
- **Probe Results:**
  - `GET /api/v1/health` -> **200 OK** (`{"status":"ok"}`)
  - `GET /api/v1/health/ready` -> **503 Service Unavailable**
    ```json
    {"status":"schema_mismatch","database":"reachable","schema":{"current":["0072"],"expected":["0070"],"up_to_date":false}}
    ```
- **Deployment Status:**
  - The live Render container is running an earlier build that expected schema `0070` (Neon staging is at `0072`).
  - OpenAPI introspection (`/openapi.json`) confirms that 439 routes are currently loaded, but the new H8.6/H8.7/M21 routes (`/intelligence/fleet/overview`, `/mro-intelligence/candidates`) are not yet active on the live container.
  - **Reason:** Render webhook on `staging/m17-drone-ops-review` either has a build queue latency (5–8 minutes on free tier) or requires triggering "Manual Deploy -> Clear build cache & deploy" on the Render Dashboard for `aerocomply-backend-staging`.

### 1.2 Vercel Frontend (`aerocomply.vercel.app`)
- **FQDN:** `https://aerocomply.vercel.app`
- **Probe Results:**
  - `GET /` -> **200 OK** (7,479 bytes HTML)
  - `GET /intelligence/fleet` -> **200 OK** (16,172 bytes HTML)
- **Deployment Status:** **DEPLOYED & ACTIVE**. The static Next.js route `/intelligence/fleet` is served by Vercel edge nodes.

---

## 2. Live Staging Endpoint Verification Matrix

| Endpoint | Method | Live Staging Response | Local Port 55432 Response | Status / Finding |
|---|---|---|---|---|
| `/health` | GET | **200 OK** (`{"status":"ok"}`) | **200 OK** | Live container is responsive |
| `/health/ready` | GET | **503** (schema expected 0070, found 0072) | **200 OK** | Container pending rebuild to latest branch commit |
| `/intelligence/fleet/overview` | GET | **404 Not Found** | **200 OK** (Fleet metrics) | Pending Render container deployment |
| `/intelligence/fleet/signals` | GET | **404 Not Found** | **200 OK** (Signal stream) | Pending Render container deployment |
| `/intelligence/fleet/mro` | GET | **404 Not Found** | **200 OK** (MRO context) | Pending Render container deployment |
| `/mro-intelligence/candidates` | GET | **404 Not Found** | **200 OK** (3 candidates) | Pending Render container deployment |
| `/mro-intelligence/candidates/{id}/draft-work-order` | POST | **404 Not Found** | **200 OK** (Created WO) / **409 Conflict** (Dedup) | Pending Render container deployment |

---

## 3. Staging Demo-Seeding Plan (Awaiting Authorization)

Per non-negotiable rules: **No seeding, reset, or database modification has been performed on the staging database.**

### 3.1 Target Environment & Tenant Identity
- **Target Organization:** `Kota Aerospace Demo Operations`
- **Target Database:** Staging Neon PostgreSQL instance (`small-meadow-85982633` / `aerocomply_staging`).
- **Target Connection String Environment Variable:** `DATABASE_URL`

### 3.2 Database Safeguards
1. **Strict Tenant Scoping:** `seed_m21_demo_environment.py` resolves the unique tenant UUID for `Kota Aerospace Demo Operations`. All insertions, queries, and deletions are strictly filtered by `WHERE organization_id == org_id`.
2. **Customer Tenant Protection:** Zero queries or deletions can reach real customer tenants (`Apex Aero`, `SkyGrid`, etc.). Verified by `test_m21_demo_reset_safety`.
3. **Idempotence Guard:** When run without `--reset`, the seeder queries existing assets (`existing_asset_count >= 9`) and exits cleanly in <0.5s without re-inserting or modifying records.
4. **Credential Security:** Password is not hardcoded. The seeder reads `DEMO_PASSWORD` from the environment:
   ```bash
   $env:DEMO_PASSWORD = "<secure_staging_demo_password>"
   ```
   Plaintext credentials are never written to standard output.

### 3.3 Execution Command (To Be Run Only After Staging Deployment & Authorization)
```bash
# 1. Set Staging Neon Database URL and Secure Rotating Credential
$env:DATABASE_URL = "<neon_staging_database_connection_string>"
$env:DEMO_PASSWORD = "<secure_temporary_demo_password>"

# 2. Run Seeder with Safe Demo-Tenant Reset
python backend/scripts/seed_m21_demo_environment.py --reset
```

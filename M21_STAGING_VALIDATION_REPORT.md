# Milestone M21 Staging Validation Report
## Environment Verification, Route Health & Deployment Status

**Date:** 2026-10-04  
**Target Environments:**
- Staging Backend: `https://aerocomply-backend-staging.onrender.com/api/v1`
- Staging Frontend: `https://aerocomply.vercel.app`
- Local Test Environment: PostgreSQL port 55432 / localhost  

---

## 1. Deployed Environment Probing Results

| Endpoint / Target | Probed URL | Observed Status | Response Summary | Finding |
|---|---|---|---|---|
| **Staging Backend Health** | `https://aerocomply-backend-staging.onrender.com/api/v1/health` | **200 OK** | `{"status":"ok"}` | Staging backend container is healthy and responding. |
| **Staging Frontend Root** | `https://aerocomply.vercel.app` | **200 OK** | 7,479 bytes HTML | Vercel production edge is serving application bundle. |
| **Fleet Overview** | `.../intelligence/fleet/overview` | **404 Not Found** | `{"detail":"Not Found"}` | Route not yet deployed to staging (local commits held). |
| **Fleet Signals** | `.../intelligence/fleet/signals` | **404 Not Found** | `{"detail":"Not Found"}` | Route not yet deployed to staging (local commits held). |
| **Fleet MRO Context** | `.../intelligence/fleet/mro` | **404 Not Found** | `{"detail":"Not Found"}` | Route not yet deployed to staging (local commits held). |
| **MRO Candidates** | `.../mro-intelligence/candidates` | **404 Not Found** | `{"detail":"Not Found"}` | Route not yet deployed to staging (local commits held). |

### Analysis
The staging backend on Render is currently serving git revision `8bb5d02` / `origin/staging/m17-drone-ops-review`. Because the 14 commits ahead of origin have not yet been pushed, Render has not executed the build for H8.6, H8.7, M19.3, and M21.

---

## 2. Staging Deployment Execution Plan

Once push authorization is granted by the project owner:

### Step 1: Push Reviewed Commits to Origin
```bash
git push origin staging/m17-drone-ops-review
```

### Step 2: Automated Deployment Tracking
- **Render Webhook:** Trigger automatic build on Render (`aerocomply-backend-staging`).
  - Expected build command: `pip install -r requirements.txt`
  - Expected pre-deploy: `alembic upgrade head`
- **Vercel Webhook:** Trigger automatic frontend build on Vercel (`aerocomply.vercel.app`).
  - Expected build: `next build` (114 routes)

### Step 3: Staging Backend Verification
Verify routes on deployed staging URL:
```bash
curl -i -H "Authorization: Bearer <staging_token>" https://aerocomply-backend-staging.onrender.com/api/v1/intelligence/fleet/overview
curl -i -H "Authorization: Bearer <staging_token>" https://aerocomply-backend-staging.onrender.com/api/v1/mro-intelligence/candidates
```

### Step 4: Staging Demo Population
Execute the idempotent seeder against the staging database:
```bash
$env:DATABASE_URL = "<staging_postgres_connection_string>"
$env:DEMO_PASSWORD = "<secure_temporary_staging_password>"
python backend/scripts/seed_m21_demo_environment.py --reset
```

### Step 5: Staging Organization Review
Log in as `demo.admin@kotaaerospace.com` at `https://aerocomply.vercel.app/login` and navigate to `/intelligence/fleet`. Verify:
1. Fleet Overview KPI cards (9 assets).
2. Signals & Attention tab (Scenario B & F warnings).
3. Cross-Asset Anomaly tab (Scenario C vibration cluster).
4. Predictive MRO tab (Scenario D conflict and Scenario F drafted work order).
5. LISA Assistant answering grounded questions without fabricating data.

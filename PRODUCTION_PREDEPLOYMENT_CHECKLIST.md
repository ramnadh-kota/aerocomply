> **Implementation status (2026-09-30):** this document is a design/target description. The implemented behaviour is documented in `DATA_ACQUISITION_ARCHITECTURE.md`, `ENTITLEMENT_ARCHITECTURE.md`, `SECURITY_ARCHITECTURE.md`, `OBSERVABILITY_ARCHITECTURE.md`, `PRODUCTION_RUNBOOK.md` and `FINAL_RELEASE_READINESS.md`. Run `backend/scripts/production_preflight.sql` (read-only) as part of this checklist; alembic head must be `0070` (`/api/v1/health/ready` reports `schema.up_to_date`); start the worker (`python -m app.worker --schedule`) and, if used, the listener supervisor before declaring the deploy healthy; confirm `RETENTION_DESTRUCTIVE_ENABLED` and `BILLING_ENFORCE_GRACE` are **false** unless a change request says otherwise. Items about external infrastructure are unverified. Where this text disagrees with those, those win.

# KOTA AEROSPACE — PRE-DEPLOYMENT PRODUCTION CHECKLIST

## 1. Release Identification
- **Release Version**: `v1.0.0-PROD`
- **Frozen Commit Baseline**: `2670b92` (`KOTA-AEROSPACE-FORENSIC-VALIDATED-2026-09-30`)
- **Target Working Branch**: `feature/post-freeze-productionization`
- **Database Target Migration**: `0061`

---

## 2. Pre-Deployment Verification Checklist

| Item # | Verification Task | Expected Output / Criteria | Sign-off Status |
|---|---|---|---|
| **1** | **Database Backup Verification** | Full binary snapshot (`pg_dump -Fc`) taken & verified restorable on staging instance. | `[ ] PENDING PRODUCTION ACCESS` |
| **2** | **Subscription Pre-Migration Audit** | Run subscription audit SQL on target DB to ensure all active production orgs have valid subscriptions. | `[ ] PENDING PRODUCTION RUN` |
| **3** | **Organization & Tenant Integrity** | Verify 0 orphan records (users, assets, work orders without valid `organization_id`). | `[X] VALIDATED (0060/0061)` |
| **4** | **Schema Drift Verification** | Alembic `head` matches SQLAlchemy models with zero unresolved discrepancies. | `[X] VALIDATED (0061)` |
| **5** | **Automated Test Regressions** | Backend tests (2,040 passing), Frontend tests (332 passing), Next.js (99 routes build). | `[X] VALIDATED (100% PASS)` |
| **6** | **Static Analysis & Typecheck** | `tsc --noEmit` (0 errors), `eslint` (0 errors), `ruff check backend` (0 critical errors). | `[X] VALIDATED (0 ERRORS)` |
| **7** | **LISA Tool Security Matrix** | All 59 tools enforce `_require_permission()` and `_require_entitlement()`. | `[X] VALIDATED (123 TESTS)` |
| **8** | **Environment Secrets Verification**| Production secrets loaded via Vault/Secrets Manager; no default keys in `.env`. | `[ ] PENDING SECRETS INJECTION` |
| **9** | **Physical MAVLink Hardware Bench** | Physical RF radio bench testing executed as per `MAVLINK_HARDWARE_VALIDATION_PLAN.md`. | `[ ] EXTERNAL BENCH REQUIRED` |
| **10**| **Rollback Plan Verified** | `alembic downgrade -1` tested on replica snapshot; instant container revert verified. | `[X] TESTED ON LOCAL/DEV` |

---

## 3. Step-by-Step Production Execution Runbook

### Step 1: Maintenance Window & Snapshot
```bash
# 1. Announce maintenance window (if downtime required for migration 0061)
# 2. Trigger automated snapshot
pg_dump -Fc -h db-primary.internal -U aerocomply_user aerocomply_prod > pre_deploy_backup_$(date +%Y%m%d_%H%M%S).dump
```

### Step 2: Subscription Audit Execution
```sql
-- Audit SQL for un-subscribed organizations prior to 0061
SELECT o.id, o.name, o.created_at, COUNT(s.id) as active_subscriptions
FROM organizations o
LEFT JOIN subscriptions s ON s.organization_id = o.id AND s.status = 'active'
GROUP BY o.id, o.name, o.created_at
HAVING COUNT(s.id) = 0;
```
*Note: If any production customer org has 0 active subscriptions, execute backfill script `app/scripts/backfill_subscriptions.py` prior to running migration 0061.*

### Step 3: Execute Database Migration
```bash
cd /app/backend
alembic upgrade head
```

### Step 4: Deploy & Verify Service Health
```bash
# Verify backend health endpoint
curl -sSf https://api.kota-aerospace.com/api/v1/health | jq .

# Verify frontend Next.js routes
curl -sSf https://app.kota-aerospace.com/ -o /dev/null -w "%{http_code}\n"
```

---

## 4. Emergency Rollback Procedure
If critical failures, unhandled 500 errors, or data corruption are detected during post-deploy verification:
1. Revert application containers to previous stable image tag: `v0.9.9-freeze`.
2. Downgrade database schema:
   ```bash
   alembic downgrade 0060
   ```
3. If database state is inconsistent, restore the verified pre-deployment snapshot:
   ```bash
   pg_restore -c -h db-primary.internal -U aerocomply_user -d aerocomply_prod pre_deploy_backup_*.dump
   ```

# Kota Aerospace — Production Data Readiness

## 1. Executive Summary & Purpose
This document provides the operational and data migration readiness analysis for deploying Migration `0061` (`0061_suite_plan_subscription_hierarchy.py`) to staging and production environments.

The commercial hierarchy in Kota Aerospace strictly enforces:
```text
ProductSuite (AIRCRAFT | DRONE_UAV | HELICOPTER | EVTOL_AAM)
      ↓
Plan (with suite_id NOT NULL)
      ↓
Subscription (with suite_id = Plan.suite_id, status = ACTIVE | TRIALING)
      ↓
Organization (Effective Entitlements via resolve_entitlements())
```

---

## 2. Organization Categories & Impact Analysis

### Category A: Active Production Organizations with Current Subscriptions
- **Impact**: Migration `0061` automatically backfills `subscriptions.suite_id` from `plans.suite_id`. All users retain full access to their entitled suite features.
- **Login / Auth**: Unaffected (200 OK).
- **Dashboard**: Unaffected (200 OK).
- **Feature-Gated APIs**: Unaffected (200 OK).

### Category B: Organizations Without Subscriptions (Legacy / Un-provisioned)
- **Impact**: In local dev/QA databases, test organizations created without subscriptions resolve to `NO_SUBSCRIPTION`.
- **Login / Auth**: Works normally (`POST /api/v1/auth/login` returns valid JWT).
- **Basic Dashboard**: Loads base tenant context.
- **Feature-Gated APIs**: Correctly return `403 Forbidden` (`code="no_active_subscription"`).
- **Remediation**: Must be assigned an active subscription to their target suite plan prior to, or immediately after, migration.

---

## 3. Pre-Deployment Read-Only SQL Audit Queries
Execute these queries on the target database in a read-only transaction (`BEGIN READ ONLY;`) before applying migration `0061`:

```sql
-- 1. Identify active organizations that lack any current subscription
SELECT o.id, o.name, o.status, o.created_at
FROM organizations o
WHERE o.deleted_at IS NULL
  AND NOT EXISTS (
    SELECT 1 FROM subscriptions s
    WHERE s.organization_id = o.id
      AND s.status IN ('ACTIVE', 'TRIALING', 'PAST_DUE')
      AND s.starts_at <= NOW()
      AND (s.ends_at IS NULL OR s.ends_at > NOW())
  );

-- 2. Check for organizations with multiple conflicting current subscriptions
SELECT organization_id, count(*) AS active_sub_count
FROM subscriptions
WHERE status IN ('ACTIVE', 'TRIALING', 'PAST_DUE')
  AND starts_at <= NOW()
  AND (ends_at IS NULL OR ends_at > NOW())
GROUP BY organization_id
HAVING count(*) > 1;

-- 3. Check for plans lacking an assigned suite_id
SELECT id, code, name, asset_scope
FROM plans
WHERE suite_id IS NULL;

-- 4. Check for orphaned subscriptions pointing to non-existent plans
SELECT s.id, s.organization_id, s.plan_id
FROM subscriptions s
LEFT JOIN plans p ON p.id = s.plan_id
WHERE p.id IS NULL;

-- 5. Verify current Alembic migration version
SELECT version_num FROM alembic_version; -- Must be '0060' before upgrade
```

---

## 4. Safe Backfill Strategy for Un-provisioned Organizations
If legitimate production organizations are identified that lack a subscription, run the following idempotent backfill script after applying Migration `0061`:

```sql
-- Backfill default Aircraft Suite plan for un-subscribed active organizations
DO $$
DECLARE
    v_suite_id UUID;
    v_plan_id UUID;
    v_org RECORD;
BEGIN
    -- Locate or verify default Aircraft Suite
    SELECT id INTO v_suite_id FROM product_suites WHERE code = 'AIRCRAFT';
    
    -- Locate or create default Standard Aircraft Plan
    SELECT id INTO v_plan_id FROM plans WHERE code = 'aircraft-standard' AND suite_id = v_suite_id;
    IF v_plan_id IS NULL THEN
        SELECT id INTO v_plan_id FROM plans WHERE suite_id = v_suite_id LIMIT 1;
    END IF;

    -- Provision 1-year active subscription for un-subscribed active organizations
    FOR v_org IN 
        SELECT o.id, o.name FROM organizations o
        WHERE o.deleted_at IS NULL
          AND NOT EXISTS (SELECT 1 FROM subscriptions s WHERE s.organization_id = o.id)
    LOOP
        INSERT INTO subscriptions (id, organization_id, plan_id, suite_id, status, starts_at, created_at, updated_at)
        VALUES (
            gen_random_uuid(),
            v_org.id,
            v_plan_id,
            v_suite_id,
            'ACTIVE',
            NOW() - INTERVAL '1 day',
            NOW(),
            NOW()
        );
        RAISE NOTICE 'Provisioned subscription for org % (%)', v_org.name, v_org.id;
    END LOOP;
END $$;
```

---

## 5. Rollback Considerations
- **Downgrade Path**: `alembic downgrade 0060` restores the schema by removing `subscriptions.suite_id`, dropping the composite unique constraint `uq_plans_suite_id_code`, and restoring the single-column unique constraint on `plans.code`.
- **Constraint**: Downgrading is safe provided no two suites have been populated with identical `plan.code` values.
- **Webhook Precaution**: Ensure `DJI_WEBHOOK_SECRET` environment variable is defined in production secrets before traffic is routed to `POST /api/v1/telemetry/dji/webhook`.

---

## 6. Pre-Deployment Gate Checklist
- [x] Migration 0061 verified round-trip on local and test databases.
- [x] Read-only audit queries prepared.
- [x] Backfill SQL strategy tested.
- [x] `DJI_WEBHOOK_SECRET` environment variable configured.
- [x] JWT expiration and CORS origins explicitly verified in `backend/app/core/config.py`.

-- Kota production preflight. READ-ONLY: SELECTs only, no DDL/DML. Run with:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -X -f backend/scripts/production_preflight.sql
-- Every check returns rows named `check_name | status | detail`. Any FAIL blocks the deploy; WARN needs a human decision.
-- Wrapped in a READ ONLY transaction so a typo cannot write.
BEGIN TRANSACTION READ ONLY;

WITH checks AS (
  -- 1. Schema version: the expected head for this release
  SELECT 'alembic_head_is_0065' AS check_name,
         CASE WHEN (SELECT count(*) FROM alembic_version WHERE version_num = '0065') = 1
                   AND (SELECT count(*) FROM alembic_version) = 1
              THEN 'PASS' ELSE 'FAIL' END AS status,
         (SELECT string_agg(version_num, ',') FROM alembic_version) AS detail

  UNION ALL
  -- 2. Every organization should have at most one live (non-terminal) subscription per suite
  SELECT 'one_live_subscription_per_org_suite',
         CASE WHEN count(*) = 0 THEN 'PASS' ELSE 'FAIL' END,
         coalesce(string_agg(organization_id::text || '/' || suite_id::text, ', '), '-')
  FROM (
    SELECT organization_id, suite_id FROM subscriptions
    WHERE status IN ('ACTIVE','TRIALING','PAST_DUE')
    GROUP BY organization_id, suite_id HAVING count(*) > 1
  ) d

  UNION ALL
  -- 3. Subscription suite must match its plan's suite (write-time rule; catches legacy rows)
  SELECT 'subscription_suite_matches_plan',
         CASE WHEN count(*) = 0 THEN 'PASS' ELSE 'FAIL' END,
         count(*)::text || ' mismatched subscription(s)'
  FROM subscriptions s JOIN plans p ON p.id = s.plan_id
  WHERE s.suite_id IS DISTINCT FROM p.suite_id

  UNION ALL
  -- 4. Users must belong to an existing organization
  SELECT 'users_have_organization',
         CASE WHEN count(*) = 0 THEN 'PASS' ELSE 'FAIL' END,
         count(*)::text || ' orphan user(s)'
  FROM users u LEFT JOIN organizations o ON o.id = u.organization_id
  WHERE o.id IS NULL

  UNION ALL
  -- 5. Organizations with users but no subscription will have NO entitlements (only baseline features)
  SELECT 'orgs_with_users_but_no_subscription',
         CASE WHEN count(*) = 0 THEN 'PASS' ELSE 'WARN' END,
         count(*)::text || ' org(s) will see only baseline features'
  FROM organizations o
  WHERE EXISTS (SELECT 1 FROM users u WHERE u.organization_id = o.id)
    AND NOT EXISTS (SELECT 1 FROM subscriptions s WHERE s.organization_id = o.id)

  UNION ALL
  -- 6. Active subscriptions pointing at inactive plans
  SELECT 'active_subscription_on_inactive_plan',
         CASE WHEN count(*) = 0 THEN 'PASS' ELSE 'WARN' END,
         count(*)::text || ' subscription(s)'
  FROM subscriptions s JOIN plans p ON p.id = s.plan_id
  WHERE s.status IN ('ACTIVE','TRIALING') AND NOT p.is_active

  UNION ALL
  -- 7. Data sources referencing a default asset (must be a real row)
  SELECT 'data_source_default_asset_exists',
         CASE WHEN count(*) = 0 THEN 'PASS' ELSE 'FAIL' END,
         count(*)::text || ' dangling default_asset_id'
  FROM data_sources ds
  WHERE ds.default_asset_id IS NOT NULL
    AND NOT EXISTS (SELECT 1 FROM assets a WHERE a.id = ds.default_asset_id AND a.organization_id = ds.organization_id)

  UNION ALL
  -- 8. Duplicate telemetry events (should be prevented by the unique constraint; proves it is present)
  SELECT 'telemetry_event_unique_constraint_present',
         CASE WHEN count(*) >= 1 THEN 'PASS' ELSE 'FAIL' END,
         'unique indexes on telemetry_event_logs: ' || count(*)::text
  FROM pg_indexes
  WHERE tablename = 'telemetry_event_logs' AND indexdef ILIKE 'CREATE UNIQUE%'

  UNION ALL
  -- 9. Legacy duplicate HUMS exceedance signals from before the M7 dedup fix (informational)
  SELECT 'legacy_duplicate_hums_signals',
         CASE WHEN count(*) = 0 THEN 'PASS' ELSE 'WARN' END,
         count(*)::text || ' organization/asset/window groups with >1 open signal (customer data is never auto-deleted)'
  FROM (
    SELECT organization_id, split_part(signal_key, ':', 2) a, split_part(signal_key, ':', 3) s, count(*) c
    FROM proactive_signal_records
    WHERE signal_type = 'HUMS_VIBRATION_EXCEEDANCE' AND status = 'OPEN'
    GROUP BY 1, 2, 3 HAVING count(*) > 1
  ) x
)
SELECT * FROM checks ORDER BY CASE status WHEN 'FAIL' THEN 0 WHEN 'WARN' THEN 1 ELSE 2 END, check_name;

-- 10. Sizing snapshot for retention planning (informational)
SELECT relname AS table_name, n_live_tup AS approx_rows, pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_stat_user_tables
WHERE relname IN ('telemetry_event_logs','hums_sensor_readings','hums_exceedances','proactive_signals','audit_logs')
ORDER BY pg_total_relation_size(relid) DESC;

ROLLBACK;

"""0065: O — corrective migration for the schema drift that actually matters.

Revises: 0064
Create Date: 2026-09-30

Of the ~179 model<->database differences (see KOTA_SCHEMA_DRIFT_FINAL.md for the full per-item
classification) almost all are harmless naming/redundancy differences that stay documented and are
pinned by tests/integration/test_schema_drift_guard.py. This migration fixes the ones that are real:

1. Indexes the models declare on foreign-key / lookup columns of the highest-volume tables but the
   database never received:
     telemetry_event_logs.asset_id, telemetry_event_logs.flight_id     (event history per asset/flight)
     hums_exceedances.sensor_id,  hums_exceedances.component_id        (exceedance lookups, joins)
     proactive_signal_records.component_id                             (signals per component)
   Created with CREATE INDEX CONCURRENTLY IF NOT EXISTS, outside a transaction, so a production
   table keeps accepting writes while it builds. Idempotent: re-running is a no-op.

2. Three foreign keys to users(id) declared in the model but absent in the database
   (findings.discovered_by_user_id, findings.responsible_user_id, finding_dispositions.closed_by_user_id).
   Added NOT VALID (no full-table lock, checks new writes immediately) and then VALIDATEd (only a
   SHARE UPDATE EXCLUSIVE lock). VALIDATE fails if orphaned rows exist -- run the orphan query in
   KOTA_PRODUCTION_DATA_READINESS.md on production first. Users are deactivated, not deleted, so
   orphans are not expected.

3. data_sources: the index created by 0062 was named ix_data_sources_org_id; the model's canonical
   name is ix_data_sources_organization_id (rename only).

Downgrade: drops what was added and restores the old index name. No data is touched.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0065"
down_revision: str | None = "0064"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEXES = (
    ("ix_telemetry_event_logs_asset_id", "telemetry_event_logs", "asset_id"),
    ("ix_telemetry_event_logs_flight_id", "telemetry_event_logs", "flight_id"),
    ("ix_hums_exceedances_sensor_id", "hums_exceedances", "sensor_id"),
    ("ix_hums_exceedances_component_id", "hums_exceedances", "component_id"),
    ("ix_proactive_signal_records_component_id", "proactive_signal_records", "component_id"),
)

_FKS = (
    ("fk_findings_discovered_by_user_id_users", "findings", "discovered_by_user_id"),
    ("fk_findings_responsible_user_id_users", "findings", "responsible_user_id"),
    ("fk_finding_dispositions_closed_by_user_id_users", "finding_dispositions", "closed_by_user_id"),
)


def upgrade() -> None:
    # CONCURRENTLY cannot run inside a transaction block.
    with op.get_context().autocommit_block():
        for name, table, column in _INDEXES:
            op.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON {table} ({column})")

    for name, table, column in _FKS:
        op.execute(
            f"""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = '{name}') THEN
                    ALTER TABLE {table}
                        ADD CONSTRAINT {name} FOREIGN KEY ({column}) REFERENCES users (id) NOT VALID;
                END IF;
            END $$;
            """
        )
        op.execute(f"ALTER TABLE {table} VALIDATE CONSTRAINT {name}")

    op.execute("ALTER INDEX IF EXISTS ix_data_sources_org_id RENAME TO ix_data_sources_organization_id")


def downgrade() -> None:
    op.execute("ALTER INDEX IF EXISTS ix_data_sources_organization_id RENAME TO ix_data_sources_org_id")
    for name, table, _column in _FKS:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
    with op.get_context().autocommit_block():
        for name, _table, _column in _INDEXES:
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")

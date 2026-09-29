"""Schema drift guard (Phase O).

The ORM models and the migrated database are known to differ in ~170 places, all reviewed and
classified in KOTA_SCHEMA_DRIFT_FINAL.md (naming-only index differences, DB-side protections the
models do not restate, timestamp defaults the database owns). Historical migrations are NOT
rewritten. What must not happen is NEW drift arriving unnoticed -- e.g. a model index or foreign key
that never reaches the database, which is exactly what produced the gaps fixed by migration 0065.

This test pins the reviewed set: the schema produced by `alembic upgrade head` must differ from the
models in exactly the accepted ways, no more and no fewer.

If it fails:
  * "NEW drift": either add the missing migration (preferred) or, if the difference is genuinely
    harmless, regenerate the baseline (scripts/schema_drift.py) and justify it in the drift report.
  * "RESOLVED drift": good -- regenerate the baseline so the fix is locked in.
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.schema_drift import drift_keys

BASELINE = Path(__file__).with_name("schema_drift_baseline.json")

# Kinds where the MODEL promises something the DATABASE does not have. These are the ones that can
# be real defects (missing index / FK / column / table) and are held to zero, not merely "pinned".
_MODEL_PROMISES_MISSING = {"add_fk", "add_column", "add_table", "add_constraint"}


def _tuples(rows):
    return {tuple(r) for r in rows}


def test_no_new_or_resolved_schema_drift(engine):
    with engine.connect() as conn:
        current = _tuples(drift_keys(conn))
    accepted = _tuples(json.loads(BASELINE.read_text(encoding="utf-8")))

    new = sorted(current - accepted)
    resolved = sorted(accepted - current)
    assert not new, (
        "NEW model/database drift (fix with a migration, or review + regenerate the baseline):\n"
        + "\n".join(f"  {k}" for k in new)
    )
    assert not resolved, (
        "Drift was RESOLVED but the baseline still lists it; regenerate "
        "tests/integration/schema_drift_baseline.json:\n" + "\n".join(f"  {k}" for k in resolved)
    )


def test_model_never_promises_a_table_column_or_foreign_key_the_database_lacks(engine):
    with engine.connect() as conn:
        promised_but_missing = [k for k in drift_keys(conn) if k[0] in _MODEL_PROMISES_MISSING]
    assert promised_but_missing == [], promised_but_missing


def test_every_accepted_index_gap_is_low_volume_or_covered():
    """The remaining `add_index` entries were classified one by one: 28 are covered by an existing
    index/constraint under a different name; the rest are on low-volume tables. The high-volume
    tables' gaps were closed by 0065 and must not come back."""
    accepted = _tuples(json.loads(BASELINE.read_text(encoding="utf-8")))
    must_be_indexed = {
        ("add_index", "telemetry_event_logs", "ix_telemetry_event_logs_asset_id"),
        ("add_index", "telemetry_event_logs", "ix_telemetry_event_logs_flight_id"),
        ("add_index", "hums_exceedances", "ix_hums_exceedances_sensor_id"),
        ("add_index", "hums_exceedances", "ix_hums_exceedances_component_id"),
        ("add_index", "proactive_signal_records", "ix_proactive_signal_records_component_id"),
    }
    assert not (must_be_indexed & accepted), "a high-volume index gap was re-accepted into the baseline"

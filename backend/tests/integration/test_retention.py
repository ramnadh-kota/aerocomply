"""Retention: nothing destructive without explicit configuration; dry-run; floors; tenant scoping; evidence kept;
archive-before-delete; audit trail."""
from __future__ import annotations

import gzip
import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.models.audit_event import AuditEvent
from app.models.background_job import BackgroundJob, JobStatus
from app.models.hums import HUMSExceedance, HUMSSensor, HUMSSensorReading
from app.models.retention import RetentionClass as RC
from app.models.telemetry import TelemetryEventLog, TelemetryProcessingStatus
from app.services import retention_service as rs
from tests.integration.test_acquisition_pipeline import _csv, _drone, _ingest, _org, _source

settings = get_settings()
NOW = datetime(2026, 9, 30, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _switches():
    old = (settings.retention_destructive_enabled, settings.retention_archive_dir)
    settings.retention_destructive_enabled, settings.retention_archive_dir = True, None
    yield
    settings.retention_destructive_enabled, settings.retention_archive_dir = old


def _tenant(client, db, tag):
    """Org with one sensor (created via a real ingest) plus old/recent readings inserted directly."""
    org_id, h = _org(client, db, tag)
    asset = uuid.UUID(_drone(client, h, reg=f"RET-{tag}"))
    sid = _source(client, h, "CSV_BATCH")
    _ingest(client, h, sid, _csv([{"asset_id": f"RET-{tag}", "sensor_code": "T1", "value": "1", "unit": "C",
                                   "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}]))
    sensor = db.execute(select(HUMSSensor).where(HUMSSensor.organization_id == org_id)).scalars().first()
    for days in (400, 200, 100, 5):                                        # 3 old, 1 recent
        db.add(HUMSSensorReading(organization_id=org_id, sensor_id=sensor.id, asset_id=asset,
                                 recorded_at=NOW - timedelta(days=days), value=1.0, unit="C"))
    db.flush()
    return org_id, h, sensor


def _n(db, org_id, model=HUMSSensorReading):
    return db.scalar(select(func.count(model.id)).where(model.organization_id == org_id))


def test_nothing_is_purged_without_an_enabled_policy(client, db_session):
    org_id, _, _ = _tenant(client, db_session, "r1")
    before = _n(db_session, org_id)
    assert rs.run_retention(db_session, dry_run=False, organization_id=org_id, now=NOW) == []
    rs.set_policy(db_session, organization_id=org_id, data_class=RC.TELEMETRY_READINGS, retention_days=90, enabled=False)
    assert rs.run_retention(db_session, dry_run=False, organization_id=org_id, now=NOW) == []   # disabled policy
    assert _n(db_session, org_id) == before


def test_dry_run_reports_but_deletes_nothing_and_execution_needs_the_deployment_switch(client, db_session):
    org_id, _, _ = _tenant(client, db_session, "r2")
    rs.set_policy(db_session, organization_id=org_id, data_class=RC.TELEMETRY_READINGS, retention_days=90, enabled=True)
    before = _n(db_session, org_id)
    (res,) = rs.run_retention(db_session, dry_run=True, organization_id=org_id, now=NOW)
    assert res.eligible == 3 and res.deleted == 0 and _n(db_session, org_id) == before
    settings.retention_destructive_enabled = False
    with pytest.raises(rs.RetentionError, match="disabled"):
        rs.run_retention(db_session, dry_run=False, organization_id=org_id, now=NOW)
    assert _n(db_session, org_id) == before


def test_policy_floors_and_validation(client, db_session):
    org_id, _, _ = _tenant(client, db_session, "r3")
    with pytest.raises(rs.RetentionError, match="30"):
        rs.set_policy(db_session, organization_id=org_id, data_class=RC.TELEMETRY_READINGS, retention_days=7, enabled=True)
    with pytest.raises(rs.RetentionError):
        rs.set_policy(db_session, organization_id=org_id, data_class="AUDIT_EVENTS", retention_days=400, enabled=True)
    with pytest.raises(rs.RetentionError, match="not found"):
        rs.set_policy(db_session, organization_id=uuid.uuid4(), data_class=RC.TELEMETRY_READINGS, retention_days=90, enabled=True)
    # a hand-edited row below the floor cannot undercut it at run time
    p = rs.set_policy(db_session, organization_id=org_id, data_class=RC.TELEMETRY_READINGS, retention_days=90, enabled=True)
    p.retention_days = 1
    db_session.flush()
    (res,) = rs.run_retention(db_session, dry_run=True, organization_id=org_id, now=NOW)
    assert res.retention_days == 30


def test_purge_is_tenant_scoped_keeps_recent_data_and_evidence_and_writes_an_audit_event(client, db_session):
    org_a, _, sensor_a = _tenant(client, db_session, "r4a")
    org_b, _, _ = _tenant(client, db_session, "r4b")
    # an exceedance whose window covers the 200-day-old reading: that reading is evidence and must survive
    db_session.add(HUMSExceedance(
        organization_id=org_a, sensor_id=sensor_a.id, asset_id=sensor_a.asset_id, parameter="vibration_rms",
        observed_value=9.0, threshold_value=5.0, severity="HIGH",
        window_start=NOW - timedelta(days=200, minutes=1), window_end=NOW - timedelta(days=200) + timedelta(minutes=1),
        contributing_reading_ids=[]))
    db_session.flush()
    rs.set_policy(db_session, organization_id=org_a, data_class=RC.TELEMETRY_READINGS, retention_days=90, enabled=True)
    b_before = _n(db_session, org_b)

    (res,) = rs.run_retention(db_session, dry_run=False, now=NOW)          # global entry point, tenant-scoped execution
    assert (res.organization_id, res.eligible, res.deleted) == (org_a, 2, 2)      # 400d and 100d; 200d kept as evidence
    assert _n(db_session, org_a) == 1 + 1 + 1                                      # first real one + 200d + 5d
    assert _n(db_session, org_b) == b_before                                       # other tenant untouched
    ev = db_session.execute(select(AuditEvent).where(
        AuditEvent.organization_id == org_a, AuditEvent.action == "retention.purged")).scalar_one()
    assert ev.event_metadata["deleted"] == 2 and ev.event_metadata["data_class"] == RC.TELEMETRY_READINGS
    assert rs.run_retention(db_session, dry_run=False, now=NOW)[0].deleted == 0    # idempotent


def test_tenant_policy_overrides_platform_default(client, db_session):
    org_id, _, _ = _tenant(client, db_session, "r5")
    rs.set_policy(db_session, organization_id=None, data_class=RC.TELEMETRY_READINGS, retention_days=30, enabled=True)
    (res,) = [r for r in rs.run_retention(db_session, dry_run=True, organization_id=org_id, now=NOW)]
    assert res.retention_days == 30 and res.eligible == 3
    rs.set_policy(db_session, organization_id=org_id, data_class=RC.TELEMETRY_READINGS, retention_days=365, enabled=True)
    (res,) = rs.run_retention(db_session, dry_run=True, organization_id=org_id, now=NOW)
    assert res.retention_days == 365 and res.eligible == 1
    rs.set_policy(db_session, organization_id=org_id, data_class=RC.TELEMETRY_READINGS, retention_days=365, enabled=False)
    assert rs.run_retention(db_session, dry_run=True, organization_id=org_id, now=NOW) == []   # tenant opt-out wins


def test_archive_is_written_and_verified_before_delete(client, db_session, tmp_path):
    org_id, _, _ = _tenant(client, db_session, "r6")
    settings.retention_archive_dir = str(tmp_path)
    rs.set_policy(db_session, organization_id=org_id, data_class=RC.TELEMETRY_READINGS, retention_days=90, enabled=True)
    (res,) = rs.run_retention(db_session, dry_run=False, organization_id=org_id, now=NOW)
    assert res.deleted == 3 and len(res.archived_files) == 1
    rows = [json.loads(line) for line in gzip.open(res.archived_files[0], "rt", encoding="utf-8")]
    assert len(rows) == 3 and {r["organization_id"] for r in rows} == {str(org_id)}


def test_failed_archive_blocks_deletion(client, db_session, tmp_path):
    org_id, _, _ = _tenant(client, db_session, "r7")
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x")
    settings.retention_archive_dir = str(blocker)                             # cannot mkdir underneath a file
    before = _n(db_session, org_id)
    rs.set_policy(db_session, organization_id=org_id, data_class=RC.TELEMETRY_READINGS, retention_days=90, enabled=True)
    (res,) = rs.run_retention(db_session, dry_run=False, organization_id=org_id, now=NOW)
    assert res.deleted == 0 and res.error and _n(db_session, org_id) == before


def test_event_log_keeps_quarantined_and_jobs_keep_active_and_recent_dead(client, db_session):
    org_id, _, _ = _tenant(client, db_session, "r8")
    old = NOW - timedelta(days=400)

    def log_row(status, i):
        return TelemetryEventLog(
            organization_id=org_id, source_system="X", source_event_id=f"e{i}", idempotency_key=f"k{i}",
            event_type="SENSOR_BURST", event_timestamp=old, received_timestamp=old, payload_hash="h",
            processing_status=status)

    db_session.add_all([log_row(TelemetryProcessingStatus.PROCESSED, 1), log_row(TelemetryProcessingStatus.QUARANTINED, 2),
                        log_row(TelemetryProcessingStatus.DUPLICATE, 3)])

    def job(status, age_days, key):
        return BackgroundJob(organization_id=org_id, job_type="t", status=status, payload={}, dedupe_key=key,
                             attempts=1, max_attempts=5, run_after=old,
                             finished_at=NOW - timedelta(days=age_days) if status != JobStatus.QUEUED else None)

    db_session.add_all([job(JobStatus.SUCCEEDED, 200, "a"), job(JobStatus.DEAD, 10, "b"), job(JobStatus.DEAD, 200, "c"),
                        job(JobStatus.QUEUED, 0, "d")])
    db_session.flush()
    for c in (RC.TELEMETRY_EVENT_LOG, RC.BACKGROUND_JOBS):
        rs.set_policy(db_session, organization_id=org_id, data_class=c, retention_days=90, enabled=True)
    res = {r.data_class: r for r in rs.run_retention(db_session, dry_run=False, organization_id=org_id, now=NOW)}
    assert res[RC.TELEMETRY_EVENT_LOG].deleted == 2                                 # PROCESSED + DUPLICATE
    left = db_session.execute(select(TelemetryEventLog.processing_status).where(
        TelemetryEventLog.organization_id == org_id, TelemetryEventLog.source_system == "X")).scalars().all()
    assert left == [TelemetryProcessingStatus.QUARANTINED]                          # awaiting triage: kept
    assert res[RC.BACKGROUND_JOBS].deleted == 2                                     # old SUCCEEDED + old DEAD
    remaining = {j.dedupe_key for j in db_session.execute(select(BackgroundJob).where(
        BackgroundJob.organization_id == org_id, BackgroundJob.job_type == "t")).scalars()}
    assert remaining == {"b", "d"}                                                  # recent DEAD and QUEUED survive


def test_platform_api_dry_run_default_switch_and_rbac(client, db_session):
    from tests.integration.conftest import make_platform_admin_headers

    pa = make_platform_admin_headers(client, db_session)
    org_id, tenant, _ = _tenant(client, db_session, "r9")
    assert client.get("/api/v1/platform/retention/policies", headers=tenant).status_code == 403
    assert client.put("/api/v1/platform/retention/policies", headers=tenant, json={}).status_code == 403
    bad = client.put("/api/v1/platform/retention/policies", headers=pa, json={
        "organization_id": str(org_id), "data_class": RC.TELEMETRY_READINGS, "retention_days": 3, "enabled": True})
    assert bad.status_code == 422
    ok = client.put("/api/v1/platform/retention/policies", headers=pa, json={
        "organization_id": str(org_id), "data_class": RC.TELEMETRY_READINGS, "retention_days": 90, "enabled": True})
    assert ok.status_code == 200
    before = _n(db_session, org_id)
    dry = client.post(f"/api/v1/platform/retention/run?organization_id={org_id}", headers=pa).json()
    assert dry["dry_run"] is True and _n(db_session, org_id) == before                # default is a dry run
    settings.retention_destructive_enabled = False
    refused = client.post(f"/api/v1/platform/retention/run?dry_run=false&organization_id={org_id}", headers=pa)
    assert refused.status_code == 409 and _n(db_session, org_id) == before

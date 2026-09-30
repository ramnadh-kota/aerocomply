"""Signed MAVLink through the real ingest API: the key comes from the data source's secret_reference."""
import hashlib
import uuid

from sqlalchemy import func, select

from app.core import secrets
from app.models.hums import HUMSSensorReading
from tests.integration.test_acquisition_pipeline import _drone, _ingest, _org
from tests.unit.test_m20_mavlink_integrity import vibration
from tests.unit.test_mavlink_signing import vib


def _signed_source(client, h, asset, ref, *, require_signing=None):
    cfg = {"system_id_map": {"1": asset}}
    if require_signing is not None:
        cfg["require_signing"] = require_signing
    r = client.post("/api/v1/data-sources", headers=h, json={
        "name": f"sig-{uuid.uuid4().hex[:8]}", "connector_type": "MAVLINK", "connection_config": cfg,
        "secret_reference": ref})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    assert client.patch(f"/api/v1/data-sources/{sid}", headers=h, json={"status": "ACTIVE"}).status_code == 200
    return sid


def test_signed_source_accepts_genuine_and_rejects_forged_unsigned_and_replayed(client, db_session, monkeypatch):
    org_id, h = _org(client, db_session, "sig")
    asset = _drone(client, h)
    ref = f"datasource/{org_id}/{uuid.uuid4().hex[:6]}/mavlink_key"
    passphrase = "correct horse battery staple"
    monkeypatch.setenv(secrets.env_name(ref), passphrase)
    key = hashlib.sha256(passphrase.encode()).digest()          # passphrase -> SHA-256 convention
    sid = _signed_source(client, h, asset, ref)

    ok = _ingest(client, h, sid, vib(seq=1, ts=100, key=key)).json()
    assert ok["accepted"] == 1 and ok["rejected"] == 0

    forged = _ingest(client, h, sid, vib(seq=2, ts=101, key=b"\x07" * 32)).json()
    assert forged["accepted"] == 0 and forged["rejected"] == 1 and any("signature" in e for e in forged["errors"])
    unsigned = _ingest(client, h, sid, vibration(seq=3)).json()
    assert unsigned["accepted"] == 0 and any("unsigned" in e for e in unsigned["errors"])
    replay = _ingest(client, h, sid, vib(seq=1, ts=100, key=key)).json()
    assert replay["accepted"] == 0 and any("replayed" in e for e in replay["errors"])

    n = db_session.scalar(select(func.count(HUMSSensorReading.id)).where(
        HUMSSensorReading.organization_id == org_id, HUMSSensorReading.asset_id == uuid.UUID(asset)))
    assert n == 1                                                # only the genuine frame produced data
    health = client.get(f"/api/v1/data-sources/{sid}/health", headers=h).json()
    assert health["status"] in {"DEGRADED", "FAILED", "HEALTHY"} and health["last_error"]


def test_require_signing_without_a_resolvable_key_fails_closed(client, db_session):
    org_id, h = _org(client, db_session, "sig2")
    asset = _drone(client, h)
    sid = _signed_source(client, h, asset, "datasource/unset/key", require_signing=True)
    rep = _ingest(client, h, sid, vibration(seq=1)).json()
    assert rep["accepted"] == 0 and rep["rejected"] >= 1

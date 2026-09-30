"""Signed generic webhook ingestion for GENERIC_WEBHOOK data sources.

  POST /api/v1/webhooks/data-sources/{data_source_id}
    X-Kota-Timestamp: <unix seconds>
    X-Kota-Signature: sha256=<hex HMAC-SHA256(secret, "<timestamp>." + raw body)>

Third-party systems cannot hold a user JWT, so authenticity is an HMAC keyed by the data source's secret
(`secret_reference`, resolved from the platform secrets layer - never stored in the row). The tenant comes from the data
source row, never from the request. Design rules:
  * FAIL CLOSED: an unknown/paused/wrong-type source, a missing secret, a bad or stale signature all return the SAME 401,
    so the endpoint is not an oracle for source ids or configuration.
  * REPLAY: the timestamp must be within +-5 minutes and a signature is accepted once (job idempotency key); a replay
    returns 200 {"duplicate": true} without enqueueing anything.
  * The body is not parsed here: it is stored on the durable queue and processed by the normal acquisition pipeline
    (validation, normalization, dedup, quarantine) by a worker, so a slow or hostile payload cannot hold a request open.
  * Body cap 25 MB (413). Rate limited by the `webhook` policy (per client address)."""
from __future__ import annotations

import hashlib
import hmac
import time
import uuid

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import secrets as secrets_layer
from app.core.deps import get_db_session
from app.models.data_source import DataSource, DataSourceConnectorType, DataSourceStatus
from app.services import job_handlers, job_service

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])

MAX_BODY_BYTES = 25 * 1024 * 1024
TIMESTAMP_TOLERANCE_SECONDS = 300


def sign(secret: str, timestamp: str, body: bytes) -> str:
    """Signature a sender must produce (also used by tests and documented for integrators)."""
    mac = hmac.new(secret.encode("utf-8"), timestamp.encode("ascii") + b"." + body, hashlib.sha256)
    return "sha256=" + mac.hexdigest()


def _unauthorized() -> JSONResponse:
    return JSONResponse(status_code=401, content={"error": {"code": "invalid_webhook", "message": "Invalid webhook request."}})


@router.post("/data-sources/{data_source_id}")
async def receive(
    data_source_id: uuid.UUID,
    request: Request,
    x_kota_timestamp: str | None = Header(default=None),
    x_kota_signature: str | None = Header(default=None),
    db: Session = Depends(get_db_session),
):
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Payload too large")
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Payload too large")

    source = db.execute(select(DataSource).where(DataSource.id == data_source_id)).scalar_one_or_none()
    secret = secrets_layer.resolve(source.secret_reference) if source is not None else None
    usable = (
        source is not None and secret
        and source.connector_type == DataSourceConnectorType.GENERIC_WEBHOOK
        and source.status == DataSourceStatus.ACTIVE
    )
    # Always run the comparison (against a dummy key when unusable) so timing does not reveal which check failed.
    key = secret or "unusable"
    try:
        ts = int(x_kota_timestamp or "")
        fresh = abs(time.time() - ts) <= TIMESTAMP_TOLERANCE_SECONDS
    except ValueError:
        ts, fresh = 0, False
    expected = sign(key, str(ts), raw)
    matches = hmac.compare_digest(expected, x_kota_signature or "")
    if not (usable and fresh and matches):
        log.warning("webhook.rejected", data_source_id=str(data_source_id))
        return _unauthorized()
    if not raw:
        raise HTTPException(status_code=422, detail="Empty payload")

    job, created = job_service.enqueue(
        db, job_type=job_handlers.INGEST, organization_id=source.organization_id, data_source_id=source.id,
        payload={"topic": None, "via": "webhook"}, payload_blob=raw,
        idempotency_key="wh:" + hashlib.sha256((x_kota_signature or "").encode()).hexdigest()[:48],
        correlation_id="webhook",
    )
    db.commit()
    return JSONResponse(status_code=202 if created else 200,
                        content={"job_id": str(job.id), "status": job.status, "duplicate": not created})

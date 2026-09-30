"""B5/B6/B8/B14: acquisition orchestration.

One place that turns "a configured DataSource + some raw data" into persisted telemetry:

    DataSource (tenant-bound, ACTIVE)
        -> connector (MAVLink | MQTT | CSV | JSON | canonical webhook JSON)
        -> NormalizedTelemetryEvent
        -> telemetry_service.process_normalized_event   (THE existing persistence path:
           timestamp quality gate, deterministic asset resolution, idempotency, flights,
           sensors/readings, exceedance evaluation, event log, audit)
        -> DataSource health evidence (last seen/success/failure, counts, loss, latency)

Nothing here re-implements telemetry logic; it only binds a source to the tenant, applies
connector state, isolates failures per event (SAVEPOINT) and records evidence.

Tenancy: the organization comes from the DataSource row, which is loaded WITH the caller's
organization id. An attacker's request can never route data into another tenant, and a
`default_asset_id` is re-verified to belong to the source's tenant on every ingest.

Connector state (MAVLink sequence tracking) lives in this process (`_CONNECTORS`). With
several API workers each keeps its own view; sequence/duplicate protection is therefore
per worker, while idempotency of persisted events is enforced by the database.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import secrets as secrets_layer
from app.core.errors import AeroComplyError, ConflictError, NotFoundError
from app.models.asset import Asset
from app.models.data_source import DataSource, DataSourceConnectorType, DataSourceStatus
from app.models.telemetry import TelemetryProcessingStatus
from app.schemas.telemetry import NormalizedTelemetryEvent
from app.services import audit_service, telemetry_service
from app.services.edge.batch_connectors import CSVBatchConnector, JSONBatchConnector
from app.services.edge.mavlink_connector import MAVLinkConnector
from app.services.edge.mqtt_connector import MQTTConnector

log = structlog.get_logger(__name__)

_SOURCE_SYSTEM_DEFAULTS = {
    DataSourceConnectorType.MAVLINK: "KOTA_MAVLINK_GATEWAY",
    DataSourceConnectorType.MQTT: "MQTT",
    DataSourceConnectorType.CSV_BATCH: "CSV_BATCH",
    DataSourceConnectorType.JSON_BATCH: "JSON_BATCH",
    DataSourceConnectorType.GENERIC_WEBHOOK: "GENERIC_WEBHOOK",
    DataSourceConnectorType.OEM_API: "OEM_API",
}
INGESTABLE_TYPES = frozenset(_SOURCE_SYSTEM_DEFAULTS)
_MAX_ERROR_SAMPLES = 10
_LATENCY_EWMA_ALPHA = 0.3

# (data_source_id -> stateful connector). Process-local; see module docstring.
_CONNECTORS: dict[uuid.UUID, Any] = {}


@dataclass
class AcquisitionReport:
    """Result of one ingest call (returned to the caller and used for health evidence)."""

    received: int = 0            # events presented to persistence
    accepted: int = 0            # persisted (PROCESSED)
    duplicates: int = 0          # already processed / dropped by sequence
    quarantined: int = 0         # asset unresolved or ambiguous
    rejected: int = 0            # failed quality gate or could not be parsed
    failed: int = 0              # unexpected processing error (isolated per event)
    packets_lost: int = 0        # skipped link sequence numbers (MAVLink)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    latency_ms_avg: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "received": self.received,
            "accepted": self.accepted,
            "duplicates": self.duplicates,
            "quarantined": self.quarantined,
            "rejected": self.rejected,
            "failed": self.failed,
            "packets_lost": self.packets_lost,
            "warnings": self.warnings[:_MAX_ERROR_SAMPLES],
            "errors": self.errors[:_MAX_ERROR_SAMPLES],
            "latency_ms_avg": self.latency_ms_avg,
        }


# ----------------------------------------------------------------------------- helpers
def _mavlink_signing_key(secret_reference: str | None) -> bytes | None:
    """32-byte MAVLink 2 signing key from the platform secret named by the data source. Accepts 64 hex characters,
    or a passphrase (key = SHA-256(passphrase), the convention used by MAVLink ground stations)."""
    secret = secrets_layer.resolve(secret_reference)
    if not secret:
        return None
    try:
        raw = bytes.fromhex(secret)
        if len(raw) == 32:
            return raw
    except ValueError:
        pass
    return hashlib.sha256(secret.encode("utf-8")).digest()


def _load_source(db: Session, organization_id: uuid.UUID, data_source_id: uuid.UUID) -> DataSource:
    source = db.execute(
        select(DataSource).where(
            DataSource.id == data_source_id, DataSource.organization_id == organization_id
        )
    ).scalar_one_or_none()
    if source is None:
        raise NotFoundError("Data source not found")
    return source


def _verified_default_asset(db: Session, source: DataSource) -> Asset | None:
    """default_asset_id is only honoured if it is (still) an undeleted asset of the source's
    own tenant; anything else is ignored rather than trusted."""
    if source.default_asset_id is None:
        return None
    return db.execute(
        select(Asset).where(
            Asset.id == source.default_asset_id,
            Asset.organization_id == source.organization_id,
            Asset.deleted_at.is_(None),
        )
    ).scalar_one_or_none()


def _source_system(source: DataSource) -> str:
    cfg = source.connection_config or {}
    return str(cfg.get("source_system") or _SOURCE_SYSTEM_DEFAULTS[source.connector_type])[:64]


def _connector_for(source: DataSource) -> Any:
    cfg = source.connection_config or {}
    ctype = source.connector_type
    if ctype == DataSourceConnectorType.MAVLINK:
        conn = _CONNECTORS.get(source.id)
        if conn is None:
            sysid_map = {
                int(k): str(v) for k, v in (cfg.get("system_id_map") or {}).items() if str(k).isdigit()
            }
            signing_key = _mavlink_signing_key(source.secret_reference)
            conn = MAVLinkConnector(
                connector_id=f"ds-{source.id}",
                source_system=_source_system(source),
                asset_mapping_override=sysid_map,
                signing_key=signing_key,
                # require_signing=true with no resolvable key fails CLOSED: every frame is rejected as unsigned
                require_signed=True if cfg.get("require_signing") else None,
            )
            conn.connect()
            _CONNECTORS[source.id] = conn
        return conn
    if ctype == DataSourceConnectorType.MQTT:
        conn = _CONNECTORS.get(source.id)
        if conn is None:
            conn = MQTTConnector(
                connector_id=f"ds-{source.id}",
                source_system=_source_system(source),
                topic_filter=str(cfg.get("topic_filter") or "#"),
            )
            conn.connect(str(cfg.get("endpoint") or "mqtt://managed-by-caller"))
            _CONNECTORS[source.id] = conn
        return conn
    if ctype == DataSourceConnectorType.CSV_BATCH:
        return CSVBatchConnector(connector_id=f"ds-{source.id}", source_system=_source_system(source))
    if ctype == DataSourceConnectorType.OEM_API:
        if str(((cfg.get("poll") or {}).get("format")) or "json").lower() == "csv":
            return CSVBatchConnector(connector_id=f"ds-{source.id}", source_system=_source_system(source))
        return JSONBatchConnector(connector_id=f"ds-{source.id}", source_system=_source_system(source))
    if ctype in (DataSourceConnectorType.JSON_BATCH, DataSourceConnectorType.GENERIC_WEBHOOK):
        return JSONBatchConnector(connector_id=f"ds-{source.id}", source_system=_source_system(source))
    raise ConflictError(
        f"Data source type {ctype} is not ingestable through this endpoint "
        "(DJI FlightHub uses its signed webhook)",
        code="unsupported_connector_type",
    )


def forget_connector(data_source_id: uuid.UUID) -> None:
    """Drop cached connector state (call when a source is reconfigured, paused or deleted)."""
    _CONNECTORS.pop(data_source_id, None)


def _sanitise(msg: str) -> str:
    return " ".join(str(msg).split())[:200]


# ----------------------------------------------------------------------------- core
def _decode(source: DataSource, raw: bytes, topic: str | None, report: AcquisitionReport
            ) -> list[NormalizedTelemetryEvent]:
    conn = _connector_for(source)
    ctype = source.connector_type
    if ctype == DataSourceConnectorType.MAVLINK:
        before = dict(conn.integrity)
        errors_before = conn.stats.parse_errors
        events = conn.feed_bytes(raw)
        report.packets_lost = conn.integrity["lost"] - before["lost"]
        report.duplicates += conn.integrity["duplicates"] - before["duplicates"]
        report.rejected += conn.integrity["crc_errors"] - before["crc_errors"]
        for key in ("late", "ignored_component", "ignored_sysid", "unsupported_msgid"):
            delta = conn.integrity[key] - before[key]
            if delta:
                report.warnings.append(f"{delta} frame(s) dropped: {key}")
        if conn.integrity["crc_errors"] - before["crc_errors"]:
            report.errors.append("frames failed checksum verification")
        for key, text in (("bad_signature", "frames failed MAVLink signature verification"),
                          ("replayed_signature", "replayed (stale-timestamp) signed frames"),
                          ("unsigned_rejected", "unsigned frames refused (signing required)")):
            delta = conn.integrity[key] - before[key]
            if delta:
                report.rejected += delta       # security rejections are failures, never silent drops
                report.errors.append(f"{delta} {text}")
        if conn.stats.parse_errors - errors_before and not events:
            report.errors.append("no valid MAVLink frames in payload")
        return _apply_binding(source, events)
    if ctype == DataSourceConnectorType.MQTT:
        errors_before = conn.stats.parse_errors
        events = conn.feed_bytes(raw, topic=topic or "")
        failed = conn.stats.parse_errors - errors_before
        if failed:
            report.rejected += failed
            report.errors.append("MQTT payload could not be parsed")
        return _apply_binding(source, events)
    # batch-style: whole file / body
    try:
        result = conn.process_file(raw)
    except ValueError as exc:
        report.errors.append(_sanitise(exc))
        report.rejected += 1
        return []
    if result.errors:
        report.rejected += result.errors
        report.errors.extend(_sanitise(e) for e in result.error_samples[:_MAX_ERROR_SAMPLES])
    return _apply_binding(source, result.events)


def _apply_binding(source: DataSource, events: list[NormalizedTelemetryEvent]
                   ) -> list[NormalizedTelemetryEvent]:
    """Explicit single-asset binding (opt-in): config {"asset_binding": "SINGLE_ASSET"} +
    default_asset_id makes EVERY event of this source belong to that asset. Never implicit."""
    cfg = source.connection_config or {}
    if cfg.get("asset_binding") != "SINGLE_ASSET" or source.default_asset_id is None:
        return events
    for e in events:
        e.source_asset_id = str(source.default_asset_id)  # resolved by asset id, tenant-checked
    return events


def ingest(
    db: Session,
    *,
    organization_id: uuid.UUID,
    data_source_id: uuid.UUID,
    raw: bytes,
    topic: str | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> AcquisitionReport:
    """Ingest one payload for a data source and record its health evidence."""
    source = _load_source(db, organization_id, data_source_id)
    # every log line emitted while processing this payload (persistence, HUMS, errors) now carries
    # the source, so an operator can follow one source through the whole pipeline
    structlog.contextvars.bind_contextvars(data_source_id=str(source.id), connector_type=source.connector_type)
    try:
        return _ingest_bound(db, source, raw=raw, topic=topic, actor_user_id=actor_user_id)
    finally:
        structlog.contextvars.unbind_contextvars("data_source_id", "connector_type")


def _ingest_bound(
    db: Session, source: DataSource, *, raw: bytes, topic: str | None, actor_user_id: uuid.UUID | None
) -> AcquisitionReport:
    from app.core import metrics

    with metrics.Timer() as timer:
        report = _ingest_core(db, source, raw=raw, topic=topic, actor_user_id=actor_user_id)
    ctype = source.connector_type
    metrics.INGEST_REQUESTS.inc(connector=ctype)
    metrics.INGEST_LATENCY.observe(timer.seconds, connector=ctype)
    for outcome in ("accepted", "duplicates", "quarantined", "rejected", "failed"):
        n = getattr(report, outcome)
        if n:
            metrics.INGEST_EVENTS.inc(n, connector=ctype, outcome=outcome)
    if report.packets_lost:
        metrics.INGEST_PACKETS_LOST.inc(report.packets_lost, connector=ctype)
    if report.latency_ms_avg is not None and report.accepted:
        metrics.INGEST_EVENT_AGE.observe(report.latency_ms_avg / 1000.0, connector=ctype)
    return report


def _ingest_core(
    db: Session, source: DataSource, *, raw: bytes, topic: str | None, actor_user_id: uuid.UUID | None
) -> AcquisitionReport:
    if source.status != DataSourceStatus.ACTIVE:
        raise ConflictError(
            f"Data source is {source.status}; only ACTIVE sources accept data",
            code="data_source_not_active",
        )
    if source.connector_type not in INGESTABLE_TYPES:
        _connector_for(source)  # raises the structured unsupported error

    report = AcquisitionReport()
    received_at = datetime.now(UTC)
    single_asset = (source.connection_config or {}).get("asset_binding") == "SINGLE_ASSET"
    if single_asset and _verified_default_asset(db, source) is None:
        report.errors.append("single-asset binding points to an asset outside this organization or deleted")
        report.rejected += 1
        _record_health(db, source, report, received_at)
        return report

    try:
        events = _decode(source, raw, topic, report)
    except AeroComplyError:
        raise  # structured, intentional errors (e.g. unsupported connector) keep their status
    except Exception as exc:  # noqa: BLE001 -- payload CONTENT must never crash the endpoint
        events = []
        report.rejected += 1
        report.errors.append(_sanitise(f"payload could not be processed ({type(exc).__name__})"))
        log.warning(
            "acquisition.decode_failed",
            organization_id=str(source.organization_id), data_source_id=str(source.id),
            error=type(exc).__name__,
        )
    report.received = len(events)
    latencies: list[float] = []
    hums_pending: dict[uuid.UUID, int] = {}

    for event in events:
        try:
            with db.begin_nested():  # one bad event must not abort the whole payload
                res = telemetry_service.process_normalized_event(
                    db, organization_id=source.organization_id, event=event, hums_pending=hums_pending
                )
        except IntegrityError as exc:
            if "uq_telemetry_event_org_source_eventid" in str(exc.orig):
                # Two workers processed the same event at once; the database let exactly one win.
                report.duplicates += 1
                continue
            report.failed += 1
            if len(report.errors) < _MAX_ERROR_SAMPLES:
                report.errors.append(_sanitise(f"IntegrityError: {exc.orig}"))
            continue
        except Exception as exc:  # noqa: BLE001 -- isolated, logged, counted
            report.failed += 1
            if len(report.errors) < _MAX_ERROR_SAMPLES:
                report.errors.append(_sanitise(f"{type(exc).__name__}: {exc}"))
            log.warning(
                "acquisition.event_failed",
                organization_id=str(source.organization_id),
                data_source_id=str(source.id),
                source_event_id=event.source_event_id,
                error=type(exc).__name__,
            )
            continue
        telemetry_service.evaluate_pending_sensors(db, organization_id=source.organization_id, pending=hums_pending)
        status = res.status
        if status == TelemetryProcessingStatus.PROCESSED:
            report.accepted += 1
            latencies.append(max(0.0, (received_at - event.event_timestamp).total_seconds() * 1000.0))
        elif status == TelemetryProcessingStatus.DUPLICATE:
            report.duplicates += 1
        elif status == TelemetryProcessingStatus.QUARANTINED:
            report.quarantined += 1
            if len(report.warnings) < _MAX_ERROR_SAMPLES:
                report.warnings.append(_sanitise(res.message or "quarantined"))
        else:  # REJECTED / FAILED
            report.rejected += 1
            if len(report.errors) < _MAX_ERROR_SAMPLES:
                report.errors.append(_sanitise(res.message or status))
    telemetry_service.evaluate_pending_sensors(
        db, organization_id=source.organization_id, pending=hums_pending, force=True
    )
    if latencies:
        report.latency_ms_avg = round(sum(latencies) / len(latencies), 1)

    _record_health(db, source, report, received_at)
    db.flush()
    log.info(
        "acquisition.ingested",
        organization_id=str(source.organization_id),
        data_source_id=str(source.id),
        connector_type=source.connector_type,
        **{k: v for k, v in report.to_dict().items() if isinstance(v, int)},
    )
    if report.failed or report.rejected or report.quarantined:
        audit_service.record_audit_event(
            db,
            organization_id=source.organization_id,
            user_id=actor_user_id,
            action="data_source.ingest_issues",
            entity_type="DataSource",
            entity_id=source.id,
            metadata={k: v for k, v in report.to_dict().items() if isinstance(v, int) and v},
        )
    return report


def _record_health(db: Session, source: DataSource, report: AcquisitionReport, now: datetime) -> None:
    """Evidence-based counters. `last_success_at` only moves when an event was really accepted;
    an all-duplicate payload proves the source is alive (last_seen) without being a failure."""
    source.last_seen_at = now
    source.total_events_ingested += report.accepted
    source.total_events_duplicate += report.duplicates
    source.total_events_quarantined += report.quarantined
    source.total_events_rejected += report.rejected + report.failed
    source.total_packets_lost += report.packets_lost
    if report.latency_ms_avg is not None:
        prev = source.latency_ms_avg
        source.latency_ms_avg = (
            report.latency_ms_avg if prev is None
            else round(_LATENCY_EWMA_ALPHA * report.latency_ms_avg + (1 - _LATENCY_EWMA_ALPHA) * prev, 1)
        )
    if report.accepted > 0:
        source.last_success_at = now
        source.last_acquisition_at = now
        source.consecutive_failures = 0
    elif report.duplicates > 0 and not (report.rejected or report.failed):
        pass  # alive, nothing new, not a failure
    else:
        source.consecutive_failures += 1
        source.last_failure_at = now
        first = (report.errors or report.warnings or ["no events accepted"])[0]
        source.last_error = _sanitise(first)[:512]
    db.add(source)


# ----------------------------------------------------------------------------- health
def compute_health_detail(source: DataSource, now: datetime | None = None) -> dict[str, Any]:
    """Health (HEALTHY | DEGRADED | FAILED | INACTIVE) derived ONLY from recorded evidence.

    Optional connection_config keys:  expected_interval_seconds  -- how often data should
    arrive; enables staleness detection (>3x DEGRADED, >10x FAILED).
    A source that has never received data reports reason NO_DATA_YET (HEALTHY unless an
    expected interval says it is overdue), never a fabricated 'all good'.
    Evidence fields are read defensively so the function also works on partial objects."""
    now = now or datetime.now(UTC)

    def g(name: str, default: Any = None) -> Any:
        return getattr(source, name, default)

    cfg = g("connection_config") or {}
    status = g("status")
    if status != DataSourceStatus.ACTIVE:
        return _detail(source, "INACTIVE", f"source is {status}", now)
    reasons: list[str] = []
    level = 0  # 0 healthy, 1 degraded, 2 failed

    failures = g("consecutive_failures", 0) or 0
    if failures >= 5:
        level, reasons = 2, reasons + [f"{failures} consecutive failures"]
    elif failures >= 2:
        level, reasons = max(level, 1), reasons + [f"{failures} consecutive failures"]

    interval = cfg.get("expected_interval_seconds")
    if isinstance(interval, (int, float)) and interval > 0:
        ref = g("last_success_at") or g("last_acquisition_at") or g("created_at")
        age = (now - ref).total_seconds() if ref else None
        if age is not None:
            what = "no data since" if g("last_success_at") else "no data since activation/creation"
            if age > 10 * interval:
                level, reasons = 2, reasons + [f"{what} {int(age)}s (expected every {int(interval)}s)"]
            elif age > 3 * interval:
                level, reasons = max(level, 1), reasons + [f"{what} {int(age)}s (expected every {int(interval)}s)"]

    ingested = g("total_events_ingested", 0) or 0
    lost = g("total_packets_lost", 0) or 0
    quarantined = g("total_events_quarantined", 0) or 0
    delivered = ingested + lost
    if lost >= 10 and delivered and lost / delivered >= 0.2:
        level, reasons = max(level, 1), reasons + [f"packet loss {lost}/{delivered}"]
    seen = ingested + quarantined
    if quarantined >= 5 and seen and quarantined / seen >= 0.5:
        level, reasons = max(level, 1), reasons + ["most events quarantined (asset mapping problem)"]

    if not reasons and g("last_success_at") is None and not g("last_acquisition_at"):
        reasons = ["NO_DATA_YET"]
    return _detail(source, ("HEALTHY", "DEGRADED", "FAILED")[level], "; ".join(reasons) or "receiving data", now)


def _detail(source: DataSource, status: str, reason: str, now: datetime) -> dict[str, Any]:
    def iso(name: str) -> str | None:
        d = getattr(source, name, None)
        return d.isoformat() if d else None

    def n(name: str, default: Any = 0) -> Any:
        v = getattr(source, name, default)
        return default if v is None else v

    return {
        "data_source_id": str(getattr(source, "id", "")),
        "status": status,
        "reason": reason,
        "source_status": getattr(source, "status", None),
        "last_seen_at": iso("last_seen_at"),
        "last_success_at": iso("last_success_at"),
        "last_failure_at": iso("last_failure_at"),
        "last_error": getattr(source, "last_error", None),
        "event_count": n("total_events_ingested"),
        "error_count": n("total_events_rejected"),
        "duplicate_count": n("total_events_duplicate"),
        "quarantined_count": n("total_events_quarantined"),
        "loss_count": n("total_packets_lost"),
        "latency_ms": getattr(source, "latency_ms_avg", None),
        "consecutive_failures": n("consecutive_failures"),
        "evaluated_at": now.isoformat(),
    }


def get_health(db: Session, *, organization_id: uuid.UUID, data_source_id: uuid.UUID) -> dict[str, Any]:
    return compute_health_detail(_load_source(db, organization_id, data_source_id))


__all__ = [
    "AcquisitionReport", "ingest", "get_health", "compute_health_detail", "forget_connector",
    "INGESTABLE_TYPES",
]

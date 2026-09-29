"""M13 Phase 5: Production Observability & Hypercare Service.

Provides operational monitoring, telemetry metrics, HUMS state aggregation,
intelligence signal summaries, and P0-P3 incident management.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.finding import Finding, FindingStatus
from app.models.hums import (
    HUMSDiagnosticCandidate,
    HUMSExceedance,
    HUMSSensor,
    HUMSSensorReading,
)
from app.models.proactive_signal import ProactiveSignalRecord
from app.models.sso import (
    IncidentSeverity,
    IncidentStatus,
    OperationalIncident,
    SSOConfiguration,
)
from app.models.telemetry import (
    ExternalAssetMapping,
    TelemetryEventLog,
    TelemetryProcessingStatus,
)
from app.schemas.observability import (
    HUMSSummary,
    HypercareSummaryResponse,
    IncidentsSummary,
    IntelligenceSummary,
    OperationalIncidentCreate,
    OperationalIncidentUpdate,
    TelemetrySummary,
)
from app.services.audit_service import record_audit_event


def get_hypercare_summary(db: Session, organization_id: uuid.UUID) -> HypercareSummaryResponse:
    # 1. Telemetry metrics
    total_telemetry = db.execute(
        select(func.count(TelemetryEventLog.id)).where(
            TelemetryEventLog.organization_id == organization_id
        )
    ).scalar_one() or 0

    processed_telemetry = db.execute(
        select(func.count(TelemetryEventLog.id)).where(
            TelemetryEventLog.organization_id == organization_id,
            TelemetryEventLog.processing_status == TelemetryProcessingStatus.PROCESSED,
        )
    ).scalar_one() or 0

    dup_telemetry = db.execute(
        select(func.count(TelemetryEventLog.id)).where(
            TelemetryEventLog.organization_id == organization_id,
            TelemetryEventLog.processing_status == TelemetryProcessingStatus.DUPLICATE,
        )
    ).scalar_one() or 0

    rejected_telemetry = db.execute(
        select(func.count(TelemetryEventLog.id)).where(
            TelemetryEventLog.organization_id == organization_id,
            TelemetryEventLog.processing_status == TelemetryProcessingStatus.REJECTED,
        )
    ).scalar_one() or 0

    failed_telemetry = db.execute(
        select(func.count(TelemetryEventLog.id)).where(
            TelemetryEventLog.organization_id == organization_id,
            TelemetryEventLog.processing_status == TelemetryProcessingStatus.FAILED,
        )
    ).scalar_one() or 0

    active_mapped_assets = db.execute(
        select(func.count(ExternalAssetMapping.id)).where(
            ExternalAssetMapping.organization_id == organization_id,
            ExternalAssetMapping.is_active.is_(True),
        )
    ).scalar_one() or 0

    # 2. HUMS metrics
    hums_sensors_count = db.execute(
        select(func.count(HUMSSensor.id)).where(
            HUMSSensor.organization_id == organization_id
        )
    ).scalar_one() or 0

    hums_active_sensors = db.execute(
        select(func.count(HUMSSensor.id)).where(
            HUMSSensor.organization_id == organization_id,
            HUMSSensor.status == "ACTIVE",
        )
    ).scalar_one() or 0

    hums_readings_count = db.execute(
        select(func.count(HUMSSensorReading.id)).where(
            HUMSSensorReading.organization_id == organization_id
        )
    ).scalar_one() or 0

    hums_exceedances = db.execute(
        select(func.count(HUMSExceedance.id)).where(
            HUMSExceedance.organization_id == organization_id
        )
    ).scalar_one() or 0

    hums_diagnostic_candidates = db.execute(
        select(func.count(HUMSDiagnosticCandidate.id)).where(
            HUMSDiagnosticCandidate.organization_id == organization_id
        )
    ).scalar_one() or 0

    # 3. Intelligence metrics
    active_signals = db.execute(
        select(func.count(ProactiveSignalRecord.id)).where(
            ProactiveSignalRecord.organization_id == organization_id,
            ProactiveSignalRecord.status == "ACTIVE",
        )
    ).scalar_one() or 0

    critical_signals = db.execute(
        select(func.count(ProactiveSignalRecord.id)).where(
            ProactiveSignalRecord.organization_id == organization_id,
            ProactiveSignalRecord.status == "ACTIVE",
            ProactiveSignalRecord.severity.in_(["CRITICAL", "HIGH"]),
        )
    ).scalar_one() or 0

    open_findings = db.execute(
        select(func.count(Finding.id)).where(
            Finding.organization_id == organization_id,
            Finding.status == FindingStatus.OPEN,
        )
    ).scalar_one() or 0

    # 4. Operational incidents
    open_p0 = db.execute(
        select(func.count(OperationalIncident.id)).where(
            OperationalIncident.organization_id == organization_id,
            OperationalIncident.severity == IncidentSeverity.P0,
            OperationalIncident.status.in_([IncidentStatus.OPEN, IncidentStatus.ACKNOWLEDGED]),
        )
    ).scalar_one() or 0

    open_p1 = db.execute(
        select(func.count(OperationalIncident.id)).where(
            OperationalIncident.organization_id == organization_id,
            OperationalIncident.severity == IncidentSeverity.P1,
            OperationalIncident.status.in_([IncidentStatus.OPEN, IncidentStatus.ACKNOWLEDGED]),
        )
    ).scalar_one() or 0

    open_p2 = db.execute(
        select(func.count(OperationalIncident.id)).where(
            OperationalIncident.organization_id == organization_id,
            OperationalIncident.severity == IncidentSeverity.P2,
            OperationalIncident.status.in_([IncidentStatus.OPEN, IncidentStatus.ACKNOWLEDGED]),
        )
    ).scalar_one() or 0

    open_p3 = db.execute(
        select(func.count(OperationalIncident.id)).where(
            OperationalIncident.organization_id == organization_id,
            OperationalIncident.severity == IncidentSeverity.P3,
            OperationalIncident.status.in_([IncidentStatus.OPEN, IncidentStatus.ACKNOWLEDGED]),
        )
    ).scalar_one() or 0

    total_open_incidents = open_p0 + open_p1 + open_p2 + open_p3

    # Platform status determination
    if open_p0 > 0 or failed_telemetry > 5:
        platform_status = "CRITICAL"
    elif open_p1 > 0 or rejected_telemetry > 0 or critical_signals > 0:
        platform_status = "DEGRADED"
    else:
        platform_status = "OPERATIONAL"

    # SSO configured check
    sso_config = db.execute(
        select(SSOConfiguration.id).where(
            SSOConfiguration.organization_id == organization_id,
            SSOConfiguration.is_active.is_(True),
        )
    ).scalar_one_or_none()

    return HypercareSummaryResponse(
        timestamp=datetime.now(UTC),
        organization_id=organization_id,
        platform_status=platform_status,
        telemetry=TelemetrySummary(
            total_events=total_telemetry,
            processed_count=processed_telemetry,
            duplicate_count=dup_telemetry,
            rejected_count=rejected_telemetry,
            failed_count=failed_telemetry,
            active_assets_reporting=active_mapped_assets,
        ),
        hums=HUMSSummary(
            sensor_count=hums_sensors_count,
            active_sensors=hums_active_sensors,
            readings_count=hums_readings_count,
            exceedance_count=hums_exceedances,
            diagnostic_candidates_count=hums_diagnostic_candidates,
        ),
        intelligence=IntelligenceSummary(
            active_signals_count=active_signals,
            critical_signals_count=critical_signals,
            open_findings_count=open_findings,
        ),
        incidents=IncidentsSummary(
            open_p0=open_p0,
            open_p1=open_p1,
            open_p2=open_p2,
            open_p3=open_p3,
            total_open=total_open_incidents,
        ),
        auth_sso_configured=sso_config is not None,
    )


def create_incident(
    db: Session,
    organization_id: uuid.UUID,
    payload: OperationalIncidentCreate,
    user_id: uuid.UUID | None = None,
) -> OperationalIncident:
    incident = OperationalIncident(
        organization_id=organization_id,
        severity=payload.severity,
        service_name=payload.service_name,
        title=payload.title,
        description=payload.description,
        status=IncidentStatus.OPEN,
        asset_id=payload.asset_id,
        first_detected_at=datetime.now(UTC),
        details=payload.details,
    )
    db.add(incident)
    db.flush()

    record_audit_event(
        db,
        user_id=user_id,
        organization_id=organization_id,
        action="INCIDENT_CREATED",
        entity_type="operational_incident",
        entity_id=incident.id,
        metadata={"severity": incident.severity, "service": incident.service_name, "title": incident.title},
    )

    return incident


def list_incidents(
    db: Session,
    organization_id: uuid.UUID,
    status: str | None = None,
    severity: str | None = None,
    limit: int = 50,
) -> list[OperationalIncident]:
    query = select(OperationalIncident).where(
        OperationalIncident.organization_id == organization_id
    )
    if status:
        query = query.where(OperationalIncident.status == status)
    if severity:
        query = query.where(OperationalIncident.severity == severity)
    query = query.order_by(OperationalIncident.created_at.desc()).limit(limit)
    return list(db.execute(query).scalars().all())


def acknowledge_incident(
    db: Session,
    organization_id: uuid.UUID,
    incident_id: uuid.UUID,
    user_id: uuid.UUID,
) -> OperationalIncident:
    incident = db.execute(
        select(OperationalIncident).where(
            OperationalIncident.id == incident_id,
            OperationalIncident.organization_id == organization_id,
        )
    ).scalar_one_or_none()
    if not incident:
        raise NotFoundError("Operational incident not found")

    incident.status = IncidentStatus.ACKNOWLEDGED
    incident.acknowledged_by_user_id = user_id
    db.flush()

    record_audit_event(
        db,
        user_id=user_id,
        organization_id=organization_id,
        action="INCIDENT_ACKNOWLEDGED",
        entity_type="operational_incident",
        entity_id=incident.id,
        metadata={"status": incident.status},
    )
    return incident


def resolve_incident(
    db: Session,
    organization_id: uuid.UUID,
    incident_id: uuid.UUID,
    user_id: uuid.UUID,
) -> OperationalIncident:
    incident = db.execute(
        select(OperationalIncident).where(
            OperationalIncident.id == incident_id,
            OperationalIncident.organization_id == organization_id,
        )
    ).scalar_one_or_none()
    if not incident:
        raise NotFoundError("Operational incident not found")

    incident.status = IncidentStatus.RESOLVED
    incident.resolved_at = datetime.now(UTC)
    db.flush()

    record_audit_event(
        db,
        user_id=user_id,
        organization_id=organization_id,
        action="INCIDENT_RESOLVED",
        entity_type="operational_incident",
        entity_id=incident.id,
        metadata={"status": incident.status, "resolved_at": incident.resolved_at.isoformat()},
    )
    return incident

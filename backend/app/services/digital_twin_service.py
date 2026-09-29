"""H6: Digital Asset & Component Twin — a READ-ONLY aggregation layer over
existing authoritative domain services.

Core principle (H6 spec section 2): the twin is NOT a duplicate copy of the
database. PostgreSQL remains the system of record. Every function here
calls an EXISTING service (asset_service, hums_service,
readiness_intelligence_service, ...) and assembles the results into one
response — it never re-derives health/diagnostics/prognostics/compliance/
readiness logic, and it never persists a competing "twin state" row.
There is therefore no `rebuild_twin()` function to implement separately
from a normal read — every call to this module already IS a fresh rebuild
from authoritative data (see docs/DIGITAL_TWIN_ARCHITECTURE.md's
"reconciliation" section for why this sidesteps the classic
twin-state-drift problem entirely, by construction).
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.component import Component
from app.models.finding import Finding
from app.models.hums import HUMSSensor
from app.models.installation_history import ComponentInstallation
from app.models.work_order import WorkOrder
from app.schemas.digital_twin import (
    DigitalTwinAssetSnapshot,
    DigitalTwinComplianceState,
    DigitalTwinComponentNode,
    DigitalTwinComponentSnapshot,
    DigitalTwinConsistencyWarning,
    DigitalTwinGenealogyEntry,
    DigitalTwinIdentity,
    DigitalTwinMaintenanceState,
    DigitalTwinReadinessState,
    DigitalTwinTimelineEvent,
)
from app.schemas.hums import HUMSDiagnosticCandidateResponse, HUMSPrognosticRecordResponse
from app.services import asset_service, hums_service
from app.services.intelligence import readiness_intelligence_service

# Bounded per-source-type limit for the timeline aggregation -- never an
# unbounded historical scan (H6 spec section 52).
TIMELINE_PER_SOURCE_LIMIT = 15
TIMELINE_TOTAL_LIMIT = 50


def get_asset_snapshot(db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID) -> DigitalTwinAssetSnapshot:
    """L1-L13 unified current-state view. Every sub-section is fetched from
    its own authoritative service — see this module's docstring.
    """
    asset = asset_service.get_asset(db, organization_id=organization_id, asset_id=asset_id)
    identity = DigitalTwinIdentity(
        asset_id=asset.id, asset_type=asset.asset_type, registration=asset.registration,
        serial_number=asset.serial_number, manufacturer=asset.manufacturer, model=asset.model, status=asset.status,
    )
    configuration = asset_service.get_asset_configuration(db, organization_id=organization_id, asset_id=asset_id)
    usage = asset_service.get_asset_utilization(db, organization_id=organization_id, asset_id=asset_id)

    try:
        health = hums_service.get_asset_health_intelligence(db, organization_id=organization_id, asset_id=asset_id)
    except Exception:
        health = None
    diagnostics = hums_service.list_asset_diagnostics(db, organization_id=organization_id, asset_id=asset_id)
    prognostics = hums_service.list_asset_prognostics(db, organization_id=organization_id, asset_id=asset_id)

    maint_data = asset_service.get_asset_maintenance(db, organization_id=organization_id, asset_id=asset_id)
    findings_data = asset_service.get_asset_findings(db, organization_id=organization_id, asset_id=asset_id)
    accomplishments = maint_data.get("accomplishments", [])
    maintenance = DigitalTwinMaintenanceState(
        availability="AVAILABLE",
        open_work_order_count=len([wo for wo in maint_data.get("open_work_orders", []) if wo["status"] not in ("COMPLETED", "CLOSED", "CANCELLED")]),
        open_finding_count=findings_data.get("open_count", 0),
        last_accomplishment_at=(
            datetime.datetime.fromisoformat(accomplishments[0]["accomplished_at"]) if accomplishments else None
        ),
    )

    compliance_data = asset_service.get_asset_compliance(db, organization_id=organization_id, asset_id=asset_id)
    compliance = DigitalTwinComplianceState(
        availability="AVAILABLE",
        assessment_count=len(compliance_data.get("assessments", [])),
        summary={
            "overall_status": compliance_data.get("overall_status"),
            "compliant_count": compliance_data.get("compliant_count"),
            "non_compliant_count": compliance_data.get("non_compliant_count"),
        },
    )

    try:
        readiness_intel = readiness_intelligence_service.get_asset_readiness_intelligence(
            db, organization_id=organization_id, asset_id=asset_id
        )
        readiness = DigitalTwinReadinessState(
            availability="AVAILABLE",
            readiness_state=readiness_intel.readiness_state,
            blocker_count=len(readiness_intel.blockers),
            blockers=[b.description for b in readiness_intel.blockers],
        )
    except Exception:
        readiness = DigitalTwinReadinessState(availability="DATA_UNAVAILABLE")

    return DigitalTwinAssetSnapshot(
        identity=identity, configuration=configuration, usage=usage, health=health,
        diagnostics=[HUMSDiagnosticCandidateResponse.model_validate(d) for d in diagnostics],
        prognostics=[HUMSPrognosticRecordResponse.model_validate(p) for p in prognostics],
        maintenance=maintenance, compliance=compliance, readiness=readiness,
        generated_at=datetime.datetime.now(datetime.UTC),
    )


def get_asset_component_tree(db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID) -> list[DigitalTwinComponentNode]:
    """L3 — flat Asset -> Component hierarchy (see DigitalTwinComponentNode's
    docstring for why this is flat, not nested)."""
    components = asset_service.get_asset_components(db, organization_id=organization_id, asset_id=asset_id)
    nodes: list[DigitalTwinComponentNode] = []
    for component in components:
        sensors = list(
            db.execute(
                select(HUMSSensor).where(HUMSSensor.organization_id == organization_id, HUMSSensor.component_id == component.id)
            ).scalars().all()
        )
        health_state = None
        if sensors:
            try:
                component_health = hums_service.get_component_health_intelligence(
                    db, organization_id=organization_id, component_id=component.id
                )
                health_state = component_health.state
            except Exception:
                health_state = None
        diagnostics = hums_service.list_component_diagnostics(db, organization_id=organization_id, component_id=component.id)
        prognostics = hums_service.list_component_prognostics(db, organization_id=organization_id, component_id=component.id)
        active_prognostic_status = prognostics[0].status if prognostics else None
        nodes.append(
            DigitalTwinComponentNode(
                component=component, health_state=health_state, diagnostic_count=len(diagnostics),
                active_prognostic_status=active_prognostic_status,
            )
        )
    return nodes


def get_component_snapshot(db: Session, *, organization_id: uuid.UUID, component_id: uuid.UUID) -> DigitalTwinComponentSnapshot:
    component = db.execute(
        select(Component).where(Component.id == component_id, Component.organization_id == organization_id)
    ).scalar_one_or_none()
    if not component:
        raise NotFoundError("Component not found", code="component_not_found")

    from app.schemas.asset import AssetComponentResponse

    genealogy = get_component_genealogy(db, organization_id=organization_id, component_id=component_id)
    current = next((g for g in genealogy if g.is_current), None)

    health = None
    sensors = list(
        db.execute(select(HUMSSensor).where(HUMSSensor.organization_id == organization_id, HUMSSensor.component_id == component_id)).scalars().all()
    )
    if sensors:
        try:
            component_health = hums_service.get_component_health_intelligence(db, organization_id=organization_id, component_id=component_id)
            health = component_health.model_dump(mode="json")
        except Exception:
            health = None

    diagnostics = hums_service.list_component_diagnostics(db, organization_id=organization_id, component_id=component_id)
    prognostics = hums_service.list_component_prognostics(db, organization_id=organization_id, component_id=component_id)

    return DigitalTwinComponentSnapshot(
        component=AssetComponentResponse.model_validate(component),
        current_asset_id=current.asset_id if current else component.asset_id,
        installed_at=current.installed_at if current else None,
        genealogy_entry_count=len(genealogy),
        health=health,
        diagnostics=[HUMSDiagnosticCandidateResponse.model_validate(d) for d in diagnostics],
        prognostics=[HUMSPrognosticRecordResponse.model_validate(p) for p in prognostics],
        generated_at=datetime.datetime.now(datetime.UTC),
    )


def get_component_genealogy(db: Session, *, organization_id: uuid.UUID, component_id: uuid.UUID) -> list[DigitalTwinGenealogyEntry]:
    """"Where has this component been?" (H6 spec section 17) — reuses the
    EXISTING ComponentInstallation history (H1/M17.2C), no new lineage
    model. Every installation span this component has ever had, across
    every asset it's been mounted on, oldest first.
    """
    from app.models.asset import Asset

    installations = list(
        db.execute(
            select(ComponentInstallation)
            .where(ComponentInstallation.organization_id == organization_id, ComponentInstallation.component_id == component_id)
            .order_by(ComponentInstallation.installed_at.asc())
        ).scalars().all()
    )
    asset_ids = {i.asset_id for i in installations}
    registrations = {}
    if asset_ids:
        for a in db.execute(select(Asset).where(Asset.id.in_(asset_ids))).scalars().all():
            registrations[a.id] = a.registration

    return [
        DigitalTwinGenealogyEntry(
            installation_id=i.id, asset_id=i.asset_id, asset_registration=registrations.get(i.asset_id),
            installed_at=i.installed_at, removed_at=i.removed_at, is_current=i.removed_at is None,
        )
        for i in installations
    ]


def get_asset_timeline(db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID) -> list[DigitalTwinTimelineEvent]:
    """Unified lifecycle timeline (H6 spec section 25) — a live, bounded
    UNION over existing entities' own timestamps, NOT a persisted event
    log. A new `HUMSTwinEvent` table would be a second, parallel history
    that could drift from the authoritative records it summarizes; this
    codebase's existing created_at/updated_at/occurred-at columns already
    ARE that history. See docs/DIGITAL_TWIN_ARCHITECTURE.md.
    """
    from app.models.asset import Asset
    from app.models.hums import HUMSDiagnosticCandidate, HUMSPrognosticRecord

    events: list[DigitalTwinTimelineEvent] = []

    asset = db.execute(select(Asset).where(Asset.id == asset_id, Asset.organization_id == organization_id)).scalar_one_or_none()
    if asset and asset.created_at:
        events.append(DigitalTwinTimelineEvent(occurred_at=asset.created_at, event_type="ASSET_CREATED", summary=f"Asset {asset.registration or asset.serial_number} created.", source_type="Asset", source_id=asset.id))

    installations = list(
        db.execute(
            select(ComponentInstallation)
            .where(ComponentInstallation.organization_id == organization_id, ComponentInstallation.asset_id == asset_id)
            .order_by(ComponentInstallation.installed_at.desc())
            .limit(TIMELINE_PER_SOURCE_LIMIT)
        ).scalars().all()
    )
    for i in installations:
        events.append(DigitalTwinTimelineEvent(occurred_at=i.installed_at, event_type="COMPONENT_INSTALLED", summary=f"Component {i.component_id} installed.", source_type="ComponentInstallation", source_id=i.id))
        if i.removed_at:
            events.append(DigitalTwinTimelineEvent(occurred_at=i.removed_at, event_type="COMPONENT_REMOVED", summary=f"Component {i.component_id} removed.", source_type="ComponentInstallation", source_id=i.id))

    diagnostics = list(
        db.execute(
            select(HUMSDiagnosticCandidate)
            .where(HUMSDiagnosticCandidate.organization_id == organization_id, HUMSDiagnosticCandidate.asset_id == asset_id)
            .order_by(HUMSDiagnosticCandidate.detected_at.desc())
            .limit(TIMELINE_PER_SOURCE_LIMIT)
        ).scalars().all()
    )
    for d in diagnostics:
        events.append(DigitalTwinTimelineEvent(occurred_at=d.detected_at, event_type="DIAGNOSTIC_CANDIDATE_GENERATED", summary=f"{d.fault_name} ({d.status}, {d.confidence} confidence).", source_type="HUMSDiagnosticCandidate", source_id=d.id))

    prognostics = list(
        db.execute(
            select(HUMSPrognosticRecord)
            .where(HUMSPrognosticRecord.organization_id == organization_id, HUMSPrognosticRecord.asset_id == asset_id)
            .order_by(HUMSPrognosticRecord.calculated_at.desc())
            .limit(TIMELINE_PER_SOURCE_LIMIT)
        ).scalars().all()
    )
    for p in prognostics:
        rul_text = f"RUL {p.rul_estimate} {p.rul_unit}" if p.rul_estimate is not None else p.status
        events.append(DigitalTwinTimelineEvent(occurred_at=p.calculated_at, event_type="PROGNOSTIC_UPDATED", summary=f"{p.feature_type}: {rul_text}.", source_type="HUMSPrognosticRecord", source_id=p.id))

    findings = list(
        db.execute(
            select(Finding).where(Finding.organization_id == organization_id, Finding.asset_id == asset_id).order_by(Finding.discovered_at.desc()).limit(TIMELINE_PER_SOURCE_LIMIT)
        ).scalars().all()
    )
    for f in findings:
        events.append(DigitalTwinTimelineEvent(occurred_at=f.discovered_at, event_type="FINDING_CREATED", summary=f.title, source_type="Finding", source_id=f.id))

    work_orders = list(
        db.execute(
            select(WorkOrder).where(WorkOrder.organization_id == organization_id, WorkOrder.asset_id == asset_id).order_by(WorkOrder.created_at.desc()).limit(TIMELINE_PER_SOURCE_LIMIT)
        ).scalars().all()
    )
    for wo in work_orders:
        events.append(DigitalTwinTimelineEvent(occurred_at=wo.created_at, event_type="WORK_ORDER_CREATED", summary=f"{wo.work_order_number}: {wo.title} ({wo.status}).", source_type="WorkOrder", source_id=wo.id))

    events.sort(key=lambda e: e.occurred_at, reverse=True)
    return events[:TIMELINE_TOTAL_LIMIT]


def get_component_timeline(db: Session, *, organization_id: uuid.UUID, component_id: uuid.UUID) -> list[DigitalTwinTimelineEvent]:
    events: list[DigitalTwinTimelineEvent] = []
    for entry in get_component_genealogy(db, organization_id=organization_id, component_id=component_id):
        events.append(DigitalTwinTimelineEvent(occurred_at=entry.installed_at, event_type="COMPONENT_INSTALLED", summary=f"Installed on {entry.asset_registration or entry.asset_id}.", source_type="ComponentInstallation", source_id=entry.installation_id))
        if entry.removed_at:
            events.append(DigitalTwinTimelineEvent(occurred_at=entry.removed_at, event_type="COMPONENT_REMOVED", summary=f"Removed from {entry.asset_registration or entry.asset_id}.", source_type="ComponentInstallation", source_id=entry.installation_id))

    diagnostics = hums_service.list_component_diagnostics(db, organization_id=organization_id, component_id=component_id)
    for d in diagnostics[:TIMELINE_PER_SOURCE_LIMIT]:
        events.append(DigitalTwinTimelineEvent(occurred_at=d.detected_at, event_type="DIAGNOSTIC_CANDIDATE_GENERATED", summary=f"{d.fault_name} ({d.status}).", source_type="HUMSDiagnosticCandidate", source_id=d.id))

    events.sort(key=lambda e: e.occurred_at, reverse=True)
    return events[:TIMELINE_TOTAL_LIMIT]


def check_asset_consistency(db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID) -> list[DigitalTwinConsistencyWarning]:
    """Detects data-integrity issues rather than silently ignoring them
    (H6 spec section 41). Returns warnings; never auto-corrects.
    """
    warnings: list[DigitalTwinConsistencyWarning] = []

    components = asset_service.get_asset_components(db, organization_id=organization_id, asset_id=asset_id)
    component_ids = {c.id for c in components}

    sensors = list(db.execute(select(HUMSSensor).where(HUMSSensor.organization_id == organization_id, HUMSSensor.asset_id == asset_id)).scalars().all())
    for sensor in sensors:
        if sensor.component_id and sensor.component_id not in component_ids:
            warnings.append(
                DigitalTwinConsistencyWarning(
                    check="SENSOR_COMPONENT_REFERENCE", severity="WARNING",
                    message=f"Sensor {sensor.sensor_code} references component {sensor.component_id}, which is not currently listed on this asset.",
                    entity_type="HUMSSensor", entity_id=sensor.id,
                )
            )

    for component in components:
        open_installations = list(
            db.execute(
                select(ComponentInstallation).where(
                    ComponentInstallation.organization_id == organization_id,
                    ComponentInstallation.component_id == component.id,
                    ComponentInstallation.removed_at.is_(None),
                )
            ).scalars().all()
        )
        if len(open_installations) > 1:
            warnings.append(
                DigitalTwinConsistencyWarning(
                    check="DUPLICATE_OPEN_INSTALLATION", severity="ERROR",
                    message=f"Component {component.name} ({component.id}) has {len(open_installations)} simultaneously open installation records.",
                    entity_type="Component", entity_id=component.id,
                )
            )
        elif open_installations and open_installations[0].asset_id != asset_id:
            warnings.append(
                DigitalTwinConsistencyWarning(
                    check="INSTALLATION_ASSET_MISMATCH", severity="WARNING",
                    message=f"Component {component.name} is listed on this asset but its open installation record points to a different asset.",
                    entity_type="Component", entity_id=component.id,
                )
            )

    return warnings


__all__ = [
    "get_asset_snapshot",
    "get_asset_component_tree",
    "get_component_snapshot",
    "get_component_genealogy",
    "get_asset_timeline",
    "get_component_timeline",
    "check_asset_consistency",
]

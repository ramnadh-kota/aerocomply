"""H6: Digital Asset & Component Twin — response schemas.

The twin is a READ-ONLY aggregation over existing authoritative data. Every
field here is populated by calling an existing domain service
(asset_service, hums_service, readiness_intelligence_service, ...) — none
of these schemas back a new table of authoritative state. See
docs/DIGITAL_TWIN_ARCHITECTURE.md for the full source-of-truth policy.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

from app.schemas.asset import AssetComponentResponse, AssetConfigurationResponse, AssetUtilizationResponse
from app.schemas.hums import HUMSAssetHealthIntelligence, HUMSDiagnosticCandidateResponse, HUMSPrognosticRecordResponse

DataAvailability = Literal["AVAILABLE", "DATA_UNAVAILABLE"]


class DigitalTwinIdentity(BaseModel):
    """L1 — maps the twin to exactly one authoritative Asset row."""

    asset_id: uuid.UUID
    asset_type: str
    registration: str | None
    serial_number: str | None
    manufacturer: str | None
    model: str | None
    status: str


class DigitalTwinMaintenanceState(BaseModel):
    availability: DataAvailability
    open_work_order_count: int = 0
    open_finding_count: int = 0
    last_accomplishment_at: datetime | None = None


class DigitalTwinComplianceState(BaseModel):
    availability: DataAvailability
    assessment_count: int = 0
    summary: dict[str, Any] = {}


class DigitalTwinReadinessState(BaseModel):
    availability: DataAvailability
    readiness_state: str | None = None
    blocker_count: int = 0
    blockers: list[str] = []


class DigitalTwinAssetSnapshot(BaseModel):
    """L1-L13 combined — the single "current digital state of this asset"
    view (H6 spec section 29). Every sub-section states its own
    `availability`/`status` so a caller never has to guess whether a
    missing field means "healthy" or "we couldn't compute it".
    """

    identity: DigitalTwinIdentity
    configuration: AssetConfigurationResponse
    usage: AssetUtilizationResponse
    health: HUMSAssetHealthIntelligence | None  # None only if HUMS is not configured for this asset
    diagnostics: list[HUMSDiagnosticCandidateResponse]
    prognostics: list[HUMSPrognosticRecordResponse]
    maintenance: DigitalTwinMaintenanceState
    compliance: DigitalTwinComplianceState
    readiness: DigitalTwinReadinessState
    generated_at: datetime


class DigitalTwinComponentNode(BaseModel):
    """L3 — Asset -> Component. Flat, one level: this codebase's Component
    model has no parent_component_id, so a deeper System/Subsystem/
    Component hierarchy is NOT representable — see
    docs/DIGITAL_TWIN_ARCHITECTURE.md for why this is a documented scope
    boundary, not an oversight (same reasoning H4's fault-isolation
    documentation already established for the same underlying limitation).
    """

    component: AssetComponentResponse
    health_state: str | None = None
    diagnostic_count: int = 0
    active_prognostic_status: str | None = None


class DigitalTwinComponentSnapshot(BaseModel):
    """Component-level twin — identity, installation lineage, usage-since-
    install, and the same H3/H4/H5 state as the asset-level snapshot,
    scoped to this component's sensors."""

    component: AssetComponentResponse
    current_asset_id: uuid.UUID | None
    installed_at: datetime | None
    genealogy_entry_count: int
    health: dict | None  # component-scoped health intelligence (same shape as HUMSComponentHealthIntelligence)
    diagnostics: list[HUMSDiagnosticCandidateResponse]
    prognostics: list[HUMSPrognosticRecordResponse]
    generated_at: datetime


class DigitalTwinGenealogyEntry(BaseModel):
    """One installation span in a component's lifecycle — 'where has this
    component been?' (H6 spec section 17)."""

    installation_id: uuid.UUID
    asset_id: uuid.UUID
    asset_registration: str | None
    installed_at: datetime
    removed_at: datetime | None
    is_current: bool


class DigitalTwinTimelineEvent(BaseModel):
    """One entry in the unified lifecycle timeline (H6 spec section 25).
    `source_type`/`source_id` let a UI/AI navigate back to the actual
    authoritative record — the timeline itself stores nothing new.
    """

    occurred_at: datetime
    event_type: str
    summary: str
    source_type: str
    source_id: uuid.UUID


class DigitalTwinConsistencyWarning(BaseModel):
    """One detected data-integrity issue (H6 spec section 41) — a warning
    surfaced to a human, never silently auto-corrected."""

    check: str
    severity: Literal["INFO", "WARNING", "ERROR"]
    message: str
    entity_type: str
    entity_id: uuid.UUID


__all__ = [
    "DigitalTwinIdentity",
    "DigitalTwinMaintenanceState",
    "DigitalTwinComplianceState",
    "DigitalTwinReadinessState",
    "DigitalTwinAssetSnapshot",
    "DigitalTwinComponentNode",
    "DigitalTwinComponentSnapshot",
    "DigitalTwinGenealogyEntry",
    "DigitalTwinTimelineEvent",
    "DigitalTwinConsistencyWarning",
]

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ControlCenterAircraftRow(BaseModel):
    aircraft_id: uuid.UUID
    registration: str
    operational_status: str  # OPERATIONAL | UNDER_MAINTENANCE | AOG
    open_work_orders: int
    open_deferred_items: int
    open_part_shortages: int
    active_aog_event_id: uuid.UUID | None = None


class ControlCenterFleetHealth(BaseModel):
    total_assets: int = 0
    ready_count: int = 0
    restricted_count: int = 0
    maintenance_due_count: int = 0
    grounded_count: int = 0
    available_count: int = 0
    in_mission_count: int = 0
    unknown_count: int = 0
    asset_class_counts: dict[str, int] = {}


class ControlCenterOperationalActivity(BaseModel):
    flights_today: int = 0
    flights_this_week: int = 0
    total_flight_hours: float = 0.0
    total_cycles: int = 0
    total_flights: int = 0
    active_missions: int = 0


class ControlCenterAttentionItem(BaseModel):
    id: str
    asset_id: uuid.UUID | None = None
    registration: str | None = None
    asset_type: str | None = None
    priority: str  # CRITICAL | HIGH | MEDIUM | LOW
    category: str  # INSPECTION | MAINTENANCE | COMPLIANCE | FINDING | MATERIAL | BATTERY
    title: str
    reason: str
    blocking_condition: str | None = None
    recommended_action: str | None = None
    link_href: str | None = None


class ControlCenterDailyBrief(BaseModel):
    date_str: str
    total_assets: int = 0
    ready_assets: int = 0
    attention_required_count: int = 0
    restricted_assets: int = 0
    maintenance_due_count: int = 0
    pending_inspections_count: int = 0
    open_findings_count: int = 0
    summary_headline: str
    key_bullet_points: list[str] = []
    generated_at: datetime


class ControlCenterFleetOperationRow(BaseModel):
    asset_id: uuid.UUID
    registration: str | None = None
    asset_type: str
    manufacturer: str | None = None
    model: str | None = None
    serial_number: str | None = None
    lifecycle_status: str
    operational_state: str
    readiness_state: str
    risk_level: str
    priority_level: str
    total_flight_hours: float = 0.0
    total_cycles: int = 0
    last_flight_at: datetime | None = None
    open_work_orders: int = 0
    open_findings: int = 0
    active_blocker_count: int = 0
    next_action: str | None = None


class OperationalTimelineEvent(BaseModel):
    event_id: str
    event_type: str
    occurred_at: datetime
    title: str
    description: str | None = None
    actor: str | None = None
    entity_type: str
    entity_id: str
    asset_id: uuid.UUID | None = None
    asset_registration: str | None = None
    asset_type: str | None = None
    metadata: dict[str, Any] = {}


class ControlCenterSummary(BaseModel):
    total_aircraft: int
    operational: int
    under_maintenance: int
    aog: int
    open_work_orders_total: int
    open_deferred_items_total: int
    open_part_shortages_total: int
    # Fleet-wide distribution across ALL assets (not just Aircraft) using
    # asset_service.compute_operational_state's 8-value vocabulary --
    # additive fields, existing consumers of the fields above are unaffected.
    total_assets: int = 0
    operational_states: dict[str, int] = {}
    fleet_health: ControlCenterFleetHealth | None = None
    operational_activity: ControlCenterOperationalActivity | None = None
    attention_items: list[ControlCenterAttentionItem] = []
    daily_brief: ControlCenterDailyBrief | None = None
    readiness_distribution: dict[str, int] = {}
    compliance_distribution: dict[str, int] = {}

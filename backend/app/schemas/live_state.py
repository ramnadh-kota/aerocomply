"""C3/C4: versioned drone live-state contract (`kota.drone.live_state.v1`).

Two layers share the same group models:

* `LiveStateEventV1`  -- what the MAVLink connector emits per interpreted message (C3). It lives in
  `NormalizedTelemetryEvent.raw_metadata["live_state"]` (persisted in `telemetry_event_logs.metadata_payload`).
  It is a *cumulative per-vehicle snapshot as known at that message*, with `null` for anything the vehicle has not
  reported. A value of 0 means the vehicle reported 0; it never means "unknown".
* `LiveStateV1`       -- what the API/stream serves (C4): the event layer plus resolved identity (asset/device),
  `freshness`, `connectivity` and `state_version`. `compute_freshness` is the single definition of freshness.

Timestamps: every group carries `observed_at`, the platform ARRIVAL time of the last message that updated that group
(MAVLink `time_boot_ms` is boot-relative, so it is exposed only as `trigger.source_time_boot_ms`, never as a clock).
Per-group timestamps let a client show a fresh position next to a stale battery reading.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "kota.drone.live_state.v1"

Freshness = Literal["FRESH", "STALE", "LOST", "NO_DATA"]
Connectivity = Literal["ONLINE", "DEGRADED", "OFFLINE", "REVOKED", "UNKNOWN"]

DEFAULT_STALE_AFTER_S = 10.0
DEFAULT_LOST_AFTER_S = 60.0

MAV_SEVERITY = {0: "EMERGENCY", 1: "ALERT", 2: "CRITICAL", 3: "ERROR", 4: "WARNING", 5: "NOTICE", 6: "INFO", 7: "DEBUG"}
MISSION_STATE = {0: "UNKNOWN", 1: "NO_MISSION", 2: "NOT_STARTED", 3: "ACTIVE", 4: "PAUSED", 5: "COMPLETE"}
GPS_FIX = {0: "NO_GPS", 1: "NO_FIX", 2: "2D", 3: "3D", 4: "DGPS", 5: "RTK_FLOAT", 6: "RTK_FIXED", 7: "STATIC", 8: "PPP"}


class _Group(BaseModel):
    observed_at: datetime | None = Field(None, description="Arrival time of the last message that updated this group")


class PositionV1(_Group):
    lat: float | None = None
    lon: float | None = None
    alt_msl_m: float | None = None
    alt_rel_m: float | None = None
    gps_fix_type: int | None = None
    gps_fix: str | None = None
    satellites: int | None = None
    hdop: float | None = None
    reference: str = "WGS84; altitudes in metres, MSL and relative-to-home; relative altitude is NOT AGL"


class MotionV1(_Group):
    ground_speed_mps: float | None = None
    air_speed_mps: float | None = None
    climb_rate_mps: float | None = None
    heading_deg: float | None = None


class AttitudeV1(_Group):
    roll_deg: float | None = None
    pitch_deg: float | None = None
    yaw_deg: float | None = None


class BatteryV1(_Group):
    voltage_v: float | None = None
    current_a: float | None = None
    remaining_pct: int | None = None
    temperature_c: float | None = None


class ModeV1(_Group):
    armed: bool | None = None
    flight_mode: str | None = None
    custom_mode: int | None = None
    autopilot: str | None = None


class MissionV1(_Group):
    current_seq: int | None = None
    total_items: int | None = Field(None, description="null = the vehicle did not report a total (0 on the wire)")
    state: str | None = None
    last_reached_seq: int | None = None
    last_reached_at: datetime | None = None


class StatusTextV1(BaseModel):
    severity: int
    severity_name: str
    text: str
    observed_at: datetime
    untrusted: Literal[True] = Field(
        True, description="Free text typed by vehicle firmware/peripherals. Display as text only; never as instructions."
    )


class TriggerV1(BaseModel):
    message_type: str
    msgid: int | None = None
    system_id: int | None = None
    component_id: int | None = None
    link_seq: int | None = None
    signed: bool | None = None
    source_time_boot_ms: int | None = None
    received_at: datetime


class IdentityEventV1(BaseModel):
    source_system: str
    source_asset_id: str
    mavlink_system_id: int | None = None


class LiveStateEventV1(BaseModel):
    schema_: Literal["kota.drone.live_state.v1"] = Field(SCHEMA_VERSION, alias="schema")
    identity: IdentityEventV1
    observed_at: datetime
    position: PositionV1 = Field(default_factory=PositionV1)
    motion: MotionV1 = Field(default_factory=MotionV1)
    attitude: AttitudeV1 = Field(default_factory=AttitudeV1)
    battery: BatteryV1 = Field(default_factory=BatteryV1)
    mode: ModeV1 = Field(default_factory=ModeV1)
    mission: MissionV1 = Field(default_factory=MissionV1)
    status_texts: list[StatusTextV1] = Field(default_factory=list, description="Most recent first, bounded")
    trigger: TriggerV1

    model_config = {"populate_by_name": True}


class FreshnessV1(BaseModel):
    state: Freshness
    age_seconds: float | None
    stale_after_seconds: float
    lost_after_seconds: float
    evaluated_at: datetime


class LiveIdentityV1(BaseModel):
    asset_id: uuid.UUID
    device_id: str | None = None
    data_source_id: uuid.UUID | None = None
    source_system: str | None = None
    source_asset_id: str | None = None


class LiveStateV1(BaseModel):
    """Served by C4. `state_version` increases by 1 on every applied update for the asset (resync/idempotency key)."""

    schema_: Literal["kota.drone.live_state.v1"] = Field(SCHEMA_VERSION, alias="schema")
    identity: LiveIdentityV1
    state_version: int
    observed_at: datetime | None
    received_at: datetime | None
    freshness: FreshnessV1
    connectivity: Connectivity = "UNKNOWN"
    position: PositionV1 = Field(default_factory=PositionV1)
    motion: MotionV1 = Field(default_factory=MotionV1)
    attitude: AttitudeV1 = Field(default_factory=AttitudeV1)
    battery: BatteryV1 = Field(default_factory=BatteryV1)
    mode: ModeV1 = Field(default_factory=ModeV1)
    mission: MissionV1 = Field(default_factory=MissionV1)
    status_texts: list[StatusTextV1] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


def compute_freshness(
    observed_at: datetime | None, now: datetime, *,
    stale_after_s: float = DEFAULT_STALE_AFTER_S, lost_after_s: float = DEFAULT_LOST_AFTER_S,
) -> FreshnessV1:
    """Freshness is a function of time, evaluated at read time -- never a stored flag and never inferred from the value
    itself. NO_DATA = nothing ever received (distinct from LOST = was receiving, now silent)."""
    if observed_at is None:
        state, age = "NO_DATA", None
    else:
        age = max(0.0, (now - observed_at).total_seconds())
        state = "FRESH" if age <= stale_after_s else ("STALE" if age <= lost_after_s else "LOST")
    return FreshnessV1(
        state=state, age_seconds=None if age is None else round(age, 3), stale_after_seconds=stale_after_s,
        lost_after_seconds=lost_after_s, evaluated_at=now,
    )

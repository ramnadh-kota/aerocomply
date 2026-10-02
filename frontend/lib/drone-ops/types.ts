// Drone Operations — shared TypeScript interfaces.
//
// These are the PROPOSED shared contracts between frontend and Claude's backend.
// All fields are marked as reconciled against existing schemas where verified;
// new fields are proposed and must be confirmed with Claude before backend integration.
//
// Field alignment:
//   - asset_id → matches DroneResponse.id (lib/api/drones.ts)
//   - organization_id → matches DroneResponse.organization_id
//   - BackendMission.status → PLANNED | AUTHORIZED | IN_PROGRESS | COMPLETED | CANCELLED
//     (lib/api/missions.ts). We add CLOSED to the mission state here as a UI-only terminal state.

// ─────────────────────────────────────────────────────────────────────────────
// Live Drone State (per drone, per telemetry tick)
// Proposed contract for GET /drones/{id}/live-state and WS/SSE fleet snapshots.
// ─────────────────────────────────────────────────────────────────────────────

export type ConnectionStatus = "CONNECTED" | "DEGRADED" | "DISCONNECTED" | "UNKNOWN";
export type FlightMode =
  | "MANUAL"
  | "STABILIZE"
  | "LOITER"
  | "AUTO"
  | "RTL"
  | "LAND"
  | "GUIDED"
  | "HOLD"
  | "TAKEOFF"
  | "IDLE"
  | "UNKNOWN";

export type FreshnessStatus = "FRESH" | "STALE" | "VERY_STALE" | "UNKNOWN";

export interface DroneState {
  /** Maps to DroneResponse.organization_id */
  organization_id: string;
  /** Maps to DroneResponse.id (asset_id) */
  asset_id: string;
  /** Maps to DroneResponse.registration */
  registration: string;
  /** Optional: hardware device/MAVLink system ID */
  device_id: string | null;

  // Geospatial position
  latitude: number | null;
  longitude: number | null;
  altitude: number | null; // metres AGL
  heading: number | null; // degrees 0–359
  speed: number | null; // m/s ground speed

  // Power
  battery_percentage: number | null; // 0–100
  battery_voltage: number | null; // volts

  // Operational state
  flight_mode: FlightMode;
  connection_status: ConnectionStatus;

  // Timestamps
  source_timestamp: string | null; // ISO-8601: when the drone produced this packet
  received_timestamp: string | null; // ISO-8601: when backend received/processed
  freshness_status: FreshnessStatus;
}

// ─────────────────────────────────────────────────────────────────────────────
// Mission State (per mission)
// Proposed contract for operational mission progress panels.
// Extends BackendMission (lib/api/missions.ts) with live-derived fields.
// ─────────────────────────────────────────────────────────────────────────────

export type MissionStatus =
  | "PLANNED"
  | "AUTHORIZED"
  | "IN_PROGRESS"
  | "COMPLETED"
  | "CANCELLED"
  | "CLOSED"; // UI-only terminal alias

export interface MissionState {
  mission_id: string;
  asset_id: string;
  registration: string | null;
  pilot_name: string | null;
  mission_status: MissionStatus;
  purpose: string;
  operating_area: string | null;

  // Progress tracking (proposed — confirm with Claude)
  current_waypoint: number | null;
  total_waypoints: number | null;
  progress: number | null; // 0.0–1.0

  // Timing
  planned_start: string | null;
  planned_end: string | null;
  estimated_completion: string | null;
  updated_at: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Operational Events / Alerts
// Proposed contract for GET /drones/operational-events
// ─────────────────────────────────────────────────────────────────────────────

export type EventSeverity = "CRITICAL" | "WARNING" | "INFO" | "DEBUG";
export type EventType =
  | "LOW_BATTERY"
  | "SIGNAL_LOST"
  | "GEOFENCE_BREACH"
  | "FLIGHT_MODE_CHANGE"
  | "MISSION_STARTED"
  | "MISSION_COMPLETED"
  | "MISSION_ABORTED"
  | "MAINTENANCE_DUE"
  | "SENSOR_FAULT"
  | "RTL_TRIGGERED"
  | "LANDING_DETECTED"
  | "TAKEOFF_DETECTED"
  | "TELEMETRY_STALE"
  | "GENERIC";

export interface OperationalEvent {
  event_id: string;
  organization_id: string;
  asset_id: string | null;
  registration: string | null;
  event_type: EventType;
  severity: EventSeverity;
  description: string;
  event_timestamp: string; // ISO-8601
  acknowledgment_status: "ACKNOWLEDGED" | "UNACKNOWLEDGED" | "AUTO_CLEARED";
  evidence_reference: string | null; // links to backend evidence record
}

// ─────────────────────────────────────────────────────────────────────────────
// Fleet Snapshot — aggregate of all drone states for the org
// ─────────────────────────────────────────────────────────────────────────────

export interface FleetSnapshot {
  organization_id: string;
  snapshot_at: string;
  drones: DroneState[];
  active_missions: MissionState[];
  recent_events: OperationalEvent[];
}

// ─────────────────────────────────────────────────────────────────────────────
// UI-derived summary types (computed in the frontend, never sent to backend)
// ─────────────────────────────────────────────────────────────────────────────

export interface FleetKPIs {
  total: number;
  airborne: number;
  grounded: number;
  disconnected: number;
  low_battery_count: number;
  active_missions: number;
  unacknowledged_alerts: number;
}

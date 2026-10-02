// Drone Operations — A1 simulated mock state.
//
// IMPORTANT: This file produces SIMULATED data only.
// It is exclusively used during A1 (dashboard shell) before Claude's live API
// is available. Every consumer of this module must display the SimDataBanner.
// Remove individual drone simulations as real telemetry endpoints are connected.
//
// Simulation philosophy:
// - Data changes on every tick via a deterministic oscillator (no random seeds
//   per render to keep React stable).
// - Positions are anchored near a realistic coordinate (Bangalore tech corridor
//   used as demo region; swap to any coords before production).
// - Battery drains at ~0.3% per 10s tick for drones in IN_PROGRESS missions.
// - Alerts fire probabilistically on a low-frequency schedule.

import type {
  DroneState,
  MissionState,
  OperationalEvent,
  FleetSnapshot,
  FleetKPIs,
} from "./types";
import { DEMO_DRONES } from "@/lib/demo/demoDrones";
import { DEMO_ORG_ID } from "@/lib/auth/SessionContext";

// ─────────────────────────────────────────────────────────────────────────────
// Static simulated positions (anchored around Bangalore / electronic city area)
// Replace with real GPS coordinates from MAVLink once backend is connected.
// ─────────────────────────────────────────────────────────────────────────────

const BASE_LAT = 12.9716;
const BASE_LNG = 77.5946;

interface DroneSimSeed {
  lat: number;
  lng: number;
  alt: number;
  heading: number;
  speed: number;
  battery: number;
  mode: DroneState["flight_mode"];
  connection: DroneState["connection_status"];
  missionId: string | null;
}

const DRONE_SEEDS: Record<string, DroneSimSeed> = {
  "drn-kota-001": { lat: BASE_LAT + 0.01,  lng: BASE_LNG + 0.02,  alt: 85,  heading: 45,  speed: 12, battery: 78, mode: "AUTO",      connection: "CONNECTED",    missionId: "msn-001" },
  "drn-kota-002": { lat: BASE_LAT + 0.025, lng: BASE_LNG - 0.015, alt: 120, heading: 190, speed: 8,  battery: 91, mode: "LOITER",    connection: "CONNECTED",    missionId: "msn-002" },
  "drn-kota-003": { lat: BASE_LAT - 0.012, lng: BASE_LNG + 0.031, alt: 0,   heading: 270, speed: 0,  battery: 55, mode: "IDLE",      connection: "CONNECTED",    missionId: null       },
  "drn-kota-004": { lat: BASE_LAT + 0.018, lng: BASE_LNG + 0.008, alt: 60,  heading: 310, speed: 15, battery: 42, mode: "GUIDED",    connection: "DEGRADED",     missionId: "msn-003" },
  "drn-kota-005": { lat: BASE_LAT - 0.005, lng: BASE_LNG - 0.022, alt: 0,   heading: 0,   speed: 0,  battery: 100,mode: "IDLE",     connection: "DISCONNECTED", missionId: null       },
  "drn-kota-006": { lat: BASE_LAT + 0.033, lng: BASE_LNG + 0.041, alt: 40,  heading: 90,  speed: 6,  battery: 23, mode: "RTL",      connection: "CONNECTED",    missionId: "msn-004" },
};

// ─────────────────────────────────────────────────────────────────────────────
// Tick-based oscillation (deterministic, stable across renders)
// ─────────────────────────────────────────────────────────────────────────────

function oscillate(base: number, amplitude: number, tick: number, phase: number): number {
  return base + amplitude * Math.sin((tick / 20 + phase) * Math.PI * 2);
}

export function buildDroneState(droneId: string, tick: number): DroneState {
  const drone = DEMO_DRONES.find((d) => d.id === droneId);
  const seed = DRONE_SEEDS[droneId];

  if (!drone || !seed) {
    return {
      organization_id: DEMO_ORG_ID,
      asset_id: droneId,
      registration: droneId,
      device_id: null,
      latitude: null,
      longitude: null,
      altitude: null,
      heading: null,
      speed: null,
      battery_percentage: null,
      battery_voltage: null,
      flight_mode: "UNKNOWN",
      connection_status: "UNKNOWN",
      source_timestamp: new Date().toISOString(),
      received_timestamp: new Date().toISOString(),
      freshness_status: "UNKNOWN",
    };
  }

  const phaseOffset = DEMO_DRONES.findIndex((d) => d.id === droneId) * 0.15;
  const isAirborne = seed.alt > 0 && seed.connection !== "DISCONNECTED";

  return {
    organization_id: DEMO_ORG_ID,
    asset_id: drone.id,
    registration: drone.registration ?? droneId,
    device_id: `mav-${droneId.split("-").pop()}`,

    latitude: isAirborne
      ? oscillate(seed.lat, 0.0008, tick, phaseOffset)
      : seed.lat,
    longitude: isAirborne
      ? oscillate(seed.lng, 0.0012, tick, phaseOffset + 0.25)
      : seed.lng,
    altitude: isAirborne
      ? Math.max(0, oscillate(seed.alt, 5, tick, phaseOffset + 0.5))
      : 0,
    heading: isAirborne
      ? ((seed.heading + tick * 0.4 * phaseOffset) % 360 + 360) % 360
      : seed.heading,
    speed: isAirborne
      ? Math.max(0, oscillate(seed.speed, 2, tick, phaseOffset + 0.1))
      : 0,

    battery_percentage: Math.max(
      0,
      seed.battery - (isAirborne ? tick * 0.03 : 0)
    ),
    battery_voltage: seed.battery > 0 ? 22.2 * (seed.battery / 100) + 0.5 : null,

    flight_mode: seed.mode,
    connection_status: seed.connection,

    source_timestamp: new Date(Date.now() - 800).toISOString(),
    received_timestamp: new Date().toISOString(),
    freshness_status:
      seed.connection === "DISCONNECTED"
        ? "VERY_STALE"
        : seed.connection === "DEGRADED"
        ? "STALE"
        : "FRESH",
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Simulated missions
// ─────────────────────────────────────────────────────────────────────────────

export const SIM_MISSIONS: MissionState[] = [
  {
    mission_id: "msn-001",
    asset_id: "drn-kota-001",
    registration: "KOTA-D001",
    pilot_name: "Cmdr. Reyes",
    mission_status: "IN_PROGRESS",
    purpose: "Infrastructure Corridor Survey — Sector 4B",
    operating_area: "Bangalore Tech Corridor, Zone 4B",
    current_waypoint: 7,
    total_waypoints: 12,
    progress: 0.58,
    planned_start: new Date(Date.now() - 28 * 60000).toISOString(),
    planned_end: new Date(Date.now() + 18 * 60000).toISOString(),
    estimated_completion: new Date(Date.now() + 20 * 60000).toISOString(),
    updated_at: new Date(Date.now() - 90000).toISOString(),
  },
  {
    mission_id: "msn-002",
    asset_id: "drn-kota-002",
    registration: "KOTA-D002",
    pilot_name: "Flt. Lt. Nair",
    mission_status: "IN_PROGRESS",
    purpose: "Site Photogrammetry — Whitefield Expansion Zone",
    operating_area: "Whitefield, Bangalore",
    current_waypoint: 3,
    total_waypoints: 8,
    progress: 0.35,
    planned_start: new Date(Date.now() - 12 * 60000).toISOString(),
    planned_end: new Date(Date.now() + 35 * 60000).toISOString(),
    estimated_completion: new Date(Date.now() + 38 * 60000).toISOString(),
    updated_at: new Date(Date.now() - 45000).toISOString(),
  },
  {
    mission_id: "msn-003",
    asset_id: "drn-kota-004",
    registration: "KOTA-D004",
    pilot_name: "Capt. Sharma",
    mission_status: "AUTHORIZED",
    purpose: "Emergency Pipeline Inspection — Sector 7",
    operating_area: "Electronic City Phase 2",
    current_waypoint: null,
    total_waypoints: 6,
    progress: 0,
    planned_start: new Date(Date.now() + 5 * 60000).toISOString(),
    planned_end: new Date(Date.now() + 45 * 60000).toISOString(),
    estimated_completion: null,
    updated_at: new Date(Date.now() - 15000).toISOString(),
  },
  {
    mission_id: "msn-004",
    asset_id: "drn-kota-006",
    registration: "KOTA-D006",
    pilot_name: "Auto-RTL",
    mission_status: "IN_PROGRESS",
    purpose: "Return-to-Launch (Low Battery Trigger)",
    operating_area: "Launch Point Alpha",
    current_waypoint: 1,
    total_waypoints: 1,
    progress: 0.7,
    planned_start: new Date(Date.now() - 5 * 60000).toISOString(),
    planned_end: new Date(Date.now() + 3 * 60000).toISOString(),
    estimated_completion: new Date(Date.now() + 2 * 60000).toISOString(),
    updated_at: new Date(Date.now() - 10000).toISOString(),
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// Simulated operational alerts
// ─────────────────────────────────────────────────────────────────────────────

export const SIM_EVENTS: OperationalEvent[] = [
  {
    event_id: "evt-001",
    organization_id: DEMO_ORG_ID,
    asset_id: "drn-kota-006",
    registration: "KOTA-D006",
    event_type: "LOW_BATTERY",
    severity: "CRITICAL",
    description: "KOTA-D006 battery at 23% — Auto-RTL triggered",
    event_timestamp: new Date(Date.now() - 4 * 60000).toISOString(),
    acknowledgment_status: "UNACKNOWLEDGED",
    evidence_reference: null,
  },
  {
    event_id: "evt-002",
    organization_id: DEMO_ORG_ID,
    asset_id: "drn-kota-004",
    registration: "KOTA-D004",
    event_type: "SIGNAL_LOST",
    severity: "WARNING",
    description: "KOTA-D004 link quality degraded — operating at 62% RSSI",
    event_timestamp: new Date(Date.now() - 9 * 60000).toISOString(),
    acknowledgment_status: "UNACKNOWLEDGED",
    evidence_reference: null,
  },
  {
    event_id: "evt-003",
    organization_id: DEMO_ORG_ID,
    asset_id: "drn-kota-001",
    registration: "KOTA-D001",
    event_type: "MISSION_STARTED",
    severity: "INFO",
    description: "KOTA-D001 mission MSN-001 started — Sector 4B Survey",
    event_timestamp: new Date(Date.now() - 28 * 60000).toISOString(),
    acknowledgment_status: "AUTO_CLEARED",
    evidence_reference: null,
  },
  {
    event_id: "evt-004",
    organization_id: DEMO_ORG_ID,
    asset_id: "drn-kota-005",
    registration: "KOTA-D005",
    event_type: "TELEMETRY_STALE",
    severity: "WARNING",
    description: "KOTA-D005 telemetry link lost — last contact 18m ago",
    event_timestamp: new Date(Date.now() - 18 * 60000).toISOString(),
    acknowledgment_status: "UNACKNOWLEDGED",
    evidence_reference: null,
  },
  {
    event_id: "evt-005",
    organization_id: DEMO_ORG_ID,
    asset_id: "drn-kota-003",
    registration: "KOTA-D003",
    event_type: "MAINTENANCE_DUE",
    severity: "INFO",
    description: "KOTA-D003 motor inspection due in 3 flight hours",
    event_timestamp: new Date(Date.now() - 2 * 60 * 60000).toISOString(),
    acknowledgment_status: "UNACKNOWLEDGED",
    evidence_reference: null,
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// Full fleet snapshot builder
// ─────────────────────────────────────────────────────────────────────────────

export function buildFleetSnapshot(tick: number): FleetSnapshot {
  const drones = DEMO_DRONES.map((d) => buildDroneState(d.id, tick));
  return {
    organization_id: DEMO_ORG_ID,
    snapshot_at: new Date().toISOString(),
    drones,
    active_missions: SIM_MISSIONS,
    recent_events: SIM_EVENTS,
  };
}

export function computeFleetKPIs(snapshot: FleetSnapshot): FleetKPIs {
  const { drones, active_missions, recent_events } = snapshot;
  return {
    total: drones.length,
    airborne: drones.filter(
      (d) => (d.altitude ?? 0) > 0 && d.connection_status !== "DISCONNECTED"
    ).length,
    grounded: drones.filter(
      (d) => (d.altitude ?? 0) === 0 && d.connection_status !== "DISCONNECTED"
    ).length,
    disconnected: drones.filter((d) => d.connection_status === "DISCONNECTED")
      .length,
    low_battery_count: drones.filter(
      (d) => d.battery_percentage !== null && d.battery_percentage < 30
    ).length,
    active_missions: active_missions.filter(
      (m) => m.mission_status === "IN_PROGRESS"
    ).length,
    unacknowledged_alerts: recent_events.filter(
      (e) => e.acknowledgment_status === "UNACKNOWLEDGED"
    ).length,
  };
}

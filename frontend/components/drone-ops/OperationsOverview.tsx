"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import { DroneKPIBar } from "./DroneKPIBar";
import { FleetStatusCards } from "./FleetStatusCards";
import { FleetMap } from "./FleetMap";
import { AlertsPanel } from "./AlertsPanel";
import { MissionStatusPanel } from "./MissionStatusPanel";
import { BatteryOverviewBar } from "./BatteryOverviewBar";
import { FlightEventLog } from "./FlightEventLog";
import { DroneDetailPanel } from "./DroneDetailPanel";
import { liveApi, type LiveStateV1 } from "@/lib/api/live";
import { dronesApi, type DroneResponse } from "@/lib/api/drones";
import { missionsApi, type BackendMission } from "@/lib/api/missions";
import { proactiveApi, type BackendProactiveAlert } from "@/lib/api/proactive";
import { useSession } from "@/lib/auth/SessionContext";

import {
  buildFleetSnapshot,
  computeFleetKPIs,
  SIM_EVENTS,
  SIM_MISSIONS,
} from "@/lib/drone-ops/mockDroneState";
import type { FleetSnapshot, FleetKPIs, OperationalEvent, DroneState, FreshnessStatus, ConnectionStatus, FlightMode } from "@/lib/drone-ops/types";

// ─────────────────────────────────────────────────────────────────────────────
// Tick-based live telemetry refresh (2-second interval mirrors real-time MAVLink rates).
// ─────────────────────────────────────────────────────────────────────────────
const TICK_INTERVAL_MS = 2000;

function nowUTC(): string {
  return new Date().toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    timeZoneName: "short",
  });
}

export function OperationsOverview() {
  const { accessToken } = useSession();
  const [tick, setTick] = useState(0);
  const [isSimulated, setIsSimulated] = useState(false);
  const [realDrones, setRealDrones] = useState<DroneResponse[]>([]);
  const [liveFleetStates, setLiveFleetStates] = useState<LiveStateV1[]>([]);
  const [realMissions, setRealMissions] = useState<BackendMission[]>([]);
  const [realAlerts, setRealAlerts] = useState<BackendProactiveAlert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedDroneId, setSelectedDroneId] = useState<string | null>(null);
  const [events, setEvents] = useState<OperationalEvent[]>(SIM_EVENTS);
  const [operationalTime, setOperationalTime] = useState(nowUTC());

  const loadData = useCallback(async () => {
    if (!accessToken) return;
    try {
      const [dronesData, missionsData, alertsData, liveData] = await Promise.all([
        dronesApi.listDrones(accessToken).catch(() => []),
        missionsApi.listMissions(accessToken, { status: "IN_PROGRESS" }).catch(() => ({ items: [], total: 0, limit: 10, offset: 0 })),
        proactiveApi.getAlerts(accessToken).catch(() => []),
        liveApi.getFleet(accessToken).catch(() => null),
      ]);
      setRealDrones(dronesData);
      setRealMissions(missionsData.items);
      setRealAlerts(alertsData);
      if (liveData?.drones) {
        setLiveFleetStates(liveData.drones);
      }
    } catch (err: any) {
      setError(err.message || "Failed to load operational data.");
    } finally {
      setLoading(false);
    }
  }, [accessToken]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Periodic polling for live telemetry
  useEffect(() => {
    const interval = setInterval(() => {
      setTick((t) => {
        const nextTick = t + 1;
        setOperationalTime(nowUTC());
        return nextTick;
      });
      if (accessToken && !isSimulated) {
        liveApi.getFleet(accessToken).then((res) => {
          if (res?.drones) {
            setLiveFleetStates(res.drones);
          }
        }).catch(() => {});
      }
    }, TICK_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [accessToken, isSimulated]);

  const snapshot = useMemo<FleetSnapshot>(() => {
    if (isSimulated) {
      return buildFleetSnapshot(tick);
    }
    
    // Live mode: map real drones and live backend state
    const droneMap = new Map(liveFleetStates.map((l) => [l.identity.asset_id, l]));

    const drones: DroneState[] = realDrones.map((rd) => {
      const live = droneMap.get(rd.id);
      const pos = live?.position;
      const batt = live?.battery;
      const mot = live?.motion;
      const mode = live?.mode;
      const fresh = live?.freshness?.state;

      let freshness_status: FreshnessStatus = "UNKNOWN";
      if (fresh === "FRESH") freshness_status = "FRESH";
      else if (fresh === "STALE") freshness_status = "STALE";
      else if (fresh === "LOST" || fresh === "NO_DATA") freshness_status = "VERY_STALE";

      let connection_status: ConnectionStatus = "DISCONNECTED";
      if (live?.connectivity === "ONLINE" || fresh === "FRESH") connection_status = "CONNECTED";
      else if (live?.connectivity === "DEGRADED" || fresh === "STALE") connection_status = "DEGRADED";

      return {
        organization_id: rd.organization_id,
        asset_id: rd.id,
        registration: rd.registration ?? rd.id,
        device_id: live?.identity?.device_id ?? null,
        latitude: pos?.lat ?? null,
        longitude: pos?.lon ?? null,
        altitude: pos?.alt_rel_m ?? pos?.alt_msl_m ?? null,
        heading: mot?.heading_deg ?? null,
        speed: mot?.ground_speed_mps ?? null,
        battery_percentage: batt?.remaining_pct ?? null,
        battery_voltage: batt?.voltage_v ?? null,
        flight_mode: (mode?.flight_mode as FlightMode) ?? (mode?.armed ? "GUIDED" : "IDLE"),
        connection_status,
        source_timestamp: live?.observed_at ?? null,
        received_timestamp: live?.received_at ?? null,
        freshness_status,
      };
    });

    return {
      organization_id: realDrones[0]?.organization_id ?? "unknown",
      snapshot_at: new Date().toISOString(),
      drones,
      active_missions: [],
      recent_events: [],
    };
  }, [isSimulated, tick, realDrones, liveFleetStates]);

  const kpis = useMemo<FleetKPIs>(() => computeFleetKPIs(snapshot), [snapshot]);


  const handleAcknowledge = useCallback((eventId: string) => {
    setEvents((prev) =>
      prev.map((e) =>
        e.event_id === eventId
          ? { ...e, acknowledgment_status: "ACKNOWLEDGED" as const }
          : e
      )
    );
  }, []);

  return (
    <div className="ac-drone-overview">
      {/* ── Top bar: KPIs + org identity ── */}
      <div style={{ display: "flex", flexDirection: "column" }}>
        <DroneKPIBar
          kpis={kpis}
          operationalTime={operationalTime}
          connectionLabel={isSimulated ? "SIMULATED NETWORK" : "LIVE MAVLINK"}
          isSimulated={isSimulated}
        />
        <div style={{ display: "flex", justifyContent: "flex-end", padding: "4px 16px", background: "var(--ac-bg-elevated)", borderBottom: "1px solid var(--ac-border-subtle)", fontSize: "11px", gap: "12px", alignItems: "center" }}>
          <span style={{ color: "var(--ac-text-muted)" }}>{loading ? "Syncing Fleet..." : "Fleet Synced"}</span>
          <label style={{ display: "flex", alignItems: "center", gap: "6px", cursor: "pointer" }}>
            <input 
              type="checkbox" 
              checked={isSimulated} 
              onChange={e => setIsSimulated(e.target.checked)} 
            />
            <span style={{ color: "var(--ac-text-secondary)", fontWeight: 600 }}>Simulation Mode</span>
          </label>
        </div>
      </div>


      {/* ── Main 3-column body ── */}
      <div className="ac-drone-overview-body">
        {/* LEFT: Fleet status cards */}
        <FleetStatusCards
          drones={snapshot.drones}
          selectedDroneId={selectedDroneId}
          onSelect={setSelectedDroneId}
        />

        {/* CENTER: Interactive map + bottom panels */}
        <div className="ac-drone-overview-center">
          {/* Map area */}
          <div className="ac-drone-map-area" style={{ position: "relative", overflow: "hidden" }}>
            <FleetMap 
              drones={snapshot.drones}
              selectedDroneId={selectedDroneId}
              onSelectDrone={setSelectedDroneId}
              isSimulated={isSimulated}
            />
          </div>

          {/* Bottom strip */}
          <div className="ac-drone-overview-bottom">
            <BatteryOverviewBar drones={snapshot.drones} />
            <FlightEventLog events={events} />
          </div>
        </div>

        {/* RIGHT: Alerts + missions OR Detail Panel */}
        {selectedDroneId ? (
          <div className="ac-drone-overview-right" style={{ width: "320px", flexShrink: 0 }}>
            {snapshot.drones.find((d: DroneState) => d.asset_id === selectedDroneId) && (
              <DroneDetailPanel 
                droneState={snapshot.drones.find((d: DroneState) => d.asset_id === selectedDroneId)!} 
                onClose={() => setSelectedDroneId(null)} 
              />
            )}
          </div>
        ) : (
          <div className="ac-drone-overview-right">
            <AlertsPanel events={isSimulated ? [] : realAlerts} />
            <MissionStatusPanel missions={isSimulated ? [] : realMissions} />
          </div>
        )}
      </div>
    </div>
  );
}

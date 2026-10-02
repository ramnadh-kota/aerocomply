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
import { dronesApi, type DroneResponse } from "@/lib/api/drones";
import { useSession } from "@/lib/auth/SessionContext";

import {
  buildFleetSnapshot,
  computeFleetKPIs,
  SIM_EVENTS,
  SIM_MISSIONS,
} from "@/lib/drone-ops/mockDroneState";
import type { FleetSnapshot, FleetKPIs, OperationalEvent, DroneState } from "@/lib/drone-ops/types";

// ─────────────────────────────────────────────────────────────────────────────
// Tick-based live simulation refresh (A1 — replace with WebSocket/SSE in A6).
// 4-second interval mirrors a realistic MAVLink heartbeat cycle.
// ─────────────────────────────────────────────────────────────────────────────
const TICK_INTERVAL_MS = 4000;

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
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedDroneId, setSelectedDroneId] = useState<string | null>(null);
  const [events, setEvents] = useState<OperationalEvent[]>(SIM_EVENTS);
  const [operationalTime, setOperationalTime] = useState(nowUTC());

  const loadDrones = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    setError(null);
    try {
      const data = await dronesApi.listDrones(accessToken);
      setRealDrones(data);
    } catch (err: any) {
      setError(err.message || "Failed to load fleet inventory.");
    } finally {
      setLoading(false);
    }
  }, [accessToken]);

  useEffect(() => {
    loadDrones();
  }, [loadDrones]);


  // Advance simulation tick
  useEffect(() => {
    const interval = setInterval(() => {
      setTick((t) => {
        const nextTick = t + 1;
        setOperationalTime(nowUTC());
        return nextTick;
      });
    }, TICK_INTERVAL_MS);
    return () => clearInterval(interval);
  }, []);

  const snapshot = useMemo<FleetSnapshot>(() => {
    if (isSimulated) {
      return buildFleetSnapshot(tick);
    }
    
    // Live mode: map real drones to DroneState (no fabricated telemetry)
    const drones: DroneState[] = realDrones.map(rd => ({
      organization_id: rd.organization_id,
      asset_id: rd.id,
      registration: rd.registration ?? rd.id,
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
      source_timestamp: null,
      received_timestamp: null,
      freshness_status: "UNKNOWN",
    }));

    return {
      organization_id: realDrones[0]?.organization_id ?? "unknown",
      snapshot_at: new Date().toISOString(),
      drones,
      active_missions: [], // Live missions not yet integrated
      recent_events: [], // Live events not yet integrated
    };
  }, [isSimulated, tick, realDrones]);

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
            <AlertsPanel events={isSimulated ? events : []} onAcknowledge={handleAcknowledge} />
            <MissionStatusPanel missions={isSimulated ? SIM_MISSIONS : []} />
          </div>
        )}
      </div>
    </div>
  );
}

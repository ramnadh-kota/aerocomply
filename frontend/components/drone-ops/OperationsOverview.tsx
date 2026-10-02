"use client";

import { useEffect, useState, useCallback } from "react";
import { DroneKPIBar } from "./DroneKPIBar";
import { FleetStatusCards } from "./FleetStatusCards";
import { MapPlaceholder } from "./MapPlaceholder";
import { AlertsPanel } from "./AlertsPanel";
import { MissionStatusPanel } from "./MissionStatusPanel";
import { BatteryOverviewBar } from "./BatteryOverviewBar";
import { FlightEventLog } from "./FlightEventLog";
import {
  buildFleetSnapshot,
  computeFleetKPIs,
  SIM_EVENTS,
  SIM_MISSIONS,
} from "@/lib/drone-ops/mockDroneState";
import type { FleetSnapshot, FleetKPIs, OperationalEvent } from "@/lib/drone-ops/types";

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
  const [tick, setTick] = useState(0);
  const [snapshot, setSnapshot] = useState<FleetSnapshot>(() => buildFleetSnapshot(0));
  const [kpis, setKpis] = useState<FleetKPIs>(() => computeFleetKPIs(buildFleetSnapshot(0)));
  const [selectedDroneId, setSelectedDroneId] = useState<string | null>(null);
  const [events, setEvents] = useState<OperationalEvent[]>(SIM_EVENTS);
  const [operationalTime, setOperationalTime] = useState(nowUTC());

  // Advance simulation tick
  useEffect(() => {
    const interval = setInterval(() => {
      setTick((t) => {
        const nextTick = t + 1;
        const next = buildFleetSnapshot(nextTick);
        setSnapshot(next);
        setKpis(computeFleetKPIs(next));
        setOperationalTime(nowUTC());
        return nextTick;
      });
    }, TICK_INTERVAL_MS);
    return () => clearInterval(interval);
  }, []);

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
      <DroneKPIBar
        kpis={kpis}
        operationalTime={operationalTime}
        connectionLabel="MAVLink Connected"
        isSimulated={true}
      />

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
          <div className="ac-drone-map-area">
            <MapPlaceholder
              droneCount={kpis.total}
              airborneCount={kpis.airborne}
            />
          </div>

          {/* Bottom strip */}
          <div className="ac-drone-overview-bottom">
            <BatteryOverviewBar drones={snapshot.drones} />
            <FlightEventLog events={events} />
          </div>
        </div>

        {/* RIGHT: Alerts + missions */}
        <div className="ac-drone-overview-right">
          <AlertsPanel events={events} onAcknowledge={handleAcknowledge} />
          <MissionStatusPanel missions={SIM_MISSIONS} />
        </div>
      </div>
    </div>
  );
}

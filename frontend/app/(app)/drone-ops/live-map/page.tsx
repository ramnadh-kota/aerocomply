"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import Link from "next/link";
import { FleetMap } from "@/components/drone-ops/FleetMap";
import { liveApi, type LiveStateV1 } from "@/lib/api/live";
import { dronesApi, type DroneResponse } from "@/lib/api/drones";
import { useSession } from "@/lib/auth/SessionContext";
import { buildFleetSnapshot } from "@/lib/drone-ops/mockDroneState";
import type {
  FleetSnapshot,
  DroneState,
  FreshnessStatus,
  ConnectionStatus,
  FlightMode,
} from "@/lib/drone-ops/types";

const TICK_INTERVAL_MS = 2000;

export default function LiveFleetMapPage() {
  const { accessToken } = useSession();
  const [tick, setTick] = useState(0);
  const [isSimulated, setIsSimulated] = useState(false);
  const [realDrones, setRealDrones] = useState<DroneResponse[]>([]);
  const [liveFleetStates, setLiveFleetStates] = useState<LiveStateV1[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedDroneId, setSelectedDroneId] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    if (!accessToken) return;
    try {
      const [dronesData, liveData] = await Promise.all([
        dronesApi.listDrones(accessToken).catch(() => []),
        liveApi.getFleet(accessToken).catch(() => null),
      ]);
      setRealDrones(dronesData);
      if (liveData?.drones) {
        setLiveFleetStates(liveData.drones);
      }
    } catch (err: any) {
      setError(err.message || "Failed to load live fleet positions.");
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
      setTick((t) => t + 1);
      if (accessToken && !isSimulated) {
        liveApi
          .getFleet(accessToken)
          .then((res) => {
            if (res?.drones) {
              setLiveFleetStates(res.drones);
            }
          })
          .catch(() => {});
      }
    }, TICK_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [accessToken, isSimulated]);

  const snapshot = useMemo<FleetSnapshot>(() => {
    if (isSimulated) {
      return buildFleetSnapshot(tick);
    }

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

  const selectedDrone = useMemo(() => {
    return snapshot.drones.find((d) => d.asset_id === selectedDroneId) ?? snapshot.drones[0] ?? null;
  }, [snapshot.drones, selectedDroneId]);

  const airborneCount = snapshot.drones.filter((d) => d.altitude !== null && d.altitude > 0).length;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 48px)", overflow: "hidden" }}>
      {/* Header bar */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: "12px 20px",
          background: "var(--ac-bg-card)",
          borderBottom: "1px solid var(--ac-border)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
          <h1 style={{ fontSize: "18px", fontWeight: 600, color: "var(--ac-text-primary)", margin: 0 }}>
            Live Fleet Map
          </h1>
          <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "6px",
                padding: "2px 8px",
                borderRadius: "12px",
                fontSize: "11px",
                fontWeight: 600,
                background: isSimulated ? "rgba(59, 130, 246, 0.15)" : "rgba(16, 185, 129, 0.15)",
                color: isSimulated ? "#3b82f6" : "#10b981",
              }}
            >
              <span
                style={{
                  width: "6px",
                  height: "6px",
                  borderRadius: "50%",
                  background: isSimulated ? "#3b82f6" : "#10b981",
                }}
              />
              {isSimulated ? "SIMULATED NETWORK" : "LIVE MAVLINK STREAM"}
            </span>
            <span style={{ fontSize: "12px", color: "var(--ac-text-muted)" }}>
              {snapshot.drones.length} Total Assets · {airborneCount} Airborne
            </span>
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <label style={{ display: "flex", alignItems: "center", gap: "6px", cursor: "pointer", fontSize: "12px", color: "var(--ac-text-secondary)" }}>
            <input
              type="checkbox"
              checked={isSimulated}
              onChange={(e) => setIsSimulated(e.target.checked)}
            />
            Simulated Fleet Mode
          </label>
          <Link href="/drone-ops/overview" className="ac-btn-outline" style={{ fontSize: "12px", padding: "4px 10px", textDecoration: "none" }}>
            ← Operations Overview
          </Link>
        </div>
      </div>

      {error && (
        <div style={{ padding: "8px 16px", background: "rgba(239, 68, 68, 0.1)", color: "var(--ac-status-non-compliant)", fontSize: "12px" }}>
          {error}
        </div>
      )}

      {/* Main Map Body with Side Panel */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 340px", flex: 1, minHeight: 0 }}>
        {/* Interactive Leaflet Map */}
        <div style={{ width: "100%", height: "100%", position: "relative" }}>
          <FleetMap
            drones={snapshot.drones}
            selectedDroneId={selectedDrone?.asset_id ?? null}
            onSelectDrone={(id) => setSelectedDroneId(id)}
            isSimulated={isSimulated}
          />
        </div>

        {/* Selected Drone Telemetry & Fleet List Panel */}
        <div
          style={{
            background: "var(--ac-bg-card)",
            borderLeft: "1px solid var(--ac-border)",
            display: "flex",
            flexDirection: "column",
            overflowY: "auto",
          }}
        >
          {selectedDrone ? (
            <div style={{ padding: "16px", borderBottom: "1px solid var(--ac-border)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "12px" }}>
                <div>
                  <h3 style={{ margin: 0, fontSize: "16px", color: "var(--ac-text-primary)" }}>
                    {selectedDrone.registration}
                  </h3>
                  <span style={{ fontSize: "11px", color: "var(--ac-text-muted)" }}>
                    {selectedDrone.asset_id}
                  </span>
                </div>
                <span
                  style={{
                    padding: "2px 8px",
                    borderRadius: "10px",
                    fontSize: "10px",
                    fontWeight: 700,
                    color: selectedDrone.connection_status === "CONNECTED" ? "#10b981" : "#9ca3af",
                    background: selectedDrone.connection_status === "CONNECTED" ? "rgba(16, 185, 129, 0.15)" : "rgba(156, 163, 175, 0.15)",
                  }}
                >
                  {selectedDrone.flight_mode} · {selectedDrone.connection_status}
                </span>
              </div>

              {/* Real-Time Metrics Grid */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px", fontSize: "12px", marginBottom: "16px" }}>
                <div style={{ padding: "8px", background: "var(--ac-bg-elevated)", borderRadius: "4px" }}>
                  <div style={{ color: "var(--ac-text-muted)", fontSize: "10px" }}>ALTITUDE</div>
                  <div style={{ fontWeight: 600, color: "var(--ac-text-primary)" }}>
                    {selectedDrone.altitude !== null ? `${selectedDrone.altitude.toFixed(1)} m` : "—"}
                  </div>
                </div>
                <div style={{ padding: "8px", background: "var(--ac-bg-elevated)", borderRadius: "4px" }}>
                  <div style={{ color: "var(--ac-text-muted)", fontSize: "10px" }}>GROUND SPEED</div>
                  <div style={{ fontWeight: 600, color: "var(--ac-text-primary)" }}>
                    {selectedDrone.speed !== null ? `${selectedDrone.speed.toFixed(1)} m/s` : "—"}
                  </div>
                </div>
                <div style={{ padding: "8px", background: "var(--ac-bg-elevated)", borderRadius: "4px" }}>
                  <div style={{ color: "var(--ac-text-muted)", fontSize: "10px" }}>BATTERY</div>
                  <div style={{ fontWeight: 600, color: selectedDrone.battery_percentage && selectedDrone.battery_percentage < 25 ? "#ef4444" : "var(--ac-text-primary)" }}>
                    {selectedDrone.battery_percentage !== null ? `${selectedDrone.battery_percentage}%` : "—"}
                  </div>
                </div>
                <div style={{ padding: "8px", background: "var(--ac-bg-elevated)", borderRadius: "4px" }}>
                  <div style={{ color: "var(--ac-text-muted)", fontSize: "10px" }}>HEADING</div>
                  <div style={{ fontWeight: 600, color: "var(--ac-text-primary)" }}>
                    {selectedDrone.heading !== null ? `${selectedDrone.heading}°` : "—"}
                  </div>
                </div>
              </div>

              {/* Quick Actions */}
              <div style={{ display: "flex", gap: "8px" }}>
                <Link
                  href={`/drones/${selectedDrone.asset_id}`}
                  style={{
                    flex: 1,
                    textAlign: "center",
                    padding: "6px 12px",
                    background: "var(--ac-bg-elevated)",
                    border: "1px solid var(--ac-border)",
                    borderRadius: "4px",
                    color: "var(--ac-text-primary)",
                    fontSize: "12px",
                    textDecoration: "none",
                    fontWeight: 500,
                  }}
                >
                  Inspect Asset
                </Link>
                <Link
                  href={`/drone-ops/copilot?assetId=${selectedDrone.asset_id}`}
                  style={{
                    flex: 1,
                    textAlign: "center",
                    padding: "6px 12px",
                    background: "var(--ac-accent, #38bdf8)",
                    color: "#000",
                    borderRadius: "4px",
                    fontSize: "12px",
                    textDecoration: "none",
                    fontWeight: 600,
                  }}
                >
                  Ask LISA
                </Link>
              </div>
            </div>
          ) : (
            <div style={{ padding: "24px", textAlign: "center", color: "var(--ac-text-muted)", fontSize: "13px" }}>
              {loading ? "Loading fleet telemetry…" : "No drones active."}
            </div>
          )}

          {/* Fleet List */}
          <div style={{ padding: "12px 16px", flex: 1 }}>
            <h4 style={{ margin: "0 0 8px 0", fontSize: "12px", color: "var(--ac-text-muted)", textTransform: "uppercase", letterSpacing: "0.5px" }}>
              All Fleet Units ({snapshot.drones.length})
            </h4>
            <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
              {snapshot.drones.map((d) => {
                const isSel = d.asset_id === selectedDrone?.asset_id;
                return (
                  <div
                    key={d.asset_id}
                    onClick={() => setSelectedDroneId(d.asset_id)}
                    style={{
                      padding: "8px 12px",
                      background: isSel ? "var(--ac-bg-elevated)" : "transparent",
                      border: isSel ? "1px solid var(--ac-accent, #38bdf8)" : "1px solid var(--ac-border-subtle)",
                      borderRadius: "6px",
                      cursor: "pointer",
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      fontSize: "12px",
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: 600, color: "var(--ac-text-primary)" }}>{d.registration}</div>
                      <div style={{ fontSize: "10px", color: "var(--ac-text-muted)" }}>
                        {d.latitude !== null && d.longitude !== null
                          ? `${d.latitude.toFixed(4)}, ${d.longitude.toFixed(4)}`
                          : "No GPS fix"}
                      </div>
                    </div>
                    <span
                      style={{
                        fontSize: "10px",
                        fontWeight: 700,
                        color: d.connection_status === "CONNECTED" ? "#10b981" : "#9ca3af",
                      }}
                    >
                      {d.connection_status}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

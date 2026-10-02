"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { dronesApi, type DroneResponse } from "@/lib/api/drones";
import { useSession } from "@/lib/auth/SessionContext";
import type { DroneState } from "@/lib/drone-ops/types";

export function DroneDetailPanel({ droneState, onClose }: { droneState: DroneState; onClose: () => void }) {
  const { accessToken } = useSession();
  const [droneDetails, setDroneDetails] = useState<DroneResponse | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    dronesApi.getDrone(accessToken, droneState.asset_id).then(setDroneDetails).catch(console.error);
  }, [accessToken, droneState.asset_id]);

  return (
    <div className="ac-drone-mission-panel" style={{ borderLeft: "1px solid var(--ac-border)", background: "var(--ac-bg-elevated)", height: "100%", zIndex: 10 }}>
      <div className="ac-drone-panel-header-row">
        <div>
          <span className="ac-drone-mission-reg">{droneState.registration}</span>
          <div style={{ fontSize: "9px", color: "var(--ac-text-muted)" }}>
            {droneDetails?.model || "Model Unknown"}
          </div>
        </div>
        <button onClick={onClose} style={{ background: "transparent", border: "none", color: "var(--ac-text-muted)", cursor: "pointer", fontSize: 16 }}>×</button>
      </div>

      <div className="ac-drone-mission-scroll" style={{ padding: "12px", gap: "16px" }}>
        
        {/* Status */}
        <div>
          <h4 className="ac-drone-stub-cap-heading">Status</h4>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px", fontSize: 12 }}>
            <div>
              <span style={{ color: "var(--ac-text-muted)" }}>Link: </span>
              <span style={{ color: droneState.connection_status === "CONNECTED" ? "var(--ac-status-compliant)" : "var(--ac-text-secondary)", fontWeight: 600 }}>{droneState.connection_status}</span>
            </div>
            <div>
              <span style={{ color: "var(--ac-text-muted)" }}>Freshness: </span>
              <span style={{ fontWeight: 600 }}>{droneState.freshness_status}</span>
            </div>
            <div>
              <span style={{ color: "var(--ac-text-muted)" }}>Battery: </span>
              <span style={{ fontWeight: 600, color: droneState.battery_percentage && droneState.battery_percentage < 30 ? "var(--ac-status-non-compliant)" : "inherit" }}>
                {droneState.battery_percentage !== null ? `${Math.round(droneState.battery_percentage)}%` : "UNKNOWN"}
              </span>
            </div>
            <div>
              <span style={{ color: "var(--ac-text-muted)" }}>Mode: </span>
              <span style={{ fontWeight: 600 }}>{droneState.flight_mode}</span>
            </div>
          </div>
        </div>

        {/* Telemetry */}
        <div>
          <h4 className="ac-drone-stub-cap-heading">Live Telemetry</h4>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px", fontSize: 12 }}>
            <div>
              <span style={{ color: "var(--ac-text-muted)" }}>Altitude: </span>
              <span style={{ fontWeight: 600, fontFamily: "var(--ac-font-mono)" }}>{droneState.altitude !== null ? `${Math.round(droneState.altitude)} m` : "UNAVAILABLE"}</span>
            </div>
            <div>
              <span style={{ color: "var(--ac-text-muted)" }}>Speed: </span>
              <span style={{ fontWeight: 600, fontFamily: "var(--ac-font-mono)" }}>{droneState.speed !== null ? `${droneState.speed.toFixed(1)} m/s` : "UNAVAILABLE"}</span>
            </div>
            <div>
              <span style={{ color: "var(--ac-text-muted)" }}>Heading: </span>
              <span style={{ fontWeight: 600, fontFamily: "var(--ac-font-mono)" }}>{droneState.heading !== null ? `${Math.round(droneState.heading)}°` : "UNAVAILABLE"}</span>
            </div>
            <div style={{ gridColumn: "1 / -1" }}>
              <span style={{ color: "var(--ac-text-muted)" }}>Position: </span>
              <span style={{ fontWeight: 600, fontFamily: "var(--ac-font-mono)" }}>
                {droneState.latitude !== null && droneState.longitude !== null 
                  ? `${droneState.latitude.toFixed(4)}, ${droneState.longitude.toFixed(4)}` 
                  : "UNAVAILABLE"}
              </span>
            </div>
          </div>
        </div>

        {/* Actions */}
        <div>
          <h4 className="ac-drone-stub-cap-heading">Actions</h4>
          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            <Link href={`/drone-ops/telemetry?assetId=${droneState.asset_id}`} className="ac-btn-secondary" style={{ textAlign: "center", textDecoration: "none", padding: "6px", fontSize: 11 }}>View Full Telemetry</Link>
            <Link href={`/drone-ops/health?assetId=${droneState.asset_id}`} className="ac-btn-secondary" style={{ textAlign: "center", textDecoration: "none", padding: "6px", fontSize: 11 }}>View HUMS Health</Link>
            <Link href={`/drone-ops/missions?assetId=${droneState.asset_id}`} className="ac-btn-secondary" style={{ textAlign: "center", textDecoration: "none", padding: "6px", fontSize: 11 }}>Mission Planner</Link>
            <Link href={`/drones/${droneState.asset_id}`} className="ac-btn-secondary" style={{ textAlign: "center", textDecoration: "none", padding: "6px", fontSize: 11 }}>Asset Profile</Link>
          </div>
        </div>
      </div>
    </div>
  );
}

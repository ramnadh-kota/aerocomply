"use client";

import type { DroneState } from "@/lib/drone-ops/types";

// ─────────────────────────────────────────────────────────────────────────────
// Battery overview bar — bottom panel showing per-drone battery status at a glance.
// ─────────────────────────────────────────────────────────────────────────────

interface BatteryOverviewBarProps {
  drones: DroneState[];
}

function batteryColor(pct: number | null, connection: DroneState["connection_status"]): string {
  if (connection === "DISCONNECTED") return "var(--ac-text-muted)";
  if (pct === null) return "var(--ac-text-muted)";
  if (pct <= 20) return "var(--ac-status-non-compliant)";
  if (pct <= 40) return "var(--ac-status-review)";
  return "var(--ac-status-compliant)";
}

export function BatteryOverviewBar({ drones }: BatteryOverviewBarProps) {
  return (
    <div className="ac-drone-battery-overview" role="region" aria-label="Fleet battery overview">
      <span className="ac-drone-battery-overview-label">Battery</span>
      <div className="ac-drone-battery-overview-items">
        {drones.map((drone) => {
          const pct = drone.battery_percentage;
          const offline = drone.connection_status === "DISCONNECTED";
          const color = batteryColor(pct, drone.connection_status);

          return (
            <div
              key={drone.asset_id}
              className="ac-drone-battery-cell"
              title={`${drone.registration}: ${pct !== null ? `${Math.round(pct)}%` : "Unknown"}`}
              aria-label={`${drone.registration} battery ${pct !== null ? `${Math.round(pct)}%` : "unknown"}`}
            >
              <span className="ac-drone-battery-cell-reg">{drone.registration}</span>

              {/* Vertical battery indicator */}
              <div className="ac-drone-battery-cell-track">
                <div
                  className="ac-drone-battery-cell-fill"
                  style={{
                    height: offline ? "0%" : `${pct ?? 0}%`,
                    background: color,
                  }}
                />
              </div>

              <span
                className="ac-drone-battery-cell-pct"
                style={{ color }}
              >
                {offline ? "OFF" : pct !== null ? `${Math.round(pct)}%` : "—"}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

"use client";

import Link from "next/link";
import type { DroneState } from "@/lib/drone-ops/types";

// ─────────────────────────────────────────────────────────────────────────────
// Fleet status cards — left panel of the operations overview.
// One card per drone showing identity, telemetry snapshot, battery, heading.
// ─────────────────────────────────────────────────────────────────────────────

interface FleetStatusCardsProps {
  drones: DroneState[];
  selectedDroneId: string | null;
  onSelect: (id: string) => void;
}

function batteryColor(pct: number | null): string {
  if (pct === null) return "var(--ac-text-muted)";
  if (pct <= 20) return "var(--ac-status-non-compliant)";
  if (pct <= 40) return "var(--ac-status-review)";
  return "var(--ac-status-compliant)";
}

function connectionColor(status: DroneState["connection_status"]): string {
  switch (status) {
    case "CONNECTED":    return "var(--ac-status-compliant)";
    case "DEGRADED":     return "var(--ac-status-review)";
    case "DISCONNECTED": return "var(--ac-status-non-compliant)";
    default:             return "var(--ac-text-muted)";
  }
}

function flightModeLabel(mode: DroneState["flight_mode"]): string {
  const map: Record<string, string> = {
    AUTO: "AUTO", GUIDED: "GUIDED", LOITER: "LOITER", MANUAL: "MANUAL",
    RTL: "RTL", LAND: "LAND", HOLD: "HOLD", TAKEOFF: "T/O", IDLE: "GRND",
    STABILIZE: "STAB", UNKNOWN: "—",
  };
  return map[mode] ?? mode;
}

function HeadingArrow({ heading }: { heading: number | null }) {
  if (heading === null) return <span style={{ color: "var(--ac-text-muted)" }}>—</span>;
  return (
    <span
      aria-label={`Heading ${Math.round(heading)}°`}
      style={{
        display: "inline-block",
        transform: `rotate(${heading}deg)`,
        fontSize: 14,
        lineHeight: 1,
        color: "var(--ac-accent)",
        transition: "transform 0.4s ease",
      }}
    >
      ↑
    </span>
  );
}

function BatteryBar({ pct }: { pct: number | null }) {
  const displayPct = pct ?? 0;
  const color = batteryColor(pct);
  return (
    <div className="ac-drone-battery-bar-wrap" role="progressbar" aria-valuenow={displayPct} aria-valuemin={0} aria-valuemax={100} aria-label={`Battery ${displayPct}%`}>
      <div className="ac-drone-battery-bar-track">
        <div
          className="ac-drone-battery-bar-fill"
          style={{
            width: `${displayPct}%`,
            background: color,
          }}
        />
      </div>
      <span className="ac-drone-battery-pct" style={{ color }}>{pct !== null ? `${Math.round(pct)}%` : "—"}</span>
    </div>
  );
}

export function FleetStatusCards({ drones, selectedDroneId, onSelect }: FleetStatusCardsProps) {
  return (
    <aside className="ac-drone-fleet-panel" aria-label="Fleet status cards">
      <div className="ac-drone-fleet-panel-header">
        <span className="ac-drone-panel-title">Active Fleet</span>
        <span className="ac-drone-panel-count">{drones.length} aircraft</span>
      </div>

      <div className="ac-drone-fleet-scroll">
        {drones.map((drone) => {
          const isSelected = drone.asset_id === selectedDroneId;
          const isAirborne = (drone.altitude ?? 0) > 0 && drone.connection_status !== "DISCONNECTED";

          return (
            <button
              key={drone.asset_id}
              className={`ac-drone-card${isSelected ? " selected" : ""}${isAirborne ? " airborne" : ""}`}
              onClick={() => onSelect(drone.asset_id)}
              aria-pressed={isSelected}
              aria-label={`Select drone ${drone.registration}`}
            >
              {/* Card header */}
              <div className="ac-drone-card-header">
                <div className="ac-drone-card-identity">
                  <span
                    className="ac-drone-status-dot"
                    style={{ background: connectionColor(drone.connection_status) }}
                    aria-hidden="true"
                  />
                  <span className="ac-drone-card-reg">{drone.registration}</span>
                  <span
                    className="ac-drone-card-mode"
                    style={{
                      color: isAirborne ? "var(--ac-accent)" : "var(--ac-text-muted)",
                    }}
                  >
                    {flightModeLabel(drone.flight_mode)}
                  </span>
                </div>
                <HeadingArrow heading={drone.heading} />
              </div>

              {/* Telemetry grid */}
              <div className="ac-drone-card-telemetry">
                <div className="ac-drone-telem-cell">
                  <span className="ac-drone-telem-label">ALT</span>
                  <span className="ac-drone-telem-value">
                    {drone.altitude !== null ? `${Math.round(drone.altitude)}m` : "—"}
                  </span>
                </div>
                <div className="ac-drone-telem-cell">
                  <span className="ac-drone-telem-label">SPD</span>
                  <span className="ac-drone-telem-value">
                    {drone.speed !== null ? `${drone.speed.toFixed(1)}m/s` : "—"}
                  </span>
                </div>
                <div className="ac-drone-telem-cell">
                  <span className="ac-drone-telem-label">HDG</span>
                  <span className="ac-drone-telem-value">
                    {drone.heading !== null ? `${Math.round(drone.heading)}°` : "—"}
                  </span>
                </div>
                <div className="ac-drone-telem-cell">
                  <span className="ac-drone-telem-label">LINK</span>
                  <span
                    className="ac-drone-telem-value"
                    style={{ color: connectionColor(drone.connection_status), fontSize: 10 }}
                  >
                    {drone.connection_status}
                  </span>
                </div>
              </div>

              {/* Battery */}
              <BatteryBar pct={drone.battery_percentage} />

              {/* Freshness tag */}
              {drone.freshness_status !== "FRESH" && (
                <div
                  className="ac-drone-card-stale"
                  aria-label={`Data freshness: ${drone.freshness_status}`}
                >
                  {drone.freshness_status === "VERY_STALE" ? "⚠ OFFLINE" : "⚡ STALE"}
                </div>
              )}

              {/* Detail link */}
              <Link
                href={`/drones/${drone.asset_id}`}
                className="ac-drone-card-detail-link"
                onClick={(e) => e.stopPropagation()}
                aria-label={`Open full detail for ${drone.registration}`}
              >
                Detail →
              </Link>
            </button>
          );
        })}
      </div>
    </aside>
  );
}

"use client";

import type { FleetKPIs } from "@/lib/drone-ops/types";
import { SimDataBanner } from "./SimDataBanner";

interface DroneKPIBarProps {
  kpis: FleetKPIs;
  operationalTime: string;
  connectionLabel: string;
  isSimulated: boolean;
}

interface KPIPillProps {
  label: string;
  value: string | number;
  color?: string;
  pulse?: boolean;
}

function KPIPill({ label, value, color, pulse }: KPIPillProps) {
  return (
    <div className="ac-drone-kpi-pill">
      <span
        className={`ac-drone-kpi-value${pulse ? " ac-drone-kpi-pulse" : ""}`}
        style={color ? { color } : undefined}
      >
        {value}
      </span>
      <span className="ac-drone-kpi-label">{label}</span>
    </div>
  );
}

export function DroneKPIBar({
  kpis,
  operationalTime,
  connectionLabel,
  isSimulated,
}: DroneKPIBarProps) {
  return (
    <header className="ac-drone-ops-topbar">
      {/* Left: identity */}
      <div className="ac-drone-ops-topbar-identity">
        <span className="ac-drone-ops-topbar-module">KOTA AEROSPACE</span>
        <span className="ac-drone-ops-topbar-sep">·</span>
        <span className="ac-drone-ops-topbar-workspace">DRONE OPERATIONS</span>
      </div>

      {/* Center: KPI pills */}
      <div className="ac-drone-kpi-bar" role="region" aria-label="Fleet key performance indicators">
        <KPIPill
          label="Total Fleet"
          value={kpis.total}
        />
        <KPIPill
          label="Airborne"
          value={kpis.airborne}
          color="var(--ac-status-compliant)"
          pulse={kpis.airborne > 0}
        />
        <KPIPill
          label="Active Missions"
          value={kpis.active_missions}
          color="var(--ac-accent)"
        />
        <KPIPill
          label="Low Battery"
          value={kpis.low_battery_count}
          color={kpis.low_battery_count > 0 ? "var(--ac-status-non-compliant)" : undefined}
        />
        <KPIPill
          label="Alerts"
          value={kpis.unacknowledged_alerts}
          color={kpis.unacknowledged_alerts > 0 ? "var(--ac-status-review)" : undefined}
          pulse={kpis.unacknowledged_alerts > 0}
        />
      </div>

      {/* Right: status */}
      <div className="ac-drone-ops-topbar-status">
        {isSimulated && <SimDataBanner compact />}
        <div className="ac-drone-ops-connection-pill" title={connectionLabel}>
          <span
            className="ac-drone-ops-connection-dot"
            style={{
              background: isSimulated
                ? "var(--ac-status-review)"
                : "var(--ac-status-compliant)",
            }}
            aria-hidden="true"
          />
          <span className="ac-drone-ops-connection-label">
            {isSimulated ? "SIMULATION" : connectionLabel}
          </span>
        </div>
        <span className="ac-drone-ops-time" aria-label="Operational time">
          {operationalTime}
        </span>
      </div>
    </header>
  );
}

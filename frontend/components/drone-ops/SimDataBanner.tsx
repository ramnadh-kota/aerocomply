"use client";

// Persistent "SIMULATED FLIGHT DATA" notice rendered in every drone-ops page
// during A1 (before live telemetry is connected). Must never be hidden or
// optional when simulation data is in use — per master prompt §1 rule 10:
// "Simulated data must always be visibly labeled."

interface SimDataBannerProps {
  compact?: boolean;
}

export function SimDataBanner({ compact = false }: SimDataBannerProps) {
  if (compact) {
    return (
      <span
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 4,
          padding: "2px 8px",
          borderRadius: 4,
          background: "rgba(232, 163, 61, 0.15)",
          border: "1px solid rgba(232, 163, 61, 0.35)",
          color: "var(--ac-status-review)",
          fontSize: 10,
          fontWeight: 700,
          letterSpacing: "0.06em",
          textTransform: "uppercase",
          fontFamily: "var(--ac-font-mono, monospace)",
        }}
        aria-label="Simulated flight data — not live telemetry"
      >
        <span aria-hidden="true">⚠</span>
        SIM DATA
      </span>
    );
  }

  return (
    <div
      role="note"
      aria-label="Simulated flight data — not live telemetry"
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "7px 14px",
        background: "rgba(232, 163, 61, 0.1)",
        borderBottom: "1px solid rgba(232, 163, 61, 0.25)",
        color: "var(--ac-status-review)",
        fontSize: 11,
        fontWeight: 600,
        letterSpacing: "0.04em",
        fontFamily: "var(--ac-font-mono, monospace)",
      }}
    >
      <span aria-hidden="true" style={{ fontSize: 13 }}>⚠</span>
      SIMULATED FLIGHT DATA — NOT CONNECTED TO LIVE TELEMETRY
      <span
        style={{
          marginLeft: "auto",
          fontWeight: 400,
          color: "var(--ac-text-muted)",
          fontFamily: "var(--ac-font)",
          letterSpacing: 0,
          fontSize: 11,
        }}
      >
        Connect MAVLink / MAVProxy to replace with real data
      </span>
    </div>
  );
}

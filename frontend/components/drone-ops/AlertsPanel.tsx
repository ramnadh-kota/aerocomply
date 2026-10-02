"use client";

import type { BackendProactiveAlert } from "@/lib/api/proactive";

// ─────────────────────────────────────────────────────────────────────────────
// Alerts & Events panel — right-side strip showing proactive alerts.
// ─────────────────────────────────────────────────────────────────────────────

interface AlertsPanelProps {
  events: BackendProactiveAlert[];
}

function severityIcon(severity: BackendProactiveAlert["severity"]): { icon: string; color: string } {
  switch (severity) {
    case "CRITICAL": return { icon: "🔴", color: "var(--ac-status-non-compliant)" };
    case "HIGH":  return { icon: "🟠", color: "var(--ac-status-review)" };
    case "MEDIUM":     return { icon: "🟡", color: "var(--ac-status-review)" };
    default:         return { icon: "⚪", color: "var(--ac-text-muted)" };
  }
}

export function AlertsPanel({ events }: AlertsPanelProps) {
  // Proactive alerts don't have an explicit 'acknowledged' state returned via the proactiveApi yet,
  // and no resolution actions exist. We treat all returned alerts as active.

  return (
    <aside className="ac-drone-alerts-panel" aria-label="Operational alerts">
      <div className="ac-drone-panel-header-row">
        <span className="ac-drone-panel-title">Alerts & Events</span>
        {events.length > 0 && (
          <span
            className="ac-drone-alerts-badge"
            aria-label={`${events.length} alerts`}
          >
            {events.length}
          </span>
        )}
      </div>

      <div className="ac-drone-alerts-scroll">
        {events.length === 0 && (
          <div className="ac-drone-alerts-empty">
            <span aria-hidden="true" style={{ fontSize: 20, display: "block", marginBottom: 6 }}>✓</span>
            No active alerts
          </div>
        )}

        {events.map((evt) => {
          const { icon, color } = severityIcon(evt.severity);
          return (
            <div
              key={evt.id}
              className={`ac-drone-alert-item severity-${evt.severity.toLowerCase()}`}
              role="alert"
              aria-atomic="true"
            >
              <div className="ac-drone-alert-header">
                <span
                  className="ac-drone-alert-icon"
                  aria-label={evt.severity}
                  title={evt.severity}
                >
                  {icon}
                </span>
                <span className="ac-drone-alert-reg" style={{ color }}>
                  {evt.aircraft_id ?? evt.work_order_id ?? "Fleet"}
                </span>
              </div>
              <div style={{ fontSize: 11, fontWeight: 600, marginTop: 4, color: "var(--ac-text-primary)" }}>
                {evt.title}
              </div>
              <p className="ac-drone-alert-desc" style={{ marginTop: 2 }}>{evt.message}</p>
            </div>
          );
        })}

        {/* Placeholder for LISA Context Integration */}
        <div style={{ marginTop: "16px", padding: "12px", border: "1px dashed var(--ac-border)", borderRadius: "8px", background: "rgba(0,0,0,0.2)" }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: "var(--ac-accent)", marginBottom: 4 }}>
            ✧ LISA Context
          </div>
          <p style={{ fontSize: 11, color: "var(--ac-text-muted)", margin: 0 }}>
            LISA integration for alert root-cause analysis is pending verified backend response schemas.
          </p>
        </div>
      </div>
    </aside>
  );
}

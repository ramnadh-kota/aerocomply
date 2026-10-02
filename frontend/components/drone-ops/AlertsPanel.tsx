"use client";

import type { OperationalEvent } from "@/lib/drone-ops/types";

// ─────────────────────────────────────────────────────────────────────────────
// Alerts & Events panel — right-side strip showing unacknowledged alerts.
// ─────────────────────────────────────────────────────────────────────────────

interface AlertsPanelProps {
  events: OperationalEvent[];
  onAcknowledge: (eventId: string) => void;
}

function severityIcon(severity: OperationalEvent["severity"]): { icon: string; color: string } {
  switch (severity) {
    case "CRITICAL": return { icon: "🔴", color: "var(--ac-status-non-compliant)" };
    case "WARNING":  return { icon: "🟡", color: "var(--ac-status-review)" };
    case "INFO":     return { icon: "🔵", color: "var(--ac-accent)" };
    default:         return { icon: "⚪", color: "var(--ac-text-muted)" };
  }
}

function relativeTime(isoTimestamp: string): string {
  const diff = Date.now() - new Date(isoTimestamp).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  return `${hrs}h ago`;
}

export function AlertsPanel({ events, onAcknowledge }: AlertsPanelProps) {
  const active = events.filter((e) => e.acknowledgment_status === "UNACKNOWLEDGED");
  const cleared = events.filter((e) => e.acknowledgment_status !== "UNACKNOWLEDGED");

  return (
    <aside className="ac-drone-alerts-panel" aria-label="Operational alerts">
      <div className="ac-drone-panel-header-row">
        <span className="ac-drone-panel-title">Alerts & Events</span>
        {active.length > 0 && (
          <span
            className="ac-drone-alerts-badge"
            aria-label={`${active.length} unacknowledged alerts`}
          >
            {active.length}
          </span>
        )}
      </div>

      <div className="ac-drone-alerts-scroll">
        {active.length === 0 && (
          <div className="ac-drone-alerts-empty">
            <span aria-hidden="true" style={{ fontSize: 20, display: "block", marginBottom: 6 }}>✓</span>
            No active alerts
          </div>
        )}

        {active.map((evt) => {
          const { icon, color } = severityIcon(evt.severity);
          return (
            <div
              key={evt.event_id}
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
                  {evt.registration ?? "Fleet"}
                </span>
                <span className="ac-drone-alert-time">
                  {relativeTime(evt.event_timestamp)}
                </span>
              </div>

              <p className="ac-drone-alert-desc">{evt.description}</p>

              <button
                className="ac-drone-alert-ack-btn"
                onClick={() => onAcknowledge(evt.event_id)}
                aria-label={`Acknowledge alert: ${evt.description}`}
              >
                Acknowledge
              </button>
            </div>
          );
        })}

        {/* Cleared / auto-cleared section */}
        {cleared.length > 0 && (
          <>
            <div className="ac-drone-alerts-divider">
              <span>Recent — Cleared</span>
            </div>
            {cleared.slice(0, 3).map((evt) => {
              const { icon } = severityIcon(evt.severity);
              return (
                <div
                  key={evt.event_id}
                  className="ac-drone-alert-item cleared"
                  aria-label={`Cleared: ${evt.description}`}
                >
                  <div className="ac-drone-alert-header">
                    <span className="ac-drone-alert-icon" aria-hidden="true">{icon}</span>
                    <span className="ac-drone-alert-reg cleared-text">
                      {evt.registration ?? "Fleet"}
                    </span>
                    <span className="ac-drone-alert-time">
                      {relativeTime(evt.event_timestamp)}
                    </span>
                  </div>
                  <p className="ac-drone-alert-desc cleared-text">{evt.description}</p>
                </div>
              );
            })}
          </>
        )}
      </div>
    </aside>
  );
}

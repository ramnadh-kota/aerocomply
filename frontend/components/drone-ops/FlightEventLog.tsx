"use client";

import type { OperationalEvent } from "@/lib/drone-ops/types";

// ─────────────────────────────────────────────────────────────────────────────
// Flight event log — bottom strip showing a live event timeline.
// ─────────────────────────────────────────────────────────────────────────────

interface FlightEventLogProps {
  events: OperationalEvent[];
}

function severityStyle(severity: OperationalEvent["severity"]): { color: string; prefix: string } {
  switch (severity) {
    case "CRITICAL": return { color: "var(--ac-status-non-compliant)", prefix: "CRIT" };
    case "WARNING":  return { color: "var(--ac-status-review)",        prefix: "WARN" };
    case "INFO":     return { color: "var(--ac-accent)",               prefix: "INFO" };
    default:         return { color: "var(--ac-text-muted)",           prefix: "DBG " };
  }
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  const ss = String(d.getSeconds()).padStart(2, "0");
  return `${hh}:${mm}:${ss}`;
}

export function FlightEventLog({ events }: FlightEventLogProps) {
  const sorted = [...events].sort(
    (a, b) =>
      new Date(b.event_timestamp).getTime() -
      new Date(a.event_timestamp).getTime()
  );

  return (
    <div className="ac-drone-event-log" role="log" aria-label="Flight event log" aria-live="polite">
      <span className="ac-drone-event-log-label">Flight Log</span>
      <div className="ac-drone-event-log-scroll">
        {sorted.length === 0 && (
          <span className="ac-drone-event-log-empty">No events recorded</span>
        )}
        {sorted.map((evt, idx) => {
          const { color, prefix } = severityStyle(evt.severity);
          return (
            <div key={evt.event_id ?? idx} className="ac-drone-event-log-row">
              <span
                className="ac-drone-event-log-time"
                aria-label={`Event at ${formatTime(evt.event_timestamp)}`}
              >
                {formatTime(evt.event_timestamp)}
              </span>
              <span
                className="ac-drone-event-log-sev"
                style={{ color }}
                aria-label={evt.severity}
              >
                {prefix}
              </span>
              <span className="ac-drone-event-log-reg">
                {evt.registration ?? "FLT"}
              </span>
              <span className="ac-drone-event-log-msg">{evt.description}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

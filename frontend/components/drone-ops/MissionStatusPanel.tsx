"use client";

import type { BackendMission } from "@/lib/api/missions";

// ─────────────────────────────────────────────────────────────────────────────
// Mission status and progress cards — right-side panel, below alerts.
// ─────────────────────────────────────────────────────────────────────────────

interface MissionStatusPanelProps {
  missions: BackendMission[];
}

function statusColor(status: BackendMission["status"]): string {
  switch (status) {
    case "IN_PROGRESS":  return "var(--ac-status-compliant)";
    case "AUTHORIZED":   return "var(--ac-accent)";
    case "PLANNED":      return "var(--ac-text-muted)";
    case "COMPLETED":    return "var(--ac-status-compliant)";
    case "CANCELLED":    return "var(--ac-status-non-compliant)";
    default:             return "var(--ac-text-muted)";
  }
}

function statusLabel(status: BackendMission["status"]): string {
  const map: Record<string, string> = {
    IN_PROGRESS: "IN FLIGHT",
    AUTHORIZED: "AUTHORIZED",
    PLANNED: "PLANNED",
    COMPLETED: "COMPLETE",
    CANCELLED: "CANCELLED",
  };
  return map[status] ?? status;
}

function relativeTime(iso: string | null): string {
  if (!iso) return "—";
  const diff = new Date(iso).getTime() - Date.now();
  const mins = Math.round(Math.abs(diff) / 60000);
  if (mins < 1) return diff < 0 ? "now" : "< 1m";
  if (mins < 60) return diff < 0 ? `${mins}m ago` : `in ${mins}m`;
  return `${Math.floor(mins / 60)}h ${mins % 60}m`;
}

export function MissionStatusPanel({ missions }: MissionStatusPanelProps) {
  const active = missions.filter(
    (m) => m.status === "IN_PROGRESS" || m.status === "AUTHORIZED"
  );

  return (
    <div className="ac-drone-mission-panel" aria-label="Active missions">
      <div className="ac-drone-panel-header-row">
        <span className="ac-drone-panel-title">Active Missions</span>
        <span className="ac-drone-panel-count">{active.length}</span>
      </div>

      <div className="ac-drone-mission-scroll">
        {active.length === 0 && (
          <div className="ac-drone-mission-empty">No active missions</div>
        )}

        {active.map((mission) => (
          <div key={mission.id} className="ac-drone-mission-card">
            <div className="ac-drone-mission-card-header">
              <span className="ac-drone-mission-reg">{mission.asset_id}</span>
              <span
                className="ac-drone-mission-status-pill"
                style={{ color: statusColor(mission.status) }}
              >
                {statusLabel(mission.status)}
              </span>
            </div>

            <p className="ac-drone-mission-purpose" title={mission.purpose}>
              {mission.purpose.length > 52
                ? `${mission.purpose.slice(0, 52)}…`
                : mission.purpose}
            </p>

            <div className="ac-drone-mission-meta">
              <span>
                <span className="ac-drone-mission-meta-key">Pilot</span>
                {mission.pilot_name ?? "—"}
              </span>
              <span>
                <span className="ac-drone-mission-meta-key">Planned</span>
                {relativeTime(mission.planned_start)}
              </span>
            </div>

            {mission.operating_area && (
              <div className="ac-drone-mission-area">
                <span aria-hidden="true">◎</span>
                {mission.operating_area}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

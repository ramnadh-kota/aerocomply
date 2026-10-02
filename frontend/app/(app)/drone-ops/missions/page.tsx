"use client";

import { useEffect, useState } from "react";
import { useSession } from "@/lib/auth/SessionContext";
import { missionsApi, type BackendMission, missionPilotLabel } from "@/lib/api/missions";
import Link from "next/link";

export default function MissionsPage() {
  const { accessToken } = useSession();
  const [missions, setMissions] = useState<BackendMission[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    setLoading(true);
    missionsApi.listMissions(accessToken)
      .then(data => setMissions(data.items))
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, [accessToken]);

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

  return (
    <div style={{ padding: "24px", maxWidth: "1200px", margin: "0 auto" }}>
      <header style={{ marginBottom: "24px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1 style={{ fontSize: "24px", fontWeight: 600, color: "var(--ac-text-primary)", margin: 0 }}>Mission Operations</h1>
        <div style={{ display: "flex", gap: "12px" }}>
          <button className="ac-btn-primary" disabled style={{ opacity: 0.5, cursor: "not-allowed" }}>Plan New Mission</button>
        </div>
      </header>

      {error && (
        <div style={{ padding: "12px", background: "rgba(239, 68, 68, 0.1)", border: "1px solid var(--ac-status-non-compliant)", color: "var(--ac-status-non-compliant)", borderRadius: "4px", marginBottom: "16px" }}>
          {error}
        </div>
      )}

      <div style={{ background: "var(--ac-bg-card)", border: "1px solid var(--ac-border)", borderRadius: "8px", overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left", fontSize: 13 }}>
          <thead style={{ background: "var(--ac-bg-elevated)", color: "var(--ac-text-muted)" }}>
            <tr>
              <th style={{ padding: "12px 16px", borderBottom: "1px solid var(--ac-border)" }}>Asset / Mission</th>
              <th style={{ padding: "12px 16px", borderBottom: "1px solid var(--ac-border)" }}>Status</th>
              <th style={{ padding: "12px 16px", borderBottom: "1px solid var(--ac-border)" }}>Pilot</th>
              <th style={{ padding: "12px 16px", borderBottom: "1px solid var(--ac-border)" }}>Planned Start</th>
              <th style={{ padding: "12px 16px", borderBottom: "1px solid var(--ac-border)" }}>Operating Area</th>
              <th style={{ padding: "12px 16px", borderBottom: "1px solid var(--ac-border)", textAlign: "right" }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={6} style={{ padding: "24px", textAlign: "center", color: "var(--ac-text-muted)" }}>Loading missions...</td></tr>
            ) : missions.length === 0 ? (
              <tr><td colSpan={6} style={{ padding: "24px", textAlign: "center", color: "var(--ac-text-muted)" }}>No missions found.</td></tr>
            ) : (
              missions.map(mission => (
                <tr key={mission.id} style={{ borderBottom: "1px solid var(--ac-border-subtle)" }}>
                  <td style={{ padding: "12px 16px" }}>
                    <div style={{ fontWeight: 600, color: "var(--ac-text-primary)", marginBottom: 2 }}>{mission.asset_id}</div>
                    <div style={{ color: "var(--ac-text-secondary)", fontSize: 11 }}>{mission.purpose}</div>
                  </td>
                  <td style={{ padding: "12px 16px" }}>
                    <span style={{
                      display: "inline-block",
                      padding: "2px 8px",
                      borderRadius: "12px",
                      fontSize: 10,
                      fontWeight: 700,
                      color: statusColor(mission.status),
                      background: `color-mix(in srgb, ${statusColor(mission.status)} 15%, transparent)`
                    }}>
                      {mission.status}
                    </span>
                  </td>
                  <td style={{ padding: "12px 16px", color: "var(--ac-text-secondary)" }}>
                    {missionPilotLabel(mission) ?? "Unassigned"}
                  </td>
                  <td style={{ padding: "12px 16px", color: "var(--ac-text-secondary)" }}>
                    {mission.planned_start ? new Date(mission.planned_start).toLocaleString() : "—"}
                  </td>
                  <td style={{ padding: "12px 16px", color: "var(--ac-text-secondary)" }}>
                    {mission.operating_area || "—"}
                  </td>
                  <td style={{ padding: "12px 16px", textAlign: "right", display: "flex", gap: "12px", justifyContent: "flex-end" }}>
                    <Link href={`/drone-ops/copilot?assetId=${mission.asset_id}&q=${encodeURIComponent(`Tell me about mission ${mission.purpose || mission.id}`)}`} style={{ color: "var(--ac-accent)", textDecoration: "none", fontSize: 12, fontWeight: 500 }}>
                      Ask LISA
                    </Link>
                    <Link href={`/drone-ops/overview?assetId=${mission.asset_id}`} style={{ color: "var(--ac-text-secondary)", textDecoration: "none", fontSize: 12, fontWeight: 500 }}>
                      View in Fleet
                    </Link>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

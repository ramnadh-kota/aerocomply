"use client";

import { useEffect, useState } from "react";
import { useSession } from "@/lib/auth/SessionContext";
import { proactiveApi, type BackendProactiveAlert } from "@/lib/api/proactive";
import Link from "next/link";

export default function AlertsPage() {
  const { accessToken } = useSession();
  const [alerts, setAlerts] = useState<BackendProactiveAlert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    setLoading(true);
    proactiveApi.getAlerts(accessToken)
      .then(setAlerts)
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, [accessToken]);

  function severityBadge(severity: BackendProactiveAlert["severity"]) {
    let color = "var(--ac-text-muted)";
    if (severity === "CRITICAL") color = "var(--ac-status-non-compliant)";
    if (severity === "HIGH") color = "var(--ac-status-review)";
    if (severity === "MEDIUM") color = "var(--ac-status-review)";

    return (
      <span style={{
        display: "inline-block",
        padding: "2px 8px",
        borderRadius: "12px",
        fontSize: 10,
        fontWeight: 700,
        color: color,
        background: `color-mix(in srgb, ${color} 15%, transparent)`
      }}>
        {severity}
      </span>
    );
  }

  return (
    <div style={{ padding: "24px", maxWidth: "1200px", margin: "0 auto" }}>
      <header style={{ marginBottom: "24px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1 style={{ fontSize: "24px", fontWeight: 600, color: "var(--ac-text-primary)", margin: 0 }}>Operational Alerts</h1>
      </header>

      {error && (
        <div style={{ padding: "12px", background: "rgba(239, 68, 68, 0.1)", border: "1px solid var(--ac-status-non-compliant)", color: "var(--ac-status-non-compliant)", borderRadius: "4px", marginBottom: "16px" }}>
          {error}
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: "24px", alignItems: "start" }}>
        {/* Main Alerts Feed */}
        <div style={{ background: "var(--ac-bg-card)", border: "1px solid var(--ac-border)", borderRadius: "8px", overflow: "hidden", display: "flex", flexDirection: "column" }}>
          {loading ? (
            <div style={{ padding: "24px", textAlign: "center", color: "var(--ac-text-muted)" }}>Loading alerts...</div>
          ) : alerts.length === 0 ? (
            <div style={{ padding: "24px", textAlign: "center", color: "var(--ac-text-muted)" }}>No active alerts.</div>
          ) : (
            alerts.map((alert, idx) => (
              <div key={alert.id} style={{ padding: "16px", borderBottom: idx < alerts.length - 1 ? "1px solid var(--ac-border-subtle)" : "none" }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "8px" }}>
                  <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
                    {severityBadge(alert.severity)}
                    <span style={{ fontWeight: 600, color: "var(--ac-text-primary)" }}>{alert.title}</span>
                  </div>
                  <span style={{ color: "var(--ac-text-muted)", fontSize: 12 }}>
                    Asset: {alert.aircraft_id ?? alert.work_order_id ?? "Fleet"}
                  </span>
                </div>
                <p style={{ margin: "0 0 12px 0", color: "var(--ac-text-secondary)", fontSize: 13, lineHeight: 1.5 }}>
                  {alert.message}
                </p>
                <div style={{ display: "flex", justifyContent: "flex-end", gap: "12px", alignItems: "center" }}>
                  {alert.aircraft_id && (
                    <Link href={`/drone-ops/copilot?assetId=${alert.aircraft_id}&q=${encodeURIComponent(`Tell me about alert: ${alert.title}`)}`} style={{ color: "var(--ac-accent)", textDecoration: "none", fontSize: 12, fontWeight: 500 }}>
                      Ask LISA
                    </Link>
                  )}
                  {alert.aircraft_id ? (
                    <Link href={`/drones/${alert.aircraft_id}`} style={{ color: "var(--ac-text-secondary)", textDecoration: "none", fontSize: 12, fontWeight: 500 }}>
                      Inspect Asset
                    </Link>
                  ) : null}
                </div>
              </div>
            ))
          )}
        </div>

        {/* Right Panel: LISA Context */}
        <div style={{ background: "var(--ac-bg-elevated)", border: "1px dashed var(--ac-border)", borderRadius: "8px", padding: "16px" }}>
          <h3 style={{ margin: "0 0 8px 0", fontSize: 14, color: "var(--ac-accent)", display: "flex", alignItems: "center", gap: "8px" }}>
            <span>✧</span> LISA Context
          </h3>
          <p style={{ margin: 0, fontSize: 13, color: "var(--ac-text-muted)", lineHeight: 1.5 }}>
            LISA can be queried for asset-level context.
            <br /><br />
            <em>Note: Dedicated root-cause analysis for specific alert IDs is pending backend integration. Use &quot;Ask LISA&quot; on an alert to open the Copilot with the associated asset&apos;s context.</em>
          </p>
        </div>
      </div>
    </div>
  );
}

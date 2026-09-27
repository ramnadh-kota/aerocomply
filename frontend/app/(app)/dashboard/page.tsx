"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { PageHeader } from "@/components/layout/PageHeader";
import { ViewingAsBadge } from "@/components/layout/ViewingAsBadge";
import { AircraftContextLayer } from "@/components/aircraft-visual/AircraftContextLayer";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { StatusBadge, operationalStateBadge, priorityBadge } from "@/components/status/StatusBadge";
import { useSession } from "@/lib/auth/SessionContext";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import {
  controlCenterApi,
  type ControlCenterSummary,
  type ControlCenterFleetOperationRow,
  type OperationalTimelineEvent,
  type ControlCenterAttentionItem,
} from "@/lib/api/controlCenter";
import { AI_NAME, PLATFORM_NAME } from "@/lib/brand";

const ASSET_TYPE_ICONS: Record<string, string> = {
  AIRCRAFT: "✈",
  DRONE: "◆",
  HELICOPTER: "🚁",
  EVTOL: "⚡",
  AAM: "✦",
  OTHER: "▤",
};

export default function DashboardPage() {
  const { accessToken, isAuthenticated, sessionType } = useSession();
  const [summary, setSummary] = useState<ControlCenterSummary | null>(null);
  const [fleetOps, setFleetOps] = useState<ControlCenterFleetOperationRow[]>([]);
  const [timeline, setTimeline] = useState<OperationalTimelineEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<NormalizedApiError | null>(null);
  const [asOf, setAsOf] = useState<string | null>(null);
  const [timelineFilter, setTimelineFilter] = useState<string>("ALL");

  useEffect(() => {
    if (!isAuthenticated) {
      setLoading(false);
      return;
    }

    if (sessionType === "DEMO") {
      setSummary({
        total_aircraft: 12,
        operational: 9,
        under_maintenance: 2,
        aog: 1,
        open_work_orders_total: 4,
        open_deferred_items_total: 2,
        open_part_shortages_total: 1,
        total_assets: 24,
        operational_states: {
          AVAILABLE: 16,
          IN_MISSION: 3,
          MAINTENANCE: 3,
          UNDER_INSPECTION: 1,
          GROUNDED: 1,
        },
        fleet_health: {
          total_assets: 24,
          ready_count: 19,
          restricted_count: 5,
          maintenance_due_count: 4,
          grounded_count: 1,
          available_count: 16,
          in_mission_count: 3,
          unknown_count: 0,
          asset_class_counts: {
            AIRCRAFT: 8,
            DRONE: 12,
            HELICOPTER: 2,
            EVTOL: 2,
          },
        },
        operational_activity: {
          flights_today: 6,
          flights_this_week: 38,
          total_flight_hours: 1420.5,
          total_cycles: 2840,
          total_flights: 512,
          active_missions: 3,
        },
        attention_items: [
          {
            id: "demo-att-1",
            asset_id: "demo-dr-019",
            registration: "DR-019",
            asset_type: "DRONE",
            priority: "CRITICAL",
            category: "INSPECTION",
            title: "Overdue 100-Hour Structural Inspection",
            reason: "Inspection interval exceeded by 4.2 flight hours.",
            blocking_condition: "Inspection INS-104 Overdue",
            recommended_action: "Perform structural integrity check and upload non-destructive testing (NDT) evidence.",
            link_href: "/assets",
          },
          {
            id: "demo-att-2",
            asset_id: "demo-vt-abc",
            registration: "VT-ABC",
            asset_type: "AIRCRAFT",
            priority: "HIGH",
            category: "FINDING",
            title: "Hydraulic System Minor Pressure Drop",
            reason: "High severity finding discovered during pre-flight sector.",
            blocking_condition: "Finding FND-892 (HIGH)",
            recommended_action: "Inspect line B connector, replace seal, and record corrective disposition.",
            link_href: "/findings",
          },
          {
            id: "demo-att-3",
            asset_id: "demo-dr-004",
            registration: "DR-004",
            asset_type: "DRONE",
            priority: "MEDIUM",
            category: "BATTERY",
            title: "Battery Approaching Lifecycle Limit",
            reason: "Battery pack cycle count at 285/300 cycles (95%).",
            blocking_condition: null,
            recommended_action: "Schedule battery replacement before next mission sortie.",
            link_href: "/drones",
          },
        ],
        daily_brief: {
          date_str: new Date().toLocaleDateString(undefined, { day: "2-digit", month: "long", year: "numeric" }),
          total_assets: 24,
          ready_assets: 19,
          attention_required_count: 3,
          restricted_assets: 5,
          maintenance_due_count: 4,
          pending_inspections_count: 2,
          open_findings_count: 2,
          summary_headline: "3 operational priorities require attention across the fleet.",
          key_bullet_points: [
            "5 assets are currently restricted or under maintenance.",
            "2 open findings require technical disposition.",
            "4 active work orders in progress across the fleet.",
          ],
          generated_at: new Date().toISOString(),
        },
        readiness_distribution: { READY: 19, BLOCKED: 5, UNKNOWN: 0 },
        compliance_distribution: { COMPLIANT: 20, REVIEW_REQUIRED: 3, NON_COMPLIANT: 1 },
      });
      setAsOf("Demo Environment (Deterministic Synthetic Fleet)");
      setLoading(false);
      return;
    }

    if (!accessToken) {
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);
    Promise.all([
      controlCenterApi.getSummary(accessToken),
      controlCenterApi.getFleetOperations(accessToken).catch(() => []),
      controlCenterApi.getTimeline(accessToken, { limit: 25 }).catch(() => []),
    ])
      .then(([summ, ops, time]) => {
        setSummary(summ);
        setFleetOps(ops);
        setTimeline(time);
        setAsOf(new Date().toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" }));
      })
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setLoading(false));
  }, [accessToken, isAuthenticated, sessionType]);

  const health = summary?.fleet_health;
  const activity = summary?.operational_activity;
  const brief = summary?.daily_brief;
  const attentionItems = summary?.attention_items ?? [];

  const filteredTimeline = timeline.filter((e) => {
    if (timelineFilter === "ALL") return true;
    if (timelineFilter === "FLIGHTS") return e.event_type === "FLIGHT_SORTIE";
    if (timelineFilter === "MAINTENANCE") return e.event_type.startsWith("WORK_ORDER");
    if (timelineFilter === "FINDINGS") return e.event_type.startsWith("FINDING");
    if (timelineFilter === "COMPONENTS") return e.event_type.startsWith("COMPONENT");
    return true;
  });

  return (
    <div className="ac-page">
      <AircraftContextLayer showGrid />
      <PageHeader
        title="Operational Command Center"
        subtitle="Real-time aerospace command, fleet health, maintenance readiness, and grounded intelligence."
        actions={<ViewingAsBadge />}
      />

      <RealDataPanel
        loading={loading}
        error={error}
        isEmpty={!loading && !error && (!summary || summary.total_assets === 0)}
        emptyMessage="No assets registered yet. Add assets or import legacy flight records to activate Command Center."
      >
        {/* 1. Daily Operational Briefing Banner */}
        {brief && (
          <div
            className="ac-card ac-card-glass"
            style={{
              marginBottom: 20,
              padding: "20px 24px",
              borderColor: "var(--ac-accent)",
              background: "linear-gradient(135deg, rgba(17, 24, 39, 0.85) 0%, rgba(31, 41, 55, 0.6) 100%)",
            }}
          >
            <div className="ac-flex ac-justify-between ac-items-center" style={{ marginBottom: 8, flexWrap: "wrap", gap: 8 }}>
              <div className="ac-flex ac-items-center ac-gap-2">
                <span style={{ fontSize: "1.1rem" }}>⚡</span>
                <span className="ac-eyebrow" style={{ margin: 0, letterSpacing: "1px", fontWeight: 700 }}>
                  KOTA OPERATIONAL BRIEF · {brief.date_str}
                </span>
              </div>
              <span className="ac-text-sm ac-text-muted">
                {asOf ? `Updated ${asOf}` : "Grounded Live Tenant Truth"}
              </span>
            </div>
            <h3 style={{ margin: "4px 0 10px 0", fontSize: "1.15rem", fontWeight: 700, color: "#fff" }}>
              {brief.summary_headline}
            </h3>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
                gap: 10,
                marginBottom: 14,
              }}
            >
              <div style={{ background: "rgba(16, 185, 129, 0.1)", border: "1px solid rgba(16, 185, 129, 0.3)", padding: "8px 12px", borderRadius: 8 }}>
                <div style={{ fontSize: "0.7rem", color: "#10b981", textTransform: "uppercase", fontWeight: 600 }}>Ready Assets</div>
                <div style={{ fontSize: "1.4rem", fontWeight: 800, color: "#10b981" }}>{brief.ready_assets} <span style={{ fontSize: "0.8rem", color: "#9ca3af" }}>/ {brief.total_assets}</span></div>
              </div>
              <div style={{ background: "rgba(239, 68, 68, 0.1)", border: "1px solid rgba(239, 68, 68, 0.3)", padding: "8px 12px", borderRadius: 8 }}>
                <div style={{ fontSize: "0.7rem", color: "#ef4444", textTransform: "uppercase", fontWeight: 600 }}>Restricted / Blocked</div>
                <div style={{ fontSize: "1.4rem", fontWeight: 800, color: "#ef4444" }}>{brief.restricted_assets}</div>
              </div>
              <div style={{ background: "rgba(245, 158, 11, 0.1)", border: "1px solid rgba(245, 158, 11, 0.3)", padding: "8px 12px", borderRadius: 8 }}>
                <div style={{ fontSize: "0.7rem", color: "#f59e0b", textTransform: "uppercase", fontWeight: 600 }}>Maintenance Due</div>
                <div style={{ fontSize: "1.4rem", fontWeight: 800, color: "#f59e0b" }}>{brief.maintenance_due_count}</div>
              </div>
              <div style={{ background: "rgba(56, 189, 248, 0.1)", border: "1px solid rgba(56, 189, 248, 0.3)", padding: "8px 12px", borderRadius: 8 }}>
                <div style={{ fontSize: "0.7rem", color: "#38bdf8", textTransform: "uppercase", fontWeight: 600 }}>Open Findings</div>
                <div style={{ fontSize: "1.4rem", fontWeight: 800, color: "#38bdf8" }}>{brief.open_findings_count}</div>
              </div>
            </div>

            <ul style={{ margin: "0 0 12px 18px", padding: 0, fontSize: "0.875rem", color: "#d1d5db" }}>
              {brief.key_bullet_points.map((pt, i) => (
                <li key={i} style={{ marginBottom: 4 }}>{pt}</li>
              ))}
            </ul>

            <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
              <Link href="/ai" className="ac-btn ac-btn-primary">
                Ask {AI_NAME} Intelligence →
              </Link>
              <Link href="/assets" className="ac-btn">
                Fleet Operations Workspace
              </Link>
              <Link href="/maintenance/control-center" className="ac-btn">
                Maintenance Control Center
              </Link>
            </div>
          </div>
        )}

        {/* 2. Fleet Health & Operational Activity Metrics */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 12, marginBottom: 20 }}>
          <div className="ac-kpi-card-real">
            <p className="ac-kpi-label">Total Fleet Airframes</p>
            <p className="ac-kpi-value">{health?.total_assets ?? summary?.total_assets ?? 0}</p>
            <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
              {health?.available_count ?? 0} Available · {health?.in_mission_count ?? 0} In Mission
            </p>
          </div>
          <div className="ac-kpi-card-real">
            <p className="ac-kpi-label">Flight Hours (TTAF)</p>
            <p className="ac-kpi-value" style={{ color: "var(--ac-primary, #38bdf8)" }}>
              {activity?.total_flight_hours ?? 0} <span style={{ fontSize: "0.9rem" }}>hrs</span>
            </p>
            <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
              {activity?.total_cycles ?? 0} total cycles logged
            </p>
          </div>
          <div className="ac-kpi-card-real">
            <p className="ac-kpi-label">Sorties Flown Today</p>
            <p className="ac-kpi-value">{activity?.flights_today ?? 0}</p>
            <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
              {activity?.flights_this_week ?? 0} flights this week
            </p>
          </div>
          <div className="ac-kpi-card-real">
            <p className="ac-kpi-label">Active Missions</p>
            <p className="ac-kpi-value" style={{ color: "#10b981" }}>{activity?.active_missions ?? 0}</p>
            <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
              currently airborne / in progress
            </p>
          </div>
          <div className="ac-kpi-card-real">
            <p className="ac-kpi-label">Open Maintenance WOs</p>
            <p className="ac-kpi-value" style={{ color: (summary?.open_work_orders_total ?? 0) > 0 ? "#f59e0b" : "#10b981" }}>
              {summary?.open_work_orders_total ?? 0}
            </p>
            <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
              {summary?.open_part_shortages_total ?? 0} part shortages
            </p>
          </div>
        </div>

        {/* 3. Attention Required Priority Queue */}
        <section className="ac-section" style={{ marginBottom: 24 }}>
          <div className="ac-section-header">
            <div>
              <h2 className="ac-h2" style={{ margin: 0 }}>What Needs Attention Now</h2>
              <p className="ac-subtitle" style={{ margin: 0 }}>
                Prioritized aerospace operational items requiring immediate operator action.
              </p>
            </div>
            <span className="ac-text-sm ac-text-muted">{attentionItems.length} active priority item(s)</span>
          </div>

          {attentionItems.length === 0 ? (
            <div className="ac-card" style={{ padding: "20px", textAlign: "center" }}>
              <p style={{ color: "#10b981", fontWeight: 600, margin: 0 }}>
                ✓ Zero active blockers. All aircraft and drone assets nominal.
              </p>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {attentionItems.slice(0, 6).map((item) => {
                const pBadge = priorityBadge(item.priority);
                return (
                  <div
                    key={item.id}
                    className="ac-card"
                    style={{
                      padding: "16px 20px",
                      background: item.priority === "CRITICAL" ? "rgba(239, 68, 68, 0.06)" : "rgba(31, 41, 55, 0.7)",
                      border: item.priority === "CRITICAL" ? "1px solid rgba(239, 68, 68, 0.4)" : "1px solid #374151",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 12 }}>
                      <div style={{ flex: 1, minWidth: 260 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                          <StatusBadge {...pBadge} />
                          <span style={{ fontSize: "0.75rem", background: "#374151", padding: "2px 8px", borderRadius: 4, textTransform: "uppercase" }}>
                            {item.category}
                          </span>
                          {item.registration && (
                            <strong style={{ fontSize: "0.95rem", color: "#38bdf8" }}>
                              {item.registration}
                            </strong>
                          )}
                          {item.asset_type && (
                            <span style={{ fontSize: "0.75rem", color: "#9ca3af" }}>
                              [{item.asset_type}]
                            </span>
                          )}
                        </div>
                        <h4 style={{ margin: "0 0 4px 0", fontSize: "1rem", fontWeight: 700 }}>
                          {item.title}
                        </h4>
                        <p style={{ margin: "0 0 6px 0", color: "#d1d5db", fontSize: "0.85rem" }}>
                          {item.reason}
                        </p>
                        {item.blocking_condition && (
                          <div style={{ fontSize: "0.8rem", color: "#f87171", marginBottom: 4 }}>
                            <strong>Blocking Condition:</strong> {item.blocking_condition}
                          </div>
                        )}
                        {item.recommended_action && (
                          <div style={{ fontSize: "0.8rem", color: "#93c5fd" }}>
                            <strong>Recommended Action:</strong> {item.recommended_action}
                          </div>
                        )}
                      </div>

                      <div>
                        {item.link_href ? (
                          <Link href={item.link_href} className="ac-btn ac-btn-primary" style={{ padding: "6px 14px", fontSize: "0.85rem" }}>
                            Take Action →
                          </Link>
                        ) : item.asset_id ? (
                          <Link href={`/assets/${item.asset_id}`} className="ac-btn ac-btn-primary" style={{ padding: "6px 14px", fontSize: "0.85rem" }}>
                            View Asset →
                          </Link>
                        ) : null}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        {/* 4. Fleet Operations Workspace Strip */}
        {fleetOps.length > 0 && (
          <section className="ac-section" style={{ marginBottom: 24 }}>
            <div className="ac-section-header">
              <div>
                <h2 className="ac-h2" style={{ margin: 0 }}>Fleet Operations</h2>
                <p className="ac-subtitle" style={{ margin: 0 }}>
                  Live operational tracking across all airframe classes.
                </p>
              </div>
              <Link href="/assets" className="ac-text-sm">View Full Fleet Registry →</Link>
            </div>

            <div className="ac-card" style={{ padding: 0, overflowX: "auto" }}>
              <table className="ac-table" style={{ width: "100%" }}>
                <thead>
                  <tr>
                    <th>Identifier</th>
                    <th>Class</th>
                    <th>Operational State</th>
                    <th>Readiness</th>
                    <th>Flight Hours</th>
                    <th>Cycles</th>
                    <th>Last Flight</th>
                    <th>Next Required Action</th>
                  </tr>
                </thead>
                <tbody>
                  {fleetOps.slice(0, 10).map((row) => (
                    <tr key={row.asset_id}>
                      <td>
                        <Link href={`/assets/${row.asset_id}`} className="ac-mono" style={{ fontWeight: 700 }}>
                          {row.registration || "—"}
                        </Link>
                      </td>
                      <td>
                        <span style={{ fontSize: "0.8rem", color: "#38bdf8" }}>
                          {ASSET_TYPE_ICONS[row.asset_type] || "✈"} {row.asset_type}
                        </span>
                      </td>
                      <td>
                        <StatusBadge {...operationalStateBadge(row.operational_state)} />
                      </td>
                      <td>
                        <span
                          style={{
                            fontSize: "0.75rem",
                            fontWeight: 700,
                            padding: "3px 8px",
                            borderRadius: 4,
                            background: row.readiness_state === "READY" ? "rgba(16, 185, 129, 0.2)" : "rgba(239, 68, 68, 0.2)",
                            color: row.readiness_state === "READY" ? "#10b981" : "#ef4444",
                          }}
                        >
                          {row.readiness_state}
                        </span>
                      </td>
                      <td className="ac-mono">{row.total_flight_hours} hrs</td>
                      <td className="ac-mono">{row.total_cycles}</td>
                      <td className="ac-text-sm">
                        {row.last_flight_at ? new Date(row.last_flight_at).toLocaleDateString() : "—"}
                      </td>
                      <td className="ac-text-sm" style={{ color: "#d1d5db" }}>
                        {row.next_action || "Ready"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {/* 5. Unified Operational Timeline */}
        <section className="ac-section" style={{ marginBottom: 24 }}>
          <div className="ac-section-header">
            <div>
              <h2 className="ac-h2" style={{ margin: 0 }}>Unified Operational Timeline</h2>
              <p className="ac-subtitle" style={{ margin: 0 }}>
                Chronological live feed of flight sorties, maintenance completions, findings, and component installations.
              </p>
            </div>
            {/* Timeline Filter Pills */}
            <div style={{ display: "flex", gap: 6 }}>
              {["ALL", "FLIGHTS", "MAINTENANCE", "FINDINGS", "COMPONENTS"].map((f) => (
                <button
                  key={f}
                  type="button"
                  onClick={() => setTimelineFilter(f)}
                  style={{
                    fontSize: "0.75rem",
                    padding: "4px 10px",
                    borderRadius: 14,
                    border: "1px solid #374151",
                    background: timelineFilter === f ? "var(--ac-primary, #38bdf8)" : "#1f2937",
                    color: timelineFilter === f ? "#000" : "#9ca3af",
                    fontWeight: timelineFilter === f ? 700 : 500,
                    cursor: "pointer",
                  }}
                >
                  {f}
                </button>
              ))}
            </div>
          </div>

          {filteredTimeline.length === 0 ? (
            <div className="ac-card" style={{ padding: 20, textAlign: "center" }}>
              <p style={{ color: "#9ca3af", fontStyle: "italic", margin: 0 }}>
                No recent timeline events recorded.
              </p>
            </div>
          ) : (
            <div className="ac-card" style={{ padding: 0 }}>
              <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
                {filteredTimeline.map((ev, i) => (
                  <li
                    key={ev.event_id}
                    style={{
                      padding: "12px 18px",
                      borderBottom: i < filteredTimeline.length - 1 ? "1px solid #374151" : "none",
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "flex-start",
                      gap: 12,
                    }}
                  >
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 2 }}>
                        <span style={{ fontSize: "0.7rem", background: "#374151", padding: "2px 6px", borderRadius: 4, textTransform: "uppercase" }}>
                          {ev.event_type.replace(/_/g, " ")}
                        </span>
                        {ev.asset_registration && (
                          <Link href={`/assets/${ev.asset_id}`} className="ac-mono" style={{ fontWeight: 700 }}>
                            {ev.asset_registration}
                          </Link>
                        )}
                        <strong style={{ fontSize: "0.9rem" }}>{ev.title}</strong>
                      </div>
                      <p style={{ margin: 0, fontSize: "0.85rem", color: "#9ca3af" }}>
                        {ev.description}
                      </p>
                    </div>
                    <div style={{ fontSize: "0.75rem", color: "#6b7280", whiteSpace: "nowrap" }}>
                      {new Date(ev.occurred_at).toLocaleDateString(undefined, { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      </RealDataPanel>
    </div>
  );
}

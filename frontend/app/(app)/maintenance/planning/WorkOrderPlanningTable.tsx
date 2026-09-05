"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { StatusBadge, priorityBadge, riskLevelBadge } from "@/components/status/StatusBadge";
import { getWorkOrderPlanning, getWorkOrderPlanningSummary, getNextMaintenanceActions, type PlanningStatus } from "@/lib/mock/ai/analytics";

// M12.4 — Work Order Planning table + KPI strip. Client-side because the KPI
// cards filter the table in place, matching the pattern already established
// on the Control Tower page. All numbers come from
// lib/mock/ai/analytics.ts#getWorkOrderPlanning[Summary]() — the same
// functions Lisa's planning answers use, so the two can never disagree.

type KpiFilter = "ALL" | "CRITICAL_HIGH" | "READY" | "MATERIAL_BLOCKED" | "TECHNICIAN_REQUIRED" | "OVERDUE" | "AOG" | "IN_PROGRESS";

const PLANNING_STATUS_LABEL: Record<PlanningStatus, string> = {
  READY: "Ready",
  MATERIAL_BLOCKED: "Material Blocked",
  TECHNICIAN_BLOCKED: "Technician Required",
  BOTH_BLOCKED: "Blocked (Material + Technician)",
  IN_PROGRESS: "In Progress",
  WAITING_INSPECTION: "Waiting Inspection",
  COMPLETED: "Completed",
  CANCELLED: "Cancelled",
};

export function WorkOrderPlanningTable() {
  const [filter, setFilter] = useState<KpiFilter>("ALL");
  const rows = useMemo(() => getWorkOrderPlanning(), []);
  const summary = useMemo(() => getWorkOrderPlanningSummary(), []);
  const nextActions = useMemo(() => getNextMaintenanceActions(), []);

  const filtered = useMemo(() => {
    switch (filter) {
      case "ALL": return rows;
      case "CRITICAL_HIGH": return rows.filter((r) => r.priority === "CRITICAL" || r.priority === "HIGH");
      case "READY": return rows.filter((r) => r.planningStatus === "READY");
      case "MATERIAL_BLOCKED": return rows.filter((r) => r.planningStatus === "MATERIAL_BLOCKED" || r.planningStatus === "BOTH_BLOCKED");
      case "TECHNICIAN_REQUIRED": return rows.filter((r) => r.planningStatus === "TECHNICIAN_BLOCKED" || r.planningStatus === "BOTH_BLOCKED");
      case "OVERDUE": return rows.filter((r) => r.daysOverdue !== null);
      case "AOG": return rows.filter((r) => r.aogAircraft);
      case "IN_PROGRESS": return rows.filter((r) => r.planningStatus === "IN_PROGRESS" || r.planningStatus === "WAITING_INSPECTION");
      default: return rows;
    }
  }, [rows, filter]);

  const kpis: { label: string; value: number; filter: KpiFilter }[] = [
    { label: "Open Work Orders", value: summary.openWorkOrders, filter: "ALL" },
    { label: "Critical / High Priority", value: summary.criticalHigh, filter: "CRITICAL_HIGH" },
    { label: "Ready to Start", value: summary.readyToStart, filter: "READY" },
    { label: "Material Blocked", value: summary.materialBlocked, filter: "MATERIAL_BLOCKED" },
    { label: "Technician Assignment Required", value: summary.technicianAssignmentRequired, filter: "TECHNICIAN_REQUIRED" },
    { label: "Overdue / Aging", value: summary.overdue, filter: "OVERDUE" },
    { label: "AOG-Related Work", value: summary.aogRelated, filter: "AOG" },
    { label: "Planned / In Progress", value: summary.plannedInProgress, filter: "IN_PROGRESS" },
  ];

  return (
    <>
      <section className="ac-section">
        <div className="ac-kpi-grid">
          {kpis.map((k) => (
            <button
              key={k.label}
              onClick={() => setFilter(k.filter)}
              className="ac-kpi-card"
              style={{ textAlign: "left", cursor: "pointer", border: filter === k.filter ? "1px solid var(--ac-accent)" : undefined }}
            >
              <p className="ac-kpi-label">{k.label}</p>
              <p className="ac-kpi-value">{k.value}</p>
            </button>
          ))}
        </div>
        {filter !== "ALL" && (
          <p className="ac-text-sm ac-text-muted" style={{ marginTop: 8 }}>
            Filtered by {kpis.find((k) => k.filter === filter)?.label}. <button className="ac-btn" style={{ padding: "2px 8px" }} onClick={() => setFilter("ALL")}>Clear filter</button>
          </p>
        )}
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Work Order Planning</h2>
        <div className="ac-card" style={{ padding: 0, overflowX: "auto" }}>
          <table className="ac-table">
            <thead>
              <tr>
                <th>Work Order</th>
                <th>Aircraft</th>
                <th>Task / Description</th>
                <th>Priority</th>
                <th>Status</th>
                <th>Material Readiness</th>
                <th>Technician</th>
                <th>Age</th>
                <th>Risk</th>
                <th>Recommended Action</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => {
                const p = priorityBadge(r.priority);
                const risk = riskLevelBadge(r.risk);
                return (
                  <tr key={r.workOrderId}>
                    <td><Link href={`/maintenance/planning/${r.workOrderId}`} className="ac-mono">{r.workOrderNumber}</Link></td>
                    <td><Link href={`/aircraft/${r.aircraftId}`}>{r.aircraftRegistration}</Link></td>
                    <td className="ac-text-sm">{r.title}</td>
                    <td><StatusBadge status={p.status} label={p.label} /></td>
                    <td>{PLANNING_STATUS_LABEL[r.planningStatus]}</td>
                    <td>
                      {r.shortParts.length > 0 ? (
                        <span style={{ color: "var(--ac-status-non-compliant)" }}>{r.shortParts.map((sp) => sp.partNumber).join(", ")} unavailable</span>
                      ) : (
                        "Ready"
                      )}
                    </td>
                    <td>{r.assignedTechnicianName ?? <span className="ac-text-muted">Unassigned</span>}</td>
                    <td>{r.daysOverdue !== null ? <span style={{ color: "var(--ac-status-non-compliant)" }}>{r.daysOverdue}d overdue</span> : `Due ${r.dueDate}`}</td>
                    <td><StatusBadge status={risk.status} label={risk.label} /></td>
                    <td className="ac-text-sm">{r.recommendedAction}</td>
                  </tr>
                );
              })}
              {filtered.length === 0 && (
                <tr><td colSpan={10} className="ac-text-sm ac-text-muted" style={{ padding: 12 }}>No work orders match this filter.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>What Should Maintenance Do Next?</h2>
        <div className="ac-card">
          <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
            {nextActions.map((a, i) => <li key={i}>{a}</li>)}
          </ul>
        </div>
      </section>
    </>
  );
}

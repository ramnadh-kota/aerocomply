"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge, operationalStatusBadge, riskLevelBadge, priorityBadge, workOrderStatusBadge } from "@/components/status/StatusBadge";
import { PLATFORM_NAME } from "@/lib/brand";
import {
  getMaintenanceControlCenter,
  getMaintenanceControlCenterSummary,
  getControlTowerFleet,
  getExecutionQueue,
  getMaterialShortages,
  getDiscrepancyGroups,
  getProcurementActionsForShortages,
  getReleaseQueue,
  getAutomationQueue,
  getQuarantinedParts,
  getOpenDeferredItems,
  getDeferredRiskSummary,
  getFleetMaintenanceDueSummary,
  getEvidenceBlockedWorkOrders,
  type ControlCenterPriority,
  type ExecutionActionType,
} from "@/lib/mock/ai/analytics";
import { workOrderRepository } from "@/lib/domain/repositories";
import { getCurrentUser } from "@/lib/domain/currentUser";
import { useMroState } from "@/lib/mro-state/MroStateContext";
import { workOrders } from "@/lib/mock/workOrders";
import { getAircraftByRegistration } from "@/lib/mock/aircraft";
import { ActionHistory, type ActionHistoryLink } from "@/components/audit/ActionHistory";
import type { AuditEvent } from "@/lib/mock/types";

// M12.5 — Maintenance Control Center. A pure aggregation view: every number
// and reason on this page is read from the same analytics functions the
// Control Tower, Work Order Planning, Material Readiness, and Discrepancy
// Intelligence pages already call (see getMaintenanceControlCenter[Summary]
// in lib/mock/ai/analytics.ts). No new calculation lives on this page.

const PRIORITY_BADGE: Record<ControlCenterPriority, { status: Parameters<typeof StatusBadge>[0]["status"]; label: string }> = {
  CRITICAL: { status: "NON_COMPLIANT", label: "CRITICAL" },
  HIGH: { status: "REVIEW_REQUIRED", label: "HIGH" },
  MEDIUM: { status: "PENDING", label: "MEDIUM" },
  LOW: { status: "COMPLIANT", label: "LOW" },
  UNKNOWN: { status: "INSUFFICIENT_DATA", label: "UNKNOWN" },
};

export default function MaintenanceControlCenterPage() {
  const { addAuditEvent, auditLog } = useMroState();
  const current = getCurrentUser();
  const reviewed = useRef(false);
  const [, setVersion] = useState(0);

  const summary = getMaintenanceControlCenterSummary();
  const queue = getMaintenanceControlCenter();
  const fleet = getControlTowerFleet();
  const executionQueue = getExecutionQueue().filter((r) => r.planningStatus !== "COMPLETED" && r.planningStatus !== "CANCELLED");
  const materialBlockers = getMaterialShortages();
  const discrepancies = getDiscrepancyGroups().filter((g) => g.openCount > 0);
  const procurementHandoff = getProcurementActionsForShortages();
  const releaseQueue = getReleaseQueue();
  const maintenanceDueSummary = getFleetMaintenanceDueSummary();

  const recentActions = [...auditLog]
    .filter((e) => e.action.startsWith("maintenance."))
    .sort((a, b) => b.timestamp.localeCompare(a.timestamp))
    .slice(0, 10);

  function linkForAction(e: AuditEvent): ActionHistoryLink | null {
    const wo = workOrders.find((w) => w.workOrderNumber === e.objectLabel);
    if (wo) return { label: `View ${wo.workOrderNumber}`, href: `/maintenance/planning/${wo.id}` };
    const ac = getAircraftByRegistration(e.objectLabel);
    if (ac) return { label: "View Aircraft", href: `/aircraft/${ac.id}` };
    if (e.objectType === "DiscrepancyGroup") return { label: "Investigate →", href: "/maintenance/discrepancies" };
    return null;
  }

  function runAction(workOrderId: string, workOrderNumber: string, actionType: ExecutionActionType) {
    if (actionType === "START_WORK") {
      const updated = workOrderRepository.startWorkOrder(workOrderId);
      if (!updated) return;
      addAuditEvent({ actor: current?.user.name ?? "Unknown User", actorRole: "Maintenance", action: "maintenance.work_started", objectType: "WorkOrder", objectLabel: workOrderNumber, previousState: null, newState: "IN_PROGRESS" });
    } else if (actionType === "COMPLETE") {
      const updated = workOrderRepository.completeWorkOrder(workOrderId, new Date().toISOString().slice(0, 10));
      if (!updated) return;
      addAuditEvent({ actor: current?.user.name ?? "Unknown User", actorRole: "Maintenance", action: "maintenance.work_order_completed", objectType: "WorkOrder", objectLabel: workOrderNumber, previousState: null, newState: "COMPLETED" });
    } else if (actionType === "ESCALATE") {
      const updated = workOrderRepository.escalateWorkOrder(workOrderId);
      if (!updated) return;
      addAuditEvent({ actor: current?.user.name ?? "Unknown User", actorRole: "Maintenance", action: "maintenance.work_order_escalated", objectType: "WorkOrder", objectLabel: workOrderNumber, previousState: null, newState: "CRITICAL", reason: "Escalated from Maintenance Control Center." });
    } else {
      return;
    }
    setVersion((v) => v + 1);
  }

  useEffect(() => {
    if (reviewed.current) return;
    reviewed.current = true;
    addAuditEvent({
      actor: current?.user.name ?? "Unknown User",
      actorRole: "Maintenance",
      action: "maintenance.control_center_reviewed",
      objectType: "MaintenanceControlCenter",
      objectLabel: "Maintenance Control Center",
      previousState: null,
      newState: null,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const kpis: { label: string; value: number; href: string; linkLabel: string }[] = [
    { label: "Aircraft Requiring Attention", value: summary.aircraftRequiringAttention, href: "/maintenance/control-tower", linkLabel: "View Control Tower →" },
    { label: "AOG Aircraft", value: summary.aogAircraft, href: "/maintenance/control-tower", linkLabel: "View AOG Aircraft →" },
    { label: "Critical Work Orders", value: summary.criticalWorkOrders, href: "/maintenance/planning", linkLabel: "View Planning Center →" },
    { label: "Critical Discrepancies", value: summary.criticalDiscrepancies, href: "/maintenance/discrepancies", linkLabel: "View Discrepancies →" },
    { label: "Material Shortages", value: summary.materialShortages, href: "/maintenance/material-readiness", linkLabel: "View Material Readiness →" },
    { label: "Work Orders Waiting for Parts", value: summary.workOrdersWaitingForParts, href: "/maintenance/planning", linkLabel: "View Planning Center →" },
    { label: "Overdue / At-Risk Maintenance", value: summary.overdueAtRiskMaintenance, href: "/maintenance/planning", linkLabel: "View Planning Center →" },
    { label: "High-Risk Aircraft", value: summary.highRiskAircraft, href: "/maintenance/control-tower", linkLabel: "View Control Tower →" },
    // M13 — release queue: work orders whose technician step is done but
    // are not yet RELEASED (inspection pending/incomplete), read from the
    // same getExecutionState/getSafetyGatesForWorkOrder derivation the
    // Planning detail page uses — never a second "released" calculation.
    { label: "Release Queue", value: releaseQueue.length, href: "/maintenance/planning", linkLabel: "View Planning Center →" },
    // M14.14 — unified command center: consolidates the M14.2-M14.13
    // additions (automation queue, quarantine, deferred/MEL) onto the one
    // existing operations command page, reusing their derivations exactly.
    { label: "Automation Queue", value: getAutomationQueue().length, href: "/automation", linkLabel: "Open Automation Queue →" },
    { label: "Quarantined Parts", value: getQuarantinedParts().length, href: "/maintenance/parts", linkLabel: "View Parts →" },
    { label: "Open Deferred Items", value: getOpenDeferredItems().length, href: "/maintenance/defects", linkLabel: "View Defects →" },
    // M18 — deferred-item operational status, reusing getDeferredRiskSummary
    // (the same function /aircraft and Lisa read).
    { label: "Deferred Items Overdue", value: getDeferredRiskSummary().overdue, href: "/maintenance/defects", linkLabel: "View Defects →" },
    // M17 — maintenance due engine KPIs, reusing getFleetMaintenanceDueSummary
    // (the same function the /maintenance-program page and Lisa read).
    { label: "Overdue Maintenance", value: maintenanceDueSummary.overdue, href: "/maintenance-program", linkLabel: "Open Maintenance Program →" },
    { label: "Maintenance Due Soon", value: maintenanceDueSummary.dueSoon + maintenanceDueSummary.due, href: "/maintenance-program", linkLabel: "Open Maintenance Program →" },
    { label: "Maintenance Due Status Unknown", value: maintenanceDueSummary.unknown, href: "/maintenance-program", linkLabel: "Open Maintenance Program →" },
    // M28 — evidence blockers, reusing getEvidenceBlockedWorkOrders (the
    // same function Lisa and the Automation Queue read).
    { label: "Evidence Blockers", value: getEvidenceBlockedWorkOrders().length, href: "/maintenance/planning", linkLabel: "View Planning Center →" },
  ];

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Maintenance", href: "/maintenance/control-tower" }, { label: "Control Center" }]} />
      <div className="ac-section-header">
        <div>
          <p className="ac-eyebrow" style={{ marginBottom: 4 }}>{PLATFORM_NAME}</p>
          <h1 className="ac-h1">Maintenance Control Center</h1>
          <p className="ac-subtitle" style={{ fontWeight: 600 }}>Maintenance Operations Command</p>
          <p className="ac-subtitle">
            A consolidated operational view of fleet readiness, maintenance risk, materials, discrepancies and execution priorities.
            Every figure below is read from the Control Tower, Work Order Planning, Material Readiness, and Discrepancy
            Intelligence pages — nothing is calculated separately here.
          </p>
        </div>
      </div>

      <section className="ac-section">
        <div className="ac-kpi-grid">
          {kpis.map((k) => (
            <div key={k.label} className="ac-kpi-card">
              <p className="ac-kpi-label">{k.label}</p>
              <p className="ac-kpi-value">{k.value}</p>
              <Link href={k.href} className="ac-text-sm" style={{ display: "block", marginTop: 4 }}>{k.linkLabel}</Link>
            </div>
          ))}
        </div>
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>What Needs Attention Now</h2>
        <div className="ac-flex ac-flex-col ac-gap-3">
          {queue.slice(0, 12).map((item, i) => {
            const badge = PRIORITY_BADGE[item.priority];
            return (
              <div key={`${item.category}-${item.label}-${i}`} className="ac-card">
                <div className="ac-flex ac-justify-between" style={{ flexWrap: "wrap", gap: 10 }}>
                  <div>
                    <div className="ac-flex ac-items-center ac-gap-2" style={{ marginBottom: 4 }}>
                      <StatusBadge status={badge.status} label={badge.label} />
                      {item.aircraftRegistration && <span className="ac-mono ac-text-sm">{item.aircraftRegistration}</span>}
                      <span className="ac-mono ac-text-sm">{item.label}</span>
                    </div>
                    <p className="ac-text-sm" style={{ margin: "0 0 4px", fontWeight: 600 }}>{item.issue}</p>
                    <ul style={{ margin: "0 0 4px", paddingLeft: 18, fontSize: 13 }}>
                      {item.reasons.map((r) => <li key={r}>→ {r}</li>)}
                    </ul>
                    <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 2px" }}>Current status: {item.status}</p>
                    <p className="ac-text-sm" style={{ margin: "0 0 2px", fontWeight: 600 }}>Recommended action: {item.recommendedAction}</p>
                    <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Source: {item.source}</p>
                  </div>
                  <Link href={item.href} className="ac-btn">
                    {item.category === "MATERIAL" ? "View Material Readiness" : item.category === "DISCREPANCY" ? "Investigate →" : "View Work Order"}
                  </Link>
                </div>
              </div>
            );
          })}
          {queue.length === 0 && <p className="ac-text-sm ac-text-muted">No item currently requires attention.</p>}
        </div>
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Fleet Readiness</h2>
        <div className="ac-card" style={{ padding: 0, overflowX: "auto" }}>
          <table className="ac-table">
            <thead>
              <tr><th>Aircraft</th><th>Model</th><th>Operational Status</th><th>Risk</th><th>Open WOs</th><th>Critical Defects</th><th>Material Readiness</th><th>Next Action</th></tr>
            </thead>
            <tbody>
              {fleet.map((f) => {
                const opBadge = operationalStatusBadge(f.operationalStatus);
                const riskBadge = riskLevelBadge(f.risk.risk);
                return (
                  <tr key={f.aircraftId}>
                    <td><Link href={`/aircraft/${f.aircraftId}`} className="ac-mono">{f.registration}</Link></td>
                    <td>{f.model}</td>
                    <td><StatusBadge status={opBadge.status} label={opBadge.label} /></td>
                    <td><StatusBadge status={riskBadge.status} label={riskBadge.label} /></td>
                    <td>{f.openWorkOrders}</td>
                    <td>{f.criticalOpenDefects}</td>
                    <td>{f.materialShortageCount > 0 ? `${f.materialShortageCount} shortage(s)` : "Ready"}</td>
                    <td>
                      {f.operationalStatus === "AOG" ? (
                        <Link href={`/maintenance/aog-recovery/${f.aircraftId}`} className="ac-text-sm">AOG Recovery →</Link>
                      ) : (
                        <Link href="/maintenance/control-tower" className="ac-text-sm">View Control Tower →</Link>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Work Orders Requiring Action</h2>
        <p className="ac-text-sm ac-text-muted" style={{ marginBottom: 10 }}>
          Each action below calls the same mutation used on the Planning detail page (workOrderRepository) and creates a real audit
          event. &quot;Assign technician&quot; opens the Planning view, where eligible technicians and their reasons are shown.
        </p>
        <div className="ac-card" style={{ padding: 0, overflowX: "auto" }}>
          <table className="ac-table">
            <thead><tr><th>WO</th><th>Aircraft</th><th>Description</th><th>Priority</th><th>Status</th><th>Age</th><th>Material</th><th>Assigned Technician</th><th>Action</th></tr></thead>
            <tbody>
              {executionQueue.map((r) => {
                const p = priorityBadge(r.priority);
                const s = workOrderStatusBadge(r.status);
                return (
                  <tr key={r.workOrderId}>
                    <td><Link href={`/maintenance/planning/${r.workOrderId}`} className="ac-mono">{r.workOrderNumber}</Link></td>
                    <td>{r.aircraftRegistration}</td>
                    <td className="ac-text-sm">{r.title}</td>
                    <td><StatusBadge status={p.status} label={p.label} /></td>
                    <td><StatusBadge status={s.status} label={s.label} /></td>
                    <td>{r.daysOverdue !== null ? `${r.daysOverdue}d overdue` : `Due ${r.dueDate}`}</td>
                    <td>{r.shortParts.length > 0 ? r.shortParts.map((sp) => sp.partNumber).join(", ") : "Ready"}</td>
                    <td>{r.assignedTechnicianName ?? "Insufficient source data."}</td>
                    <td>
                      {r.actionType === "ASSIGN_TECHNICIAN" || r.actionType === "RESOLVE_MATERIAL_BLOCKER" || r.actionType === "REVIEW" ? (
                        <Link
                          href={r.actionType === "RESOLVE_MATERIAL_BLOCKER" ? "/maintenance/material-readiness" : `/maintenance/planning/${r.workOrderId}`}
                          className="ac-btn"
                          style={{ padding: "2px 8px" }}
                        >
                          {r.actionLabel}
                        </Link>
                      ) : (
                        <button className="ac-btn ac-btn-primary" style={{ padding: "2px 8px" }} onClick={() => runAction(r.workOrderId, r.workOrderNumber, r.actionType)}>
                          {r.actionLabel}
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
              {executionQueue.length === 0 && <tr><td colSpan={9} className="ac-text-sm ac-text-muted" style={{ padding: 12 }}>No open work order currently requires action.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Material Blockers</h2>
        <div className="ac-card" style={{ padding: 0, overflowX: "auto" }}>
          <table className="ac-table">
            <thead><tr><th>Part</th><th>Description</th><th>Aircraft</th><th>Work Order</th><th>Material Status</th><th>Vendor</th><th>Price</th><th>Lead Time</th><th>Procurement Status</th><th>Action</th></tr></thead>
            <tbody>
              {materialBlockers.map((r) => (
                <tr key={`${r.workOrderId}-${r.partNumber}`}>
                  <td className="ac-mono">{r.partNumber}</td>
                  <td className="ac-text-sm">{r.description}</td>
                  <td>{r.aircraftRegistration}</td>
                  <td><Link href={`/maintenance/planning/${r.workOrderId}`} className="ac-mono">{r.workOrderNumber}</Link></td>
                  <td>{r.materialStatus}</td>
                  <td className="ac-text-sm">{r.bestVendor?.vendorName ?? "Insufficient source data."}</td>
                  <td>{r.bestVendor?.unitPrice != null ? `${r.bestVendor.currency ?? ""} ${r.bestVendor.unitPrice}` : "Insufficient source data."}</td>
                  <td>{r.bestVendor?.leadTimeDays != null ? `${r.bestVendor.leadTimeDays} days` : "Insufficient source data."}</td>
                  <td className="ac-text-sm">{r.procurementStatus}</td>
                  <td>
                    <Link href="/maintenance/material-readiness" className="ac-btn" style={{ padding: "2px 8px" }}>
                      {r.bestVendor ? "Add to Procurement Cart" : "Procurement data incomplete"}
                    </Link>
                  </td>
                </tr>
              ))}
              {materialBlockers.length === 0 && <tr><td colSpan={10} className="ac-text-sm ac-text-muted" style={{ padding: 12 }}>No material is currently blocking maintenance.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Discrepancies Requiring Attention</h2>
        <div className="ac-card" style={{ padding: 0, overflowX: "auto" }}>
          <table className="ac-table">
            <thead><tr><th>ATA</th><th>Description</th><th>Occurrences</th><th>Aircraft</th><th>Severity</th><th>Open</th><th>Recurring</th><th>Action</th></tr></thead>
            <tbody>
              {discrepancies.map((g) => (
                <tr key={g.ataChapter}>
                  <td className="ac-mono">{g.ataChapter}</td>
                  <td className="ac-text-sm">{g.defects[0]?.description ?? "Insufficient source data."}</td>
                  <td>{g.occurrences}</td>
                  <td>{g.aircraftCount}</td>
                  <td>{g.highSeverityCount > 0 ? "HIGH/CRITICAL present" : "LOW/MEDIUM only"}</td>
                  <td>{g.openCount}</td>
                  <td>{g.recurringAircraftCount > 0 ? `${g.recurringAircraftCount} aircraft` : "No"}</td>
                  <td><Link href="/maintenance/discrepancies" className="ac-btn" style={{ padding: "2px 8px" }}>Investigate →</Link></td>
                </tr>
              ))}
              {discrepancies.length === 0 && <tr><td colSpan={8} className="ac-text-sm ac-text-muted" style={{ padding: 12 }}>No discrepancy group currently has an open occurrence.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Procurement Handoff</h2>
        <div className="ac-card" style={{ padding: 0, overflowX: "auto" }}>
          <table className="ac-table">
            <thead><tr><th>Part</th><th>Aircraft</th><th>Work Order</th><th>Reason</th><th>Vendor Availability</th><th>Known Price</th><th>Lead Time</th><th>Procurement Status</th><th>Action</th></tr></thead>
            <tbody>
              {procurementHandoff.map((r) => (
                <tr key={`${r.workOrderId}-${r.partNumber}-handoff`}>
                  <td className="ac-mono">{r.partNumber}</td>
                  <td>{r.aircraftRegistration}</td>
                  <td><Link href={`/maintenance/planning/${r.workOrderId}`} className="ac-mono">{r.workOrderNumber}</Link></td>
                  <td className="ac-text-sm">{r.materialStatus === "SHORTAGE" ? "Material shortage" : r.materialStatus === "PARTIAL" ? "Partial availability" : "Availability unknown"}</td>
                  <td className="ac-text-sm">{r.bestVendor?.availabilityStatus.replace(/_/g, " ") ?? "Insufficient source data."}</td>
                  <td>{r.bestVendor?.unitPrice != null ? `${r.bestVendor.currency ?? ""} ${r.bestVendor.unitPrice}` : "Insufficient source data."}</td>
                  <td>{r.bestVendor?.leadTimeDays != null ? `${r.bestVendor.leadTimeDays} days` : "Insufficient source data."}</td>
                  <td className="ac-text-sm">{r.procurementStatus}</td>
                  <td><Link href="/maintenance/material-readiness" className="ac-btn" style={{ padding: "2px 8px" }}>Review Part</Link></td>
                </tr>
              ))}
              {procurementHandoff.length === 0 && <tr><td colSpan={9} className="ac-text-sm ac-text-muted" style={{ padding: 12 }}>No procurement recommendation is currently available.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Recent Maintenance Actions</h2>
        <p className="ac-text-sm ac-text-muted" style={{ marginBottom: 10 }}>
          The last {recentActions.length} maintenance action(s) recorded in the audit trail this session, most recent first.
        </p>
        <ActionHistory events={recentActions} emptyMessage="No maintenance actions recorded yet this session." linkFor={linkForAction} />
      </section>

      <section className="ac-section">
        <p className="ac-text-sm ac-text-muted">
          Ask <Link href="/ai" className="ac-mono">Lisa</Link> what needs attention right now, or open the{" "}
          <Link href="/procurement/cart" className="ac-mono">Procurement Cart</Link>.
        </p>
      </section>
    </div>
  );
}

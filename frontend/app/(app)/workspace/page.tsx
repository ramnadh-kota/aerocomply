"use client";

import { useState } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge, priorityBadge, workOrderStatusBadge } from "@/components/status/StatusBadge";
import { useRoleSim } from "@/lib/role-sim/RoleSimContext";
import {
  getWorkOrderPlanning,
  getMaintenanceControlCenterSummary,
  getTechnicianWorkload,
  getFleetTatStatus,
  getWorkOrdersAwaitingAssignment,
  getMaterialBlockedWorkOrders,
  getInspectionAnalytics,
  getComplianceAnalytics,
  getExecutionEvidenceStatus,
  getTechnicianAuthorizationMatrix,
} from "@/lib/mock/ai/analytics";
import { getSuggestedQuestionsForRole } from "@/lib/mock/ai/engine";
import { evidenceRecords } from "@/lib/mock/evidenceRecords";
import { workOrderRepository } from "@/lib/domain/repositories";
import { getTechnicianById } from "@/lib/mock/technicians";
import { useMroState } from "@/lib/mro-state/MroStateContext";
import { getCurrentUser } from "@/lib/domain/currentUser";

// M12.8 — Role-oriented workspace entry point, extended to cover every role
// currently exposed by useRoleSim(). Every section below only reads and
// displays an existing canonical engine (lib/mock/ai/analytics.ts,
// lib/mock/ai/engine.ts) or the raw evidence-record store — nothing here
// recomputes a business rule that already lives elsewhere. There is no real
// per-user login in this prototype (getCurrentUser() always returns the
// same fixed identity), so the Technician view illustrates "my work" using
// one representative technician (Rahul Menon) rather than pretending to
// know who is signed in.

const REPRESENTATIVE_TECHNICIAN_ID = "tech-1";

function SuggestedQuestions({ roleId }: { roleId: string }) {
  const categories = getSuggestedQuestionsForRole(roleId);
  const top = categories[0];
  if (!top) return null;
  return (
    <section className="ac-section">
      <h2 className="ac-h2" style={{ marginBottom: 10 }}>Ask Lisa — {top.category}</h2>
      <div className="ac-card">
        <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
          {top.questions.slice(0, 5).map((q) => (
            <Link key={q} href={`/ai?q=${encodeURIComponent(q)}`} className="ac-btn" style={{ padding: "4px 10px" }}>
              {q}
            </Link>
          ))}
        </div>
      </div>
    </section>
  );
}

export default function WorkspacePage() {
  const { roleId } = useRoleSim();
  const [, setVersion] = useState(0);
  const { addAuditEvent } = useMroState();
  const current = getCurrentUser();

  if (roleId === "role-technician") {
    const tech = getTechnicianById(REPRESENTATIVE_TECHNICIAN_ID);
    const myRows = getWorkOrderPlanning().filter((r) => r.assignedTechnicianId === REPRESENTATIVE_TECHNICIAN_ID);
    const today = getWorkOrderPlanning().filter((r) => r.assignedTechnicianId === REPRESENTATIVE_TECHNICIAN_ID);
    const dueToday = today.filter((r) => r.daysOverdue === null && r.dueDate);
    const overdue = today.filter((r) => r.daysOverdue !== null);

    const evidenceRequired = myRows
      .map((r) => ({ r, status: getExecutionEvidenceStatus(r.workOrderId) }))
      .filter((x) => x.status?.state === "FAIL");
    const evidenceAwaitingReview = evidenceRecords.filter(
      (e) => e.uploadedByTechnicianId === REPRESENTATIVE_TECHNICIAN_ID && e.status === "SUBMITTED"
    );

    const authorizationRows = myRows.map((r) => {
      const matrix = getTechnicianAuthorizationMatrix(r.workOrderId);
      const mine = matrix.find((m) => m.technicianId === REPRESENTATIVE_TECHNICIAN_ID);
      return { r, mine };
    });
    const notAuthorized = authorizationRows.filter((x) => x.mine?.status === "NOT_AUTHORIZED");

    function start(workOrderId: string, workOrderNumber: string) {
      const updated = workOrderRepository.startWorkOrder(workOrderId);
      if (!updated) return;
      addAuditEvent({ actor: current?.user.name ?? "Unknown User", actorRole: "Technician", action: "maintenance.work_started", objectType: "WorkOrder", objectLabel: workOrderNumber, previousState: null, newState: "IN_PROGRESS" });
      setVersion((v) => v + 1);
    }

    function complete(workOrderId: string, workOrderNumber: string) {
      const updated = workOrderRepository.completeWorkOrder(workOrderId, new Date().toISOString().slice(0, 10));
      if (!updated) return;
      addAuditEvent({ actor: current?.user.name ?? "Unknown User", actorRole: "Technician", action: "maintenance.work_order_completed", objectType: "WorkOrder", objectLabel: workOrderNumber, previousState: null, newState: "COMPLETED" });
      setVersion((v) => v + 1);
    }

    return (
      <div>
        <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Workspace" }]} />
        <h1 className="ac-h1">My Workspace</h1>
        <p className="ac-subtitle" style={{ marginBottom: 20 }}>
          Technician view — illustrated using {tech?.name ?? REPRESENTATIVE_TECHNICIAN_ID} (this prototype has no real per-user
          login, so this is a representative technician, not an authenticated identity).
        </p>

        <section className="ac-section">
          <div className="ac-kpi-grid">
            <div className="ac-kpi-card">
              <p className="ac-kpi-label">My Work Orders</p>
              <p className="ac-kpi-value">{myRows.length}</p>
            </div>
            <div className="ac-kpi-card">
              <p className="ac-kpi-label">Due / Not Yet Overdue</p>
              <p className="ac-kpi-value">{dueToday.length}</p>
            </div>
            <div className="ac-kpi-card">
              <p className="ac-kpi-label">Overdue</p>
              <p className="ac-kpi-value">{overdue.length}</p>
            </div>
            <div className="ac-kpi-card">
              <p className="ac-kpi-label">Evidence Not Submitted</p>
              <p className="ac-kpi-value">{evidenceRequired.length}</p>
            </div>
          </div>
        </section>

        <section className="ac-section">
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>My Work Orders</h2>
          <div className="ac-card" style={{ padding: 0, overflowX: "auto" }}>
            <table className="ac-table">
              <thead><tr><th>WO</th><th>Aircraft</th><th>Description</th><th>Priority</th><th>Status</th><th>Material</th><th>Action</th></tr></thead>
              <tbody>
                {myRows.map((r) => {
                  const p = priorityBadge(r.priority);
                  const s = workOrderStatusBadge(r.status);
                  return (
                    <tr key={r.workOrderId}>
                      <td><Link href={`/maintenance/planning/${r.workOrderId}`} className="ac-mono">{r.workOrderNumber}</Link></td>
                      <td>{r.aircraftRegistration}</td>
                      <td className="ac-text-sm">{r.title}</td>
                      <td><StatusBadge status={p.status} label={p.label} /></td>
                      <td><StatusBadge status={s.status} label={s.label} /></td>
                      <td className="ac-text-sm">{r.shortParts.length > 0 ? r.shortParts.map((sp) => sp.partNumber).join(", ") : "Ready"}</td>
                      <td>
                        {r.planningStatus === "READY" && <button className="ac-btn ac-btn-primary" style={{ padding: "2px 8px" }} onClick={() => start(r.workOrderId, r.workOrderNumber)}>Start Work</button>}
                        {r.status === "IN_PROGRESS" && <button className="ac-btn ac-btn-primary" style={{ padding: "2px 8px" }} onClick={() => complete(r.workOrderId, r.workOrderNumber)}>Complete</button>}
                        {r.planningStatus === "MATERIAL_BLOCKED" && <Link href="/maintenance/material-readiness" className="ac-btn" style={{ padding: "2px 8px" }}>View Material Blocker</Link>}
                      </td>
                    </tr>
                  );
                })}
                {myRows.length === 0 && <tr><td colSpan={7} className="ac-text-sm ac-text-muted" style={{ padding: 12 }}>No work order is currently assigned to this technician.</td></tr>}
              </tbody>
            </table>
          </div>
        </section>

        <section className="ac-section">
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Evidence Required (Not Yet Submitted)</h2>
          <div className="ac-card" style={{ padding: 0, overflowX: "auto" }}>
            <table className="ac-table">
              <thead><tr><th>WO</th><th>Aircraft</th><th>Reason</th></tr></thead>
              <tbody>
                {evidenceRequired.map(({ r, status }) => (
                  <tr key={r.workOrderId}>
                    <td><Link href={`/maintenance/work-orders/${r.workOrderId}`} className="ac-mono">{r.workOrderNumber}</Link></td>
                    <td>{r.aircraftRegistration}</td>
                    <td className="ac-text-sm">{status?.reason ?? "Required execution evidence is missing."}</td>
                  </tr>
                ))}
                {evidenceRequired.length === 0 && <tr><td colSpan={3} className="ac-text-sm ac-text-muted" style={{ padding: 12 }}>No required evidence is outstanding on this technician&apos;s work orders.</td></tr>}
              </tbody>
            </table>
          </div>
        </section>

        <section className="ac-section">
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Evidence Awaiting Review</h2>
          <div className="ac-card" style={{ padding: 0, overflowX: "auto" }}>
            <table className="ac-table">
              <thead><tr><th>WO</th><th>Type</th><th>File</th><th>Captured</th></tr></thead>
              <tbody>
                {evidenceAwaitingReview.map((e) => (
                  <tr key={e.id}>
                    <td><Link href={`/maintenance/work-orders/${e.workOrderId}`} className="ac-mono">{e.workOrderId}</Link></td>
                    <td className="ac-text-sm">{e.evidenceType}</td>
                    <td className="ac-text-sm">{e.fileName}</td>
                    <td className="ac-text-sm">{e.capturedAt}</td>
                  </tr>
                ))}
                {evidenceAwaitingReview.length === 0 && <tr><td colSpan={4} className="ac-text-sm ac-text-muted" style={{ padding: 12 }}>No evidence submitted by this technician is currently awaiting reviewer action.</td></tr>}
              </tbody>
            </table>
          </div>
        </section>

        <section className="ac-section">
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Authorization Status</h2>
          <div className="ac-card" style={{ padding: 0, overflowX: "auto" }}>
            <table className="ac-table">
              <thead><tr><th>WO</th><th>Status</th><th>Reason</th></tr></thead>
              <tbody>
                {authorizationRows.map(({ r, mine }) => (
                  <tr key={r.workOrderId}>
                    <td><Link href={`/maintenance/work-orders/${r.workOrderId}`} className="ac-mono">{r.workOrderNumber}</Link></td>
                    <td>{mine ? <StatusBadge status={mine.status === "AUTHORIZED" ? "COMPLIANT" : mine.status === "NOT_AUTHORIZED" ? "NON_COMPLIANT" : "UNKNOWN"} label={mine.status.replace(/_/g, " ")} /> : "—"}</td>
                    <td className="ac-text-sm">{mine?.reasons[mine.reasons.length - 1] ?? "—"}</td>
                  </tr>
                ))}
                {authorizationRows.length === 0 && <tr><td colSpan={3} className="ac-text-sm ac-text-muted" style={{ padding: 12 }}>No work order is currently assigned to this technician.</td></tr>}
              </tbody>
            </table>
          </div>
          {notAuthorized.length > 0 && (
            <p className="ac-text-sm" style={{ marginTop: 8, color: "var(--ac-danger, #b91c1c)" }}>
              {notAuthorized.length} assigned work order(s) are flagged NOT_AUTHORIZED for this technician — see reasons above.
            </p>
          )}
        </section>

        <SuggestedQuestions roleId={roleId} />

        <section className="ac-section">
          <p className="ac-text-sm ac-text-muted">
            Full execution history and blocked-work-order detail: <Link href="/maintenance/control-center" className="ac-mono">Maintenance Control Center</Link>.
          </p>
        </section>
      </div>
    );
  }

  if (roleId === "role-maintenance-manager" || roleId === "role-maintenance-planner") {
    const isManager = roleId === "role-maintenance-manager";
    const summary = getMaintenanceControlCenterSummary();
    const workload = getTechnicianWorkload();
    const tatRows = getFleetTatStatus().filter((r) => r.assessment.status === "AT_RISK" || r.assessment.status === "DELAYED");
    const assignmentGaps = getWorkOrdersAwaitingAssignment();
    const materialBlocked = getMaterialBlockedWorkOrders();

    // Bottleneck aircraft: aircraft appearing more than once across the
    // existing material-blocked planning rows — a plain grouping over
    // getMaterialBlockedWorkOrders(), not a new calculation.
    const byAircraft = new Map<string, { count: number; registration: string }>();
    for (const r of materialBlocked) {
      const existing = byAircraft.get(r.aircraftId);
      byAircraft.set(r.aircraftId, { count: (existing?.count ?? 0) + 1, registration: r.aircraftRegistration });
    }
    const bottleneckAircraft = Array.from(byAircraft.entries())
      .filter(([, v]) => v.count > 1)
      .sort((a, b) => b[1].count - a[1].count);

    return (
      <div>
        <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Workspace" }]} />
        <h1 className="ac-h1">My Workspace</h1>
        <p className="ac-subtitle" style={{ marginBottom: 20 }}>
          {isManager ? "Maintenance Manager" : "Maintenance Planner"} view — quick access to the existing planning, execution,
          material, and audit tools. Every figure below is read from the Maintenance Control Center and Work Order Planning
          engines.
        </p>
        <section className="ac-section">
          <div className="ac-kpi-grid">
            <Link href="/maintenance/planning" className="ac-kpi-card" style={{ display: "block" }}>
              <p className="ac-kpi-label">Critical Work Orders</p>
              <p className="ac-kpi-value">{summary.criticalWorkOrders}</p>
            </Link>
            <Link href="/maintenance/material-readiness" className="ac-kpi-card" style={{ display: "block" }}>
              <p className="ac-kpi-label">Material Blockers</p>
              <p className="ac-kpi-value">{summary.materialShortages}</p>
            </Link>
            <Link href="/maintenance/planning" className="ac-kpi-card" style={{ display: "block" }}>
              <p className="ac-kpi-label">Waiting on Parts</p>
              <p className="ac-kpi-value">{summary.workOrdersWaitingForParts}</p>
            </Link>
            <Link href="/maintenance/discrepancies" className="ac-kpi-card" style={{ display: "block" }}>
              <p className="ac-kpi-label">Critical Discrepancies</p>
              <p className="ac-kpi-value">{summary.criticalDiscrepancies}</p>
            </Link>
          </div>
        </section>

        <section className="ac-section">
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>TAT Risk Work Orders</h2>
          <div className="ac-card" style={{ padding: 0, overflowX: "auto" }}>
            <table className="ac-table">
              <thead><tr><th>WO</th><th>Aircraft</th><th>TAT Status</th><th>Due Date</th><th>Reason / Blockers</th></tr></thead>
              <tbody>
                {tatRows.map((r) => (
                  <tr key={r.workOrderId}>
                    <td><Link href={`/maintenance/work-orders/${r.workOrderId}`} className="ac-mono">{r.workOrderNumber}</Link></td>
                    <td>{r.aircraftRegistration}</td>
                    <td><StatusBadge status={r.assessment.status === "DELAYED" ? "NON_COMPLIANT" : "REVIEW_REQUIRED"} label={r.assessment.status.replace(/_/g, " ")} /></td>
                    <td className="ac-text-sm ac-mono">
                      {r.assessment.dueDate || "—"}
                      {r.assessment.daysOverdue !== null && <span className="ac-text-muted"> ({r.assessment.daysOverdue}d overdue)</span>}
                      {r.assessment.daysRemaining !== null && <span className="ac-text-muted"> ({r.assessment.daysRemaining}d remaining)</span>}
                    </td>
                    <td className="ac-text-sm">
                      {r.assessment.reason}
                      {r.assessment.contributingBlockers.length > 0 && (
                        <ul style={{ margin: "4px 0 0", paddingLeft: 16 }}>
                          {r.assessment.contributingBlockers.map((b, i) => (
                            <li key={i} className="ac-text-muted">{b}</li>
                          ))}
                        </ul>
                      )}
                    </td>
                  </tr>
                ))}
                {tatRows.length === 0 && <tr><td colSpan={5} className="ac-text-sm ac-text-muted" style={{ padding: 12 }}>No open work order is currently AT_RISK or DELAYED on turnaround time.</td></tr>}
              </tbody>
            </table>
          </div>
        </section>

        <section className="ac-section">
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Critical-Path / Bottleneck Aircraft</h2>
          <div className="ac-card" style={{ padding: 0, overflowX: "auto" }}>
            <table className="ac-table">
              <thead><tr><th>Aircraft</th><th>Material-Blocked Work Orders</th></tr></thead>
              <tbody>
                {bottleneckAircraft.map(([aircraftId, v]) => (
                  <tr key={aircraftId}>
                    <td><Link href={`/aircraft/${aircraftId}`} className="ac-mono">{v.registration}</Link></td>
                    <td>{v.count}</td>
                  </tr>
                ))}
                {bottleneckAircraft.length === 0 && <tr><td colSpan={2} className="ac-text-sm ac-text-muted" style={{ padding: 12 }}>No aircraft currently has more than one material-blocked work order.</td></tr>}
              </tbody>
            </table>
          </div>
        </section>

        <section className="ac-section">
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Technician Assignment Gaps</h2>
          <div className="ac-card" style={{ padding: 0, overflowX: "auto" }}>
            <table className="ac-table">
              <thead><tr><th>WO</th><th>Aircraft</th><th>Priority</th><th>Status</th></tr></thead>
              <tbody>
                {assignmentGaps.map((r) => {
                  const p = priorityBadge(r.priority);
                  return (
                    <tr key={r.workOrderId}>
                      <td><Link href={`/maintenance/planning/${r.workOrderId}`} className="ac-mono">{r.workOrderNumber}</Link></td>
                      <td>{r.aircraftRegistration}</td>
                      <td><StatusBadge status={p.status} label={p.label} /></td>
                      <td className="ac-text-sm">{r.planningStatus.replace(/_/g, " ")}</td>
                    </tr>
                  );
                })}
                {assignmentGaps.length === 0 && <tr><td colSpan={4} className="ac-text-sm ac-text-muted" style={{ padding: 12 }}>No open work order is currently awaiting technician assignment.</td></tr>}
              </tbody>
            </table>
          </div>
        </section>

        <section className="ac-section">
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Technician Workload</h2>
          <div className="ac-card" style={{ padding: 0, overflowX: "auto" }}>
            <table className="ac-table">
              <thead><tr><th>Technician</th><th>Open Work Orders</th><th>Overdue</th><th>On Shift</th></tr></thead>
              <tbody>
                {workload.map((t) => (
                  <tr key={t.technicianId}>
                    <td>{t.name}</td>
                    <td>{t.openWorkOrders}</td>
                    <td>{t.overdueWorkOrders > 0 ? <StatusBadge status="NON_COMPLIANT" label={String(t.overdueWorkOrders)} /> : "0"}</td>
                    <td>{t.onShift ? <StatusBadge status="ACTIVE" label="On Shift" /> : <span className="ac-text-sm ac-text-muted">Off Shift</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <SuggestedQuestions roleId={roleId} />

        <section className="ac-section">
          <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
            <Link href="/maintenance/control-center" className="ac-btn ac-btn-primary">Open Control Center</Link>
            <Link href="/maintenance/planning" className="ac-btn">Work Order Planning</Link>
            <Link href="/maintenance/material-readiness" className="ac-btn">Material Readiness</Link>
            <Link href="/audit" className="ac-btn">Audit &amp; History</Link>
          </div>
        </section>
      </div>
    );
  }

  if (roleId === "role-inspector" || roleId === "role-compliance-manager") {
    const isInspector = roleId === "role-inspector";
    const inspection = getInspectionAnalytics();
    const compliance = getComplianceAnalytics();
    const rejectedEvidence = evidenceRecords.filter((e) => e.status === "REJECTED");

    return (
      <div>
        <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Workspace" }]} />
        <h1 className="ac-h1">My Workspace</h1>
        <p className="ac-subtitle" style={{ marginBottom: 20 }}>
          {isInspector ? "Inspector" : "Compliance Manager"} view — pending inspection queue, evidence needing re-review, and
          fleet-wide compliance risk, read from the existing Inspection and Compliance analytics engines.
        </p>

        <section className="ac-section">
          <div className="ac-kpi-grid">
            <div className="ac-kpi-card">
              <p className="ac-kpi-label">Awaiting Inspection</p>
              <p className="ac-kpi-value">{inspection.pending.length}</p>
            </div>
            <div className="ac-kpi-card">
              <p className="ac-kpi-label">Rejected Evidence</p>
              <p className="ac-kpi-value">{rejectedEvidence.length}</p>
            </div>
            <div className="ac-kpi-card">
              <p className="ac-kpi-label">Non-Compliant Assessments</p>
              <p className="ac-kpi-value">{compliance.nonCompliant}</p>
            </div>
            <div className="ac-kpi-card">
              <p className="ac-kpi-label">Review Required</p>
              <p className="ac-kpi-value">{compliance.reviewRequired}</p>
            </div>
          </div>
        </section>

        <section className="ac-section">
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Pending Inspections (Prioritized)</h2>
          <div className="ac-card" style={{ padding: 0, overflowX: "auto" }}>
            <table className="ac-table">
              <thead><tr><th>Work Order</th><th>Priority</th><th>Action</th></tr></thead>
              <tbody>
                {inspection.pending.map((p) => {
                  const badge = priorityBadge(p.priority);
                  return (
                    <tr key={p.id}>
                      <td className="ac-mono">{p.label}</td>
                      <td><StatusBadge status={badge.status} label={badge.label} /></td>
                      <td><Link href={p.href} className="ac-btn" style={{ padding: "2px 8px" }}>Review</Link></td>
                    </tr>
                  );
                })}
                {inspection.pending.length === 0 && <tr><td colSpan={3} className="ac-text-sm ac-text-muted" style={{ padding: 12 }}>No work order is currently awaiting inspection.</td></tr>}
              </tbody>
            </table>
          </div>
        </section>

        <section className="ac-section">
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Rejected Evidence Needing Re-Review</h2>
          <div className="ac-card" style={{ padding: 0, overflowX: "auto" }}>
            <table className="ac-table">
              <thead><tr><th>WO</th><th>Type</th><th>Reviewer Note</th></tr></thead>
              <tbody>
                {rejectedEvidence.map((e) => (
                  <tr key={e.id}>
                    <td><Link href={`/maintenance/work-orders/${e.workOrderId}`} className="ac-mono">{e.workOrderId}</Link></td>
                    <td className="ac-text-sm">{e.evidenceType}</td>
                    <td className="ac-text-sm">{e.reviewNote ?? "—"}</td>
                  </tr>
                ))}
                {rejectedEvidence.length === 0 && <tr><td colSpan={3} className="ac-text-sm ac-text-muted" style={{ padding: 12 }}>No evidence record is currently rejected.</td></tr>}
              </tbody>
            </table>
          </div>
        </section>

        <section className="ac-section">
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Compliance Risk</h2>
          <div className="ac-card">
            <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
              {compliance.kpis.map((k) => (
                <div key={k.label} className="ac-kpi-card" style={{ minWidth: 140 }}>
                  <p className="ac-kpi-label">{k.label}</p>
                  <p className="ac-kpi-value">{k.value}</p>
                </div>
              ))}
            </div>
            <p className="ac-text-sm ac-text-muted" style={{ marginTop: 10 }}>
              Full detail: <Link href="/compliance" className="ac-mono">Compliance</Link>.
            </p>
          </div>
        </section>

        <SuggestedQuestions roleId={roleId} />
      </div>
    );
  }

  if (roleId === "role-executive") {
    const summary = getMaintenanceControlCenterSummary();
    const compliance = getComplianceAnalytics();
    return (
      <div>
        <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Workspace" }]} />
        <h1 className="ac-h1">My Workspace</h1>
        <p className="ac-subtitle" style={{ marginBottom: 20 }}>
          Executive view — a brief operational snapshot. For full fleet-wide risk, financial, and compliance reporting, use the
          Executive Command Center.
        </p>
        <section className="ac-section">
          <div className="ac-kpi-grid">
            <div className="ac-kpi-card">
              <p className="ac-kpi-label">Critical Work Orders</p>
              <p className="ac-kpi-value">{summary.criticalWorkOrders}</p>
            </div>
            <div className="ac-kpi-card">
              <p className="ac-kpi-label">Material Blockers</p>
              <p className="ac-kpi-value">{summary.materialShortages}</p>
            </div>
            <div className="ac-kpi-card">
              <p className="ac-kpi-label">Non-Compliant Assessments</p>
              <p className="ac-kpi-value">{compliance.nonCompliant}</p>
            </div>
            <div className="ac-kpi-card">
              <p className="ac-kpi-label">Review Required</p>
              <p className="ac-kpi-value">{compliance.reviewRequired}</p>
            </div>
          </div>
        </section>
        <section className="ac-section">
          <Link href="/executive" className="ac-btn ac-btn-primary">Open Executive Command Center</Link>
        </section>
        <SuggestedQuestions roleId={roleId} />
      </div>
    );
  }

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Workspace" }]} />
      <h1 className="ac-h1">Workspace</h1>
      <p className="ac-subtitle" style={{ marginBottom: 20 }}>Saved views, watchlists, and team workflows.</p>
      <div className="ac-card">
        <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
          A role-specific workspace exists for Technician, Maintenance Planner, Maintenance Manager, Inspector, Compliance
          Manager, and Executive — switch &quot;Viewing as&quot; in the top bar to see it. For other roles, use the{" "}
          <Link href="/maintenance/control-center" className="ac-mono">Maintenance Control Center</Link> or{" "}
          <Link href="/executive" className="ac-mono">Executive Control Center</Link> as your primary operational view.
        </p>
      </div>
      <SuggestedQuestions roleId={roleId} />
    </div>
  );
}

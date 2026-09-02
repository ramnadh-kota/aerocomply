"use client";

import { useState } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge, priorityBadge, workOrderStatusBadge } from "@/components/status/StatusBadge";
import { useRoleSim } from "@/lib/role-sim/RoleSimContext";
import { getWorkOrderPlanning, getMaintenanceControlCenterSummary } from "@/lib/mock/ai/analytics";
import { workOrderRepository } from "@/lib/domain/repositories";
import { getTechnicianById } from "@/lib/mock/technicians";
import { useMroState } from "@/lib/mro-state/MroStateContext";
import { getCurrentUser } from "@/lib/domain/currentUser";

// M12.8 — Role-oriented workspace entry point. Reuses the existing Work
// Order Planning analytics (getWorkOrderPlanning) and the existing
// assignTechnician/startWorkOrder/completeWorkOrder mutations — no second
// work-order system, no new analytics. There is no real per-user login in
// this prototype (getCurrentUser() always returns the same fixed identity),
// so the Technician view illustrates "my work" using one representative
// technician (Rahul Menon) rather than pretending to know who is signed in.

const REPRESENTATIVE_TECHNICIAN_ID = "tech-1";

export default function WorkspacePage() {
  const { roleId } = useRoleSim();
  const [, setVersion] = useState(0);
  const { addAuditEvent } = useMroState();
  const current = getCurrentUser();

  if (roleId === "role-technician") {
    const tech = getTechnicianById(REPRESENTATIVE_TECHNICIAN_ID);
    const myRows = getWorkOrderPlanning().filter((r) => r.assignedTechnicianId === REPRESENTATIVE_TECHNICIAN_ID);

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
          <p className="ac-text-sm ac-text-muted">
            Full execution history and blocked-work-order detail: <Link href="/maintenance/control-center" className="ac-mono">Maintenance Control Center</Link>.
          </p>
        </section>
      </div>
    );
  }

  if (roleId === "role-maintenance-manager") {
    const summary = getMaintenanceControlCenterSummary();
    return (
      <div>
        <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Workspace" }]} />
        <h1 className="ac-h1">My Workspace</h1>
        <p className="ac-subtitle" style={{ marginBottom: 20 }}>
          Planner view — quick access to the existing planning, execution, material, and audit tools. Every figure below is
          read from the Maintenance Control Center.
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

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Workspace" }]} />
      <h1 className="ac-h1">Workspace</h1>
      <p className="ac-subtitle" style={{ marginBottom: 20 }}>Saved views, watchlists, and team workflows.</p>
      <div className="ac-card">
        <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
          A role-specific workspace exists for Technician and Maintenance Manager (Planner) — switch &quot;Viewing as&quot; in the
          top bar to see it. For all other roles, use the{" "}
          <Link href="/maintenance/control-center" className="ac-mono">Maintenance Control Center</Link> or{" "}
          <Link href="/executive" className="ac-mono">Executive Control Center</Link> as your primary operational view.
        </p>
      </div>
    </div>
  );
}

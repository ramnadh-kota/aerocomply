"use client";

import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { partRequests } from "@/lib/mock/procurement";
import { getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
import { getWorkOrderById } from "@/lib/mock/workOrders";
import { getUserById } from "@/lib/mock/roles";
import { getTechnicianById } from "@/lib/mock/technicians";

// M11.5 — Procurement Approval Center. Server Component (plain <table>,
// no DataTable) — reviewable by Base Manager/Production Manager/Quality
// Director/Executive/Procurement roles per the existing RoleSimContext;
// no second permission system introduced.

function requesterName(id: string): string {
  return getTechnicianById(id)?.name ?? getUserById(id)?.name ?? id;
}

function statusBadge(status: string): { status: Parameters<typeof StatusBadge>[0]["status"]; label: string } {
  switch (status) {
    case "APPROVED": return { status: "COMPLIANT", label: "Approved" };
    case "REJECTED": return { status: "NON_COMPLIANT", label: "Rejected" };
    case "CLARIFICATION_REQUIRED": return { status: "REVIEW_REQUIRED", label: "Clarification Required" };
    case "SUBMITTED": case "UNDER_REVIEW": return { status: "PENDING", label: status.replace(/_/g, " ") };
    default: return { status: "INSUFFICIENT_DATA", label: status.replace(/_/g, " ") };
  }
}

export default function ProcurementApprovalsPage() {
  const pending = partRequests.filter((r) => r.status === "SUBMITTED" || r.status === "UNDER_REVIEW");
  const aog = pending.filter((r) => r.priority === "AOG");
  const highCost = pending.filter((r) => r.estimatedCost !== null && r.estimatedCost > 1000);
  const missingCost = pending.filter((r) => r.estimatedCost === null);

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Procurement", href: "/procurement" }, { label: "Approval Center" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Procurement Approval Center</h1>
          <p className="ac-subtitle">Review, approve, reject, or request clarification on part requests before a purchase order can be generated.</p>
        </div>
      </div>

      <section className="ac-section">
        <div className="ac-kpi-grid">
          <div className="ac-kpi-card"><p className="ac-kpi-label">Pending Requests</p><p className="ac-kpi-value">{pending.length}</p></div>
          <div className="ac-kpi-card"><p className="ac-kpi-label">AOG Requests</p><p className="ac-kpi-value">{aog.length}</p></div>
          <div className="ac-kpi-card"><p className="ac-kpi-label">High Cost (&gt;$1,000)</p><p className="ac-kpi-value">{highCost.length}</p></div>
          <div className="ac-kpi-card"><p className="ac-kpi-label">Requests Older Than SLA</p><p className="ac-kpi-value">Insufficient source data.</p></div>
          <div className="ac-kpi-card"><p className="ac-kpi-label">Approved Today</p><p className="ac-kpi-value">Insufficient source data.</p></div>
          <div className="ac-kpi-card"><p className="ac-kpi-label">Missing Cost Data</p><p className="ac-kpi-value">{missingCost.length}</p></div>
        </div>
        <p className="ac-text-sm ac-text-muted" style={{ marginTop: 8 }}>
          &ldquo;Requests Older Than SLA&rdquo; and &ldquo;Approved Today&rdquo; require a defined SLA policy and timestamped decision history that do not yet exist in the domain model.
        </p>
      </section>

      <div className="ac-card" style={{ padding: 0 }}>
        <table className="ac-table">
          <thead><tr><th>Request</th><th>Priority</th><th>Part</th><th>Aircraft</th><th>Work Order</th><th>Requester</th><th>Est. Cost</th><th>Status</th></tr></thead>
          <tbody>
            {partRequests.map((r) => {
              const aircraft = getAircraftById(r.aircraftId);
              const wo = r.workOrderId ? getWorkOrderById(r.workOrderId) : undefined;
              return (
                <tr key={r.id}>
                  <td><Link href={`/procurement/approvals/${r.id}`} className="ac-mono">{r.id}</Link></td>
                  <td><StatusBadge status={r.priority === "AOG" ? "NON_COMPLIANT" : r.priority === "HIGH" ? "REVIEW_REQUIRED" : "COMPLIANT"} label={r.priority} /></td>
                  <td className="ac-mono">{r.partNumber}</td>
                  <td>{aircraft ? <Link href={`/aircraft/${aircraft.id}`}>{currentRegistration(aircraft)}</Link> : "Insufficient source data."}</td>
                  <td>{wo ? <Link href={`/maintenance/work-orders/${wo.id}`} className="ac-mono">{wo.workOrderNumber}</Link> : "Insufficient source data."}</td>
                  <td>{requesterName(r.requestedBy)}</td>
                  <td>{r.estimatedCost !== null ? `USD ${r.estimatedCost.toLocaleString()}` : "Insufficient source data."}</td>
                  <td><StatusBadge {...statusBadge(r.status)} /></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

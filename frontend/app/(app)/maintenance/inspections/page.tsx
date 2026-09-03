"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { StatusBadge, priorityBadge, inspectorReviewStatusBadge } from "@/components/status/StatusBadge";
import { workOrders, MOCK_TODAY } from "@/lib/mock/workOrders";
import { getInspectorReviewById } from "@/lib/mock/inspectorReviews";
import { getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
import { getProjectById } from "@/lib/mock/maintenanceProjects";
import { getTechnicianById } from "@/lib/mock/technicians";
import { getRequirementById } from "@/lib/mock/regulations";
import { defectsForWorkOrder } from "@/lib/mock/defects";
import { findings, findingsForWorkOrder } from "@/lib/mock/findings";
import { getAssessmentById } from "@/lib/mock/assessments";
import { useMroState, type WorkOrderChecklistRecord } from "@/lib/mro-state/MroStateContext";
import { getInspectionRequirement, type InspectionRequirementStatus } from "@/lib/mock/ai/analytics";
import type { WorkOrder, InspectorReviewStatus } from "@/lib/mock/types";

// M25 RII status is a DIFFERENT concept from the checklist inspector review
// above (InspectorReviewStatus/inspectorReviewStatusBadge): RII is whether
// an eligible INDEPENDENT inspector (not the assigned technician) is
// available to clear release, while the checklist review is a quality
// disposition of submitted work. Both are real, both matter, and they must
// never be presented as the same status. Reuses getInspectionRequirement
// exactly as-is — no second RII calculation.
const RII_BADGE: Record<InspectionRequirementStatus, { status: Parameters<typeof StatusBadge>[0]["status"]; label: string }> = {
  NOT_REQUIRED: { status: "COMPLIANT", label: "NOT REQUIRED" },
  REQUIRED: { status: "PENDING", label: "REQUIRED" },
  READY: { status: "COMPLIANT", label: "INSPECTOR AVAILABLE" },
  BLOCKED: { status: "NON_COMPLIANT", label: "NO ELIGIBLE INSPECTOR" },
  COMPLETED: { status: "COMPLIANT", label: "COMPLETED" },
  UNKNOWN: { status: "INSUFFICIENT_DATA", label: "UNKNOWN" },
};

interface Row {
  workOrder: WorkOrder;
  reviewStatus: InspectorReviewStatus;
  submittedAt: string | null;
  reviewedAt: string | null;
  record: WorkOrderChecklistRecord | undefined;
}

function buildRows(submissions: Record<string, WorkOrderChecklistRecord>): Row[] {
  return workOrders
    .filter((w) => w.inspectorReviewId)
    .map((w) => {
      const review = getInspectorReviewById(w.inspectorReviewId!);
      const record = submissions[w.id];
      // Reads the same live checklist/inspection state the technician and
      // inspector screens write to — not the static seed review — so the
      // queue reflects a decision the moment it's made.
      return {
        workOrder: w,
        reviewStatus: record?.inspectorDecisionStatus ?? review?.status ?? "PENDING_INSPECTION",
        submittedAt: record?.submittedAt ?? w.signOff?.timestamp ?? null,
        reviewedAt: record?.inspectorReviewedAt ?? review?.reviewedAt ?? null,
        record,
      };
    });
}

function daysSince(iso: string | null): number {
  if (!iso) return 0;
  const days = (new Date(MOCK_TODAY).getTime() - new Date(iso).getTime()) / (1000 * 60 * 60 * 24);
  return Math.max(0, Math.round(days));
}

/** Prototype triage ranking — NOT a certified safety decision. Order:
 * 1) UNKNOWN checklist items, 2) critical/high defects, 3) FAIL items,
 * 4) high-priority work orders, 5) aging submissions. */
function triageScore(r: Row): number {
  const items = r.record ? Object.values(r.record.items) : [];
  const hasUnknown = items.some((i) => i.result === "UNKNOWN");
  const hasFail = items.some((i) => i.result === "FAIL");
  const criticalDefects = defectsForWorkOrder(r.workOrder.id).filter((d) => d.status === "OPEN" && (d.severity === "CRITICAL" || d.severity === "HIGH")).length;
  const highPriority = r.workOrder.priority === "CRITICAL" || r.workOrder.priority === "HIGH";
  const aging = daysSince(r.submittedAt);
  let score = 0;
  if (hasUnknown) score += 1000;
  if (criticalDefects > 0) score += 500;
  if (hasFail) score += 250;
  if (highPriority) score += 100;
  score += Math.min(aging, 30);
  return score;
}

export default function InspectionQueuePage() {
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [priorityFilter, setPriorityFilter] = useState("ALL");
  const [aircraftFilter, setAircraftFilter] = useState("ALL");
  const { submissions } = useMroState();

  const rows = useMemo(() => buildRows(submissions), [submissions]);
  const aircraftOptions = useMemo(() => Array.from(new Set(rows.map((r) => r.workOrder.aircraftId))), [rows]);

  const pending = rows.filter((r) => r.reviewStatus === "PENDING_INSPECTION");
  const unknownCount = pending.filter((r) => r.record && Object.values(r.record.items).some((i) => i.result === "UNKNOWN")).length;
  const failedCount = pending.filter((r) => r.record && Object.values(r.record.items).some((i) => i.result === "FAIL")).length;
  const findingsCount = pending.reduce((sum, r) => sum + findingsForWorkOrder(r.workOrder.id).length, 0);
  const highPriorityCount = pending.filter((r) => r.workOrder.priority === "HIGH" || r.workOrder.priority === "CRITICAL").length;
  const oldestAgingDays = pending.reduce((max, r) => Math.max(max, daysSince(r.submittedAt)), 0);
  const recentlyApproved = rows.filter((r) => r.reviewStatus === "APPROVED" && r.reviewedAt).sort((a, b) => (b.reviewedAt ?? "").localeCompare(a.reviewedAt ?? "")).slice(0, 3);
  const recentlyReturned = rows.filter((r) => (r.reviewStatus === "RETURNED_FOR_CORRECTION" || r.reviewStatus === "REJECTED") && r.reviewedAt).sort((a, b) => (b.reviewedAt ?? "").localeCompare(a.reviewedAt ?? "")).slice(0, 3);
  const triaged = [...pending].sort((a, b) => triageScore(b) - triageScore(a));
  const pendingFindings = pending.flatMap((p) => findingsForWorkOrder(p.workOrder.id).map((f) => ({ finding: f, wo: p.workOrder })));
  const totalRequiringDefect = findings.filter((f) => f.requiresDefect).length;

  const filtered = rows.filter((r) => {
    if (statusFilter !== "ALL" && r.reviewStatus !== statusFilter) return false;
    if (priorityFilter !== "ALL" && r.workOrder.priority !== priorityFilter) return false;
    if (aircraftFilter !== "ALL" && r.workOrder.aircraftId !== aircraftFilter) return false;
    return true;
  });

  const columns: Column<Row>[] = [
    { key: "wo", header: "Work Order", render: (r) => <span className="ac-mono">{r.workOrder.workOrderNumber}</span>, sortValue: (r) => r.workOrder.workOrderNumber },
    {
      key: "aircraft",
      header: "Aircraft",
      render: (r) => {
        const a = getAircraftById(r.workOrder.aircraftId);
        return a ? <Link href={`/aircraft/${a.id}`} className="ac-mono">{currentRegistration(a)}</Link> : r.workOrder.aircraftId;
      },
    },
    {
      key: "project",
      header: "Maintenance Project",
      render: (r) => {
        const p = r.workOrder.projectId ? getProjectById(r.workOrder.projectId) : undefined;
        return p ? <Link href={`/maintenance/projects/${p.id}`} className="ac-mono">{p.projectNumber}</Link> : "Ad hoc";
      },
    },
    {
      key: "technician",
      header: "Technician",
      render: (r) => (r.workOrder.assignedTechnicianId ? getTechnicianById(r.workOrder.assignedTechnicianId)?.name : "Unassigned"),
    },
    { key: "submitted", header: "Submitted At", render: (r) => (r.submittedAt ? new Date(r.submittedAt).toLocaleString() : "—"), sortValue: (r) => r.submittedAt ?? "" },
    { key: "priority", header: "Priority", render: (r) => <StatusBadge {...priorityBadge(r.workOrder.priority)} /> },
    { key: "status", header: "Inspection Status", render: (r) => <StatusBadge {...inspectorReviewStatusBadge(r.reviewStatus)} /> },
    {
      key: "rii",
      header: "Independent Inspection (RII)",
      render: (r) => {
        const rii = getInspectionRequirement(r.workOrder.id);
        return <StatusBadge {...RII_BADGE[rii.status]} />;
      },
    },
    { key: "defects", header: "Defects", render: (r) => defectsForWorkOrder(r.workOrder.id).length },
    {
      key: "compliance",
      header: "Compliance Requirement",
      render: (r) => {
        const req = r.workOrder.relatedRequirementId ? getRequirementById(r.workOrder.relatedRequirementId) : undefined;
        return req ? <Link href={`/regulations/${req.id}`} className="ac-mono">{req.requirementNumber}</Link> : "—";
      },
    },
  ];

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Maintenance", href: "/maintenance/projects" }, { label: "Inspection Queue" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Inspection Queue</h1>
          <p className="ac-subtitle">{filtered.length} of {rows.length} work orders submitted for inspection</p>
        </div>
        <div className="ac-flex ac-gap-2">
          <Link href="/ai" className="ac-btn" style={{ fontSize: 12, padding: "4px 10px" }}>Ask AI to Prioritize</Link>
          <Link href="/reports/inspection-queue" className="ac-btn" style={{ fontSize: 12, padding: "4px 10px" }}>Generate Report</Link>
        </div>
      </div>

      <section className="ac-section">
        <div className="ac-kpi-grid">
          <div className="ac-kpi-card">
            <p className="ac-kpi-label">Pending</p>
            <p className="ac-kpi-value">{pending.length}</p>
          </div>
          <div className="ac-kpi-card">
            <p className="ac-kpi-label">High-Priority</p>
            <p className="ac-kpi-value">{highPriorityCount}</p>
          </div>
          <div className="ac-kpi-card">
            <p className="ac-kpi-label">UNKNOWN Items</p>
            <p className="ac-kpi-value">{unknownCount}</p>
          </div>
          <div className="ac-kpi-card">
            <p className="ac-kpi-label">Failed Items</p>
            <p className="ac-kpi-value">{failedCount}</p>
          </div>
          <div className="ac-kpi-card">
            <p className="ac-kpi-label">Findings</p>
            <p className="ac-kpi-value">{findingsCount}</p>
          </div>
          <div className="ac-kpi-card">
            <p className="ac-kpi-label">Oldest Pending</p>
            <p className="ac-kpi-value">{oldestAgingDays}d</p>
          </div>
        </div>
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Findings &amp; Traceability</h2>
        <div className="ac-card" style={{ padding: 0 }}>
          {pendingFindings.length === 0 ? (
            <p className="ac-text-sm ac-text-muted" style={{ padding: 12 }}>Insufficient source data.</p>
          ) : (
            <table className="ac-table">
              <thead><tr><th>Work Order</th><th>Finding</th><th>Severity</th><th>Requirement</th><th>Assessment</th></tr></thead>
              <tbody>
                {pendingFindings.map(({ finding, wo }) => {
                  const req = wo.relatedRequirementId ? getRequirementById(wo.relatedRequirementId) : undefined;
                  const asmt = wo.relatedAssessmentId ? getAssessmentById(wo.relatedAssessmentId) : undefined;
                  return (
                    <tr key={finding.id}>
                      <td><Link href={`/maintenance/inspections/${wo.id}`} className="ac-mono">{wo.workOrderNumber}</Link></td>
                      <td className="ac-text-sm">{finding.description}</td>
                      <td><StatusBadge {...priorityBadge(finding.severity)} label={finding.requiresDefect ? `${finding.severity} · Defect Raised` : finding.severity} /></td>
                      <td>{req ? <Link href={`/regulations/${req.id}`} className="ac-mono">{req.requirementNumber}</Link> : "—"}</td>
                      <td>{asmt ? <Link href={`/assessments/${asmt.id}`}><StatusBadge status={asmt.finalStatus} /></Link> : "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
        <p className="ac-text-sm ac-text-muted" style={{ marginTop: 6 }}>
          {totalRequiringDefect} finding(s) fleet-wide required a defect to be raised. <Link href="/maintenance/defects">View Defects →</Link>
        </p>
      </section>

      {triaged.length > 0 && (
        <section className="ac-section">
          <div className="ac-card" style={{ borderColor: "var(--ac-status-insufficient)", background: "rgba(154,107,255,0.06)" }}>
            <p className="ac-eyebrow" style={{ color: "var(--ac-status-insufficient)", marginBottom: 6 }}>
              Prototype Triage Ranking — not a certified safety decision
            </p>
            <p className="ac-text-sm ac-text-secondary" style={{ margin: "0 0 8px" }}>
              Order: UNKNOWN checklist items → critical/high defects → failed items → high-priority work orders → aging submissions.
            </p>
            <ol style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
              {triaged.slice(0, 5).map((r) => (
                <li key={r.workOrder.id} style={{ marginBottom: 4 }}>
                  <Link href={`/maintenance/inspections/${r.workOrder.id}`} className="ac-mono">{r.workOrder.workOrderNumber}</Link>
                  {" · "}
                  <StatusBadge {...priorityBadge(r.workOrder.priority)} />
                  {r.record && Object.values(r.record.items).some((i) => i.result === "UNKNOWN") && <span className="ac-text-muted"> · UNKNOWN item present</span>}
                </li>
              ))}
            </ol>
          </div>
        </section>
      )}

      {(recentlyApproved.length > 0 || recentlyReturned.length > 0) && (
        <div className="ac-grid-2 ac-section">
          <section>
            <h2 className="ac-h2" style={{ marginBottom: 8 }}>Recently Approved</h2>
            <div className="ac-flex ac-flex-col ac-gap-2">
              {recentlyApproved.length === 0 && <p className="ac-text-sm ac-text-muted">None yet.</p>}
              {recentlyApproved.map((r) => (
                <Link key={r.workOrder.id} href={`/maintenance/inspections/${r.workOrder.id}`} className="ac-card" style={{ display: "block" }}>
                  <span className="ac-mono">{r.workOrder.workOrderNumber}</span> <span className="ac-text-muted ac-text-sm">{r.reviewedAt ? new Date(r.reviewedAt).toLocaleString() : ""}</span>
                </Link>
              ))}
            </div>
          </section>
          <section>
            <h2 className="ac-h2" style={{ marginBottom: 8 }}>Recently Returned / Rejected</h2>
            <div className="ac-flex ac-flex-col ac-gap-2">
              {recentlyReturned.length === 0 && <p className="ac-text-sm ac-text-muted">None yet.</p>}
              {recentlyReturned.map((r) => (
                <Link key={r.workOrder.id} href={`/maintenance/inspections/${r.workOrder.id}`} className="ac-card" style={{ display: "block" }}>
                  <span className="ac-mono">{r.workOrder.workOrderNumber}</span> <span className="ac-text-muted ac-text-sm">{r.reviewedAt ? new Date(r.reviewedAt).toLocaleString() : ""}</span>
                </Link>
              ))}
            </div>
          </section>
        </div>
      )}

      <div className="ac-card ac-section" style={{ padding: "var(--ac-space-4)" }}>
        <div className="ac-flex ac-gap-3" style={{ flexWrap: "wrap" }}>
          <select className="ac-input" style={{ width: 200 }} value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} aria-label="Filter by inspection status">
            <option value="ALL">All Inspection Statuses</option>
            <option value="PENDING_INSPECTION">Pending Inspection</option>
            <option value="APPROVED">Approved</option>
            <option value="REJECTED">Rejected</option>
            <option value="RETURNED_FOR_CORRECTION">Returned for Correction</option>
          </select>
          <select className="ac-input" style={{ width: 160 }} value={priorityFilter} onChange={(e) => setPriorityFilter(e.target.value)} aria-label="Filter by priority">
            <option value="ALL">All Priorities</option>
            <option value="LOW">Low</option>
            <option value="MEDIUM">Medium</option>
            <option value="HIGH">High</option>
            <option value="CRITICAL">Critical</option>
          </select>
          <select className="ac-input" style={{ width: 180 }} value={aircraftFilter} onChange={(e) => setAircraftFilter(e.target.value)} aria-label="Filter by aircraft">
            <option value="ALL">All Aircraft</option>
            {aircraftOptions.map((id) => {
              const a = getAircraftById(id);
              return a ? <option key={id} value={id}>{currentRegistration(a)}</option> : null;
            })}
          </select>
        </div>
      </div>

      <div className="ac-card" style={{ padding: 0 }}>
        <DataTable columns={columns} rows={filtered} getRowHref={(r) => `/maintenance/inspections/${r.workOrder.id}`} emptyMessage="No work orders currently awaiting inspection." />
      </div>
    </div>
  );
}

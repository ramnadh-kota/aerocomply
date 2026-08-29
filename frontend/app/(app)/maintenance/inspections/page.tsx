"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { StatusBadge, priorityBadge, inspectorReviewStatusBadge } from "@/components/status/StatusBadge";
import { workOrders } from "@/lib/mock/workOrders";
import { getInspectorReviewById } from "@/lib/mock/inspectorReviews";
import { getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
import { getProjectById } from "@/lib/mock/maintenanceProjects";
import { getTechnicianById } from "@/lib/mock/technicians";
import { getRequirementById } from "@/lib/mock/regulations";
import { defectsForWorkOrder } from "@/lib/mock/defects";
import type { WorkOrder, InspectorReviewStatus } from "@/lib/mock/types";

interface Row {
  workOrder: WorkOrder;
  reviewStatus: InspectorReviewStatus;
  submittedAt: string | null;
}

function buildRows(): Row[] {
  return workOrders
    .filter((w) => w.inspectorReviewId)
    .map((w) => {
      const review = getInspectorReviewById(w.inspectorReviewId!);
      return {
        workOrder: w,
        reviewStatus: review?.status ?? "PENDING_INSPECTION",
        submittedAt: w.signOff?.timestamp ?? null,
      };
    });
}

export default function InspectionQueuePage() {
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [priorityFilter, setPriorityFilter] = useState("ALL");
  const [aircraftFilter, setAircraftFilter] = useState("ALL");

  const rows = useMemo(buildRows, []);
  const aircraftOptions = useMemo(() => Array.from(new Set(rows.map((r) => r.workOrder.aircraftId))), [rows]);

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

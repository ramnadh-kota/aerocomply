"use client";

import { useState } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { StatusBadge, workOrderStatusBadge, priorityBadge } from "@/components/status/StatusBadge";
import { workOrders } from "@/lib/mock/workOrders";
import { getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
import { getTechnicianById } from "@/lib/mock/technicians";
import type { WorkOrder, WorkOrderStatus } from "@/lib/mock/types";

const STATUSES: WorkOrderStatus[] = ["PLANNED", "OPEN", "IN_PROGRESS", "AWAITING_PARTS", "AWAITING_REVIEW", "COMPLETED", "OVERDUE", "DEFERRED"];

export default function WorkOrdersListPage() {
  const [statusFilter, setStatusFilter] = useState<string>("ALL");

  const rows = workOrders.filter((w) => statusFilter === "ALL" || w.status === statusFilter);

  const columns: Column<WorkOrder>[] = [
    { key: "num", header: "WO#", render: (w) => <span className="ac-mono">{w.workOrderNumber}</span>, sortValue: (w) => w.workOrderNumber },
    { key: "title", header: "Task", render: (w) => w.title },
    {
      key: "aircraft",
      header: "Aircraft",
      render: (w) => {
        const a = getAircraftById(w.aircraftId);
        return a ? <Link href={`/aircraft/${a.id}`} className="ac-mono">{currentRegistration(a)}</Link> : w.aircraftId;
      },
    },
    { key: "priority", header: "Priority", render: (w) => <StatusBadge {...priorityBadge(w.priority)} /> },
    { key: "tech", header: "Assigned Technician", render: (w) => (w.assignedTechnicianId ? getTechnicianById(w.assignedTechnicianId)?.name : "Unassigned") },
    { key: "due", header: "Due Date", render: (w) => w.dueDate, sortValue: (w) => w.dueDate },
    { key: "status", header: "Status", render: (w) => <StatusBadge {...workOrderStatusBadge(w.status)} /> },
  ];

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Maintenance", href: "/maintenance/projects" }, { label: "Work Orders" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Work Orders</h1>
          <p className="ac-subtitle">{rows.length} of {workOrders.length} shown</p>
        </div>
      </div>

      <div className="ac-flex ac-gap-2 ac-section" style={{ flexWrap: "wrap" }}>
        <button className="ac-btn" style={statusFilter === "ALL" ? { borderColor: "var(--ac-accent)", color: "var(--ac-accent-hover)" } : undefined} onClick={() => setStatusFilter("ALL")}>
          All
        </button>
        {STATUSES.map((s) => (
          <button key={s} className="ac-btn" style={statusFilter === s ? { borderColor: "var(--ac-accent)", color: "var(--ac-accent-hover)" } : undefined} onClick={() => setStatusFilter(s)}>
            {s.replace(/_/g, " ")}
          </button>
        ))}
      </div>

      <div className="ac-card" style={{ padding: 0 }}>
        <DataTable columns={columns} rows={rows} getRowHref={(w) => `/maintenance/work-orders/${w.id}`} />
      </div>
    </div>
  );
}

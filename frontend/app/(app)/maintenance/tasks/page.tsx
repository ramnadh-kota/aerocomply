"use client";

import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge, workOrderStatusBadge } from "@/components/status/StatusBadge";
import { workOrders } from "@/lib/mock/workOrders";
import { checklists } from "@/lib/mock/checklists";
import { getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
import { getTechnicianById } from "@/lib/mock/technicians";

export default function TasksChecklistsPage() {
  const tasksWithChecklists = checklists.map((c) => ({
    checklist: c,
    workOrder: workOrders.find((w) => w.id === c.workOrderId)!,
  }));

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Maintenance", href: "/maintenance/projects" }, { label: "Tasks / Checklists" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Tasks / Checklists</h1>
          <p className="ac-subtitle">{tasksWithChecklists.length} work-order tasks with a smart technician checklist</p>
        </div>
      </div>

      <div className="ac-flex ac-flex-col ac-gap-3">
        {tasksWithChecklists.map(({ checklist, workOrder }) => {
          const aircraft = getAircraftById(workOrder.aircraftId);
          const technician = workOrder.assignedTechnicianId ? getTechnicianById(workOrder.assignedTechnicianId) : undefined;
          return (
            <Link key={checklist.id} href={`/maintenance/work-orders/${workOrder.id}`} className="ac-card" style={{ display: "block" }}>
              <div className="ac-flex ac-justify-between ac-items-center" style={{ marginBottom: 6 }}>
                <span style={{ fontWeight: 600 }}>{checklist.title}</span>
                <StatusBadge {...workOrderStatusBadge(workOrder.status)} />
              </div>
              <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
                <span className="ac-mono">{workOrder.workOrderNumber}</span> · {aircraft ? currentRegistration(aircraft) : workOrder.aircraftId} ·{" "}
                {technician ? technician.name : "Unassigned"} · {checklist.items.length} checklist items
              </p>
            </Link>
          );
        })}
      </div>
    </div>
  );
}

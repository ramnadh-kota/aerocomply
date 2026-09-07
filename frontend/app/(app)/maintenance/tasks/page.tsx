"use client";

import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge, workOrderStatusBadge, checklistResultBadge } from "@/components/status/StatusBadge";
import { workOrders } from "@/lib/mock/workOrders";
import { checklists } from "@/lib/mock/checklists";
import { getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
import { getTechnicianById } from "@/lib/mock/technicians";
import { useMroState } from "@/lib/mro-state/MroStateContext";

export default function TasksChecklistsPage() {
  const { submissions } = useMroState();
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
          // Same live checklist state the technician/inspector screens use — see lib/mro-state/MroStateContext.
          const record = submissions[workOrder.id];
          const itemResults = record ? Object.values(record.items) : [];
          const completed = itemResults.filter((i) => i.result !== null).length;
          return (
            <Link key={checklist.id} href={`/maintenance/work-orders/${workOrder.id}`} className="ac-card" style={{ display: "block" }}>
              <div className="ac-flex ac-justify-between ac-items-center" style={{ marginBottom: 6 }}>
                <span style={{ fontWeight: 600 }}>{checklist.title}</span>
                <div className="ac-flex ac-gap-2">
                  {record && <StatusBadge status={record.submissionStatus === "SUBMITTED" ? "ACTIVE" : "PENDING"} label={record.submissionStatus === "SUBMITTED" ? "Submitted" : "In Progress"} />}
                  <StatusBadge {...workOrderStatusBadge(workOrder.status)} />
                </div>
              </div>
              <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
                <span className="ac-mono">{workOrder.workOrderNumber}</span> · {aircraft ? currentRegistration(aircraft) : workOrder.aircraftId} ·{" "}
                {technician ? technician.name : "Unassigned"} · {checklist.items.length} checklist items
                {record && ` · ${completed}/${itemResults.length} recorded`}
              </p>
              {record && itemResults.some((i) => i.result === "UNKNOWN" || i.result === "FAIL") && (
                <div className="ac-flex ac-gap-2" style={{ marginTop: 6 }}>
                  {itemResults.some((i) => i.result === "UNKNOWN") && <StatusBadge {...checklistResultBadge("UNKNOWN")} />}
                  {itemResults.some((i) => i.result === "FAIL") && <StatusBadge {...checklistResultBadge("FAIL")} />}
                </div>
              )}
            </Link>
          );
        })}
      </div>
    </div>
  );
}

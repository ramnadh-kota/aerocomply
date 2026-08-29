"use client";

import Link from "next/link";
import { notFound } from "next/navigation";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge, workOrderStatusBadge, priorityBadge } from "@/components/status/StatusBadge";
import { getTechnicianById, isOnShiftNow } from "@/lib/mock/technicians";
import { workOrdersForTechnician } from "@/lib/mock/workOrders";
import { getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
import { getChecklistByWorkOrderId } from "@/lib/mock/checklists";

export default function TechnicianWorkbenchPage({ params }: { params: { id: string } }) {
  const technician = getTechnicianById(params.id);
  if (!technician) notFound();

  const tasks = workOrdersForTechnician(technician.id);
  const overdue = tasks.filter((t) => t.status === "OVERDUE");
  const awaitingSignOff = tasks.filter((t) => t.status === "AWAITING_REVIEW");
  const priorityTasks = tasks.filter((t) => t.priority === "HIGH" || t.priority === "CRITICAL");
  const completed = tasks.filter((t) => t.status === "COMPLETED").length;
  const completionPercent = tasks.length > 0 ? Math.round((completed / tasks.length) * 100) : 0;
  const assignedAircraft = Array.from(new Set(tasks.map((t) => t.aircraftId)));

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Dashboard", href: "/dashboard" },
          { label: "Maintenance", href: "/maintenance/projects" },
          { label: "Technician Workbench", href: "/maintenance/technicians" },
          { label: technician.name },
        ]}
      />

      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">{technician.name} — {technician.role}</h1>
          <p className="ac-subtitle">Shift: {technician.shiftStart}–{technician.shiftEnd} · {technician.certifications.join(", ")}</p>
        </div>
        <StatusBadge status={isOnShiftNow(technician) ? "ACTIVE" : "STORED"} label={isOnShiftNow(technician) ? "On Shift" : "Off Shift"} />
      </div>

      <div className="ac-kpi-grid ac-section">
        <div className="ac-kpi-card">
          <p className="ac-kpi-label">Today&rsquo;s Tasks</p>
          <p className="ac-kpi-value">{tasks.length}</p>
        </div>
        <div className="ac-kpi-card">
          <p className="ac-kpi-label">Priority Tasks</p>
          <p className="ac-kpi-value">{priorityTasks.length}</p>
        </div>
        <div className="ac-kpi-card">
          <p className="ac-kpi-label">Overdue</p>
          <p className="ac-kpi-value">{overdue.length}</p>
        </div>
        <div className="ac-kpi-card">
          <p className="ac-kpi-label">Awaiting Sign-off</p>
          <p className="ac-kpi-value">{awaitingSignOff.length}</p>
        </div>
        <div className="ac-kpi-card">
          <p className="ac-kpi-label">Completion</p>
          <p className="ac-kpi-value">{completionPercent}%</p>
        </div>
      </div>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Assigned Aircraft</h2>
        <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
          {assignedAircraft.length === 0 && <p className="ac-text-sm ac-text-muted">No aircraft assigned today.</p>}
          {assignedAircraft.map((id) => {
            const a = getAircraftById(id);
            return a ? (
              <Link key={id} href={`/aircraft/${a.id}`} className="ac-btn">
                {currentRegistration(a)}
              </Link>
            ) : null;
          })}
        </div>
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Today&rsquo;s Assigned Work</h2>
        <div className="ac-flex ac-flex-col ac-gap-3">
          {tasks.length === 0 && <p className="ac-text-sm ac-text-muted">No work orders assigned.</p>}
          {tasks.map((t) => {
            const aircraft = getAircraftById(t.aircraftId);
            const hasChecklist = Boolean(getChecklistByWorkOrderId(t.id));
            return (
              <Link key={t.id} href={`/maintenance/work-orders/${t.id}`} className="ac-card" style={{ display: "block" }}>
                <div className="ac-flex ac-justify-between ac-items-center" style={{ marginBottom: 6 }}>
                  <span className="ac-mono" style={{ fontWeight: 600 }}>{t.workOrderNumber}</span>
                  <div className="ac-flex ac-gap-2">
                    <StatusBadge {...priorityBadge(t.priority)} />
                    <StatusBadge {...workOrderStatusBadge(t.status)} />
                  </div>
                </div>
                <p style={{ margin: "0 0 4px", fontSize: 13 }}>{t.title}</p>
                <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
                  {aircraft ? currentRegistration(aircraft) : t.aircraftId} · Due {t.dueDate}
                  {hasChecklist && " · Checklist available"}
                </p>
              </Link>
            );
          })}
        </div>
      </section>
    </div>
  );
}

"use client";

import Link from "next/link";
import { notFound } from "next/navigation";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge, workOrderStatusBadge, priorityBadge } from "@/components/status/StatusBadge";
import { getTechnicianById, isOnShiftNow } from "@/lib/mock/technicians";
import { workOrdersForTechnician, isOverdue, MOCK_TODAY } from "@/lib/mock/workOrders";
import { getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
import { getChecklistByWorkOrderId } from "@/lib/mock/checklists";
import { getPartById } from "@/lib/mock/parts";
import { useMroState } from "@/lib/mro-state/MroStateContext";

export default function TechnicianWorkbenchPage({ params }: { params: { id: string } }) {
  const technician = getTechnicianById(params.id);
  if (!technician) notFound();
  const { submissions } = useMroState();

  const tasks = workOrdersForTechnician(technician.id);
  const overdue = tasks.filter((t) => isOverdue(t));
  const awaitingSignOff = tasks.filter((t) => t.status === "WAITING_INSPECTION");
  const priorityTasks = tasks.filter((t) => t.priority === "HIGH" || t.priority === "CRITICAL");
  const completed = tasks.filter((t) => t.status === "COMPLETED").length;
  const completionPercent = tasks.length > 0 ? Math.round((completed / tasks.length) * 100) : 0;
  const assignedAircraft = Array.from(new Set(tasks.map((t) => t.aircraftId)));

  // Single source of truth for checklist state — see lib/mro-state/MroStateContext.
  const myRecords = tasks
    .map((t) => submissions[t.id])
    .filter((r): r is NonNullable<typeof r> => Boolean(r) && r?.technicianId === technician.id);
  const itemCounts = myRecords.flatMap((r) => Object.values(r.items));
  const completedItems = itemCounts.filter((i) => i.result !== null).length;
  const checklistCompletionPercent = itemCounts.length > 0 ? Math.round((completedItems / itemCounts.length) * 100) : 0;
  const pendingSignOffs = myRecords.filter((r) => r.submissionStatus === "SUBMITTED" && !r.technicianSignOff).length;
  const findingsCreated = itemCounts.filter((i) => i.result === "FAIL").length;
  const evidenceAttached = itemCounts.filter((i) => i.evidenceAttached).length;
  const inProgressRecords = myRecords.filter((r) => r.submissionStatus === "IN_PROGRESS");
  const todaysTasks = tasks.filter((t) => t.dueDate <= MOCK_TODAY && t.status !== "COMPLETED" && t.status !== "CANCELLED");
  const requiredParts = Array.from(new Set(tasks.flatMap((t) => t.requiredPartIds))).map((id) => getPartById(id)).filter((p): p is NonNullable<typeof p> => Boolean(p));

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
          <p className="ac-kpi-value">{todaysTasks.length}</p>
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
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Checklist &amp; Sign-off Status</h2>
        <p className="ac-text-sm ac-text-muted" style={{ marginBottom: 8 }}>
          Sourced from the same checklist state the inspector reviews — see MroStateProvider. Session-only, not backend-persisted.
        </p>
        <div className="ac-kpi-grid">
          <div className="ac-kpi-card">
            <p className="ac-kpi-label">Checklist Completion</p>
            <p className="ac-kpi-value">{checklistCompletionPercent}%</p>
          </div>
          <div className="ac-kpi-card">
            <p className="ac-kpi-label">Pending Sign-offs</p>
            <p className="ac-kpi-value">{pendingSignOffs}</p>
          </div>
          <div className="ac-kpi-card">
            <p className="ac-kpi-label">Findings Created</p>
            <p className="ac-kpi-value">{findingsCreated}</p>
          </div>
          <div className="ac-kpi-card">
            <p className="ac-kpi-label">Evidence Attached</p>
            <p className="ac-kpi-value">{evidenceAttached}</p>
          </div>
          <div className="ac-kpi-card">
            <p className="ac-kpi-label">Workload</p>
            <p className="ac-kpi-value">{priorityTasks.length + overdue.length > 2 ? "High" : tasks.length > 0 ? "Normal" : "Idle"}</p>
          </div>
        </div>
        {inProgressRecords.length > 0 && (
          <p className="ac-text-sm ac-text-muted" style={{ marginTop: 8 }}>
            {inProgressRecords.length} checklist(s) still in progress, not yet submitted for inspection.
          </p>
        )}
      </section>

      {(overdue.length > 0 || priorityTasks.some((t) => t.status === "WAITING_PARTS")) && (
        <section className="ac-section">
          <div className="ac-card" style={{ borderColor: "var(--ac-status-review)", background: "rgba(232,163,61,0.06)" }}>
            <p className="ac-eyebrow" style={{ color: "var(--ac-status-review)", marginBottom: 6 }}>Compliance Warnings — Prototype</p>
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
              {overdue.map((t) => <li key={t.id}>{t.workOrderNumber} is overdue (due {t.dueDate}).</li>)}
              {priorityTasks.filter((t) => t.status === "WAITING_PARTS").map((t) => <li key={t.id}>{t.workOrderNumber} is waiting on parts.</li>)}
            </ul>
          </div>
        </section>
      )}

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Required Parts</h2>
        <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
          {requiredParts.length === 0 && <p className="ac-text-sm ac-text-muted">No parts required for current tasks.</p>}
          {requiredParts.map((p) => (
            <Link key={p.id} href="/maintenance/parts" className="ac-badge ac-badge-unknown">
              {p.partNumber} · {p.status.replace(/_/g, " ")}
            </Link>
          ))}
        </div>
      </section>

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

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge, workOrderStatusBadge, priorityBadge, genericStatusBadge } from "@/components/status/StatusBadge";
import { getTechnicianById, isOnShiftNow } from "@/lib/mock/technicians";
import { workOrdersForTechnician, isOverdue, MOCK_TODAY } from "@/lib/mock/workOrders";
import { getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
import { getChecklistByWorkOrderId } from "@/lib/mock/checklists";
import { getPartById } from "@/lib/mock/parts";
import { useMroState } from "@/lib/mro-state/MroStateContext";
import { useDataMode } from "@/lib/data-mode/DataModeContext";
import { useSession } from "@/lib/auth/SessionContext";
import { usersApi, technicianQualificationsApi, type BackendOrganizationUser, type BackendTechnicianQualification } from "@/lib/api/technicians";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";

function RealTechnicianDetail({ userId }: { userId: string }) {
  const { accessToken, isAuthenticated } = useSession();
  const [user, setUser] = useState<BackendOrganizationUser | null>(null);
  const [qualifications, setQualifications] = useState<BackendTechnicianQualification[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<NormalizedApiError | null>(null);

  useEffect(() => {
    if (!isAuthenticated || !accessToken) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([usersApi.list(accessToken), technicianQualificationsApi.list(accessToken, userId)])
      .then(([users, quals]) => {
        if (cancelled) return;
        setUser(users.find((u) => u.id === userId) ?? null);
        setQualifications(quals);
      })
      .catch((err) => {
        if (!cancelled) setError(normalizeApiError(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [accessToken, isAuthenticated, userId]);

  if (!isAuthenticated) {
    return (
      <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
        <p className="ac-text-sm" style={{ margin: 0 }}>
          REAL data mode requires signing in. <Link href="/login">Sign in →</Link>
        </p>
      </div>
    );
  }

  return (
    <RealDataPanel loading={loading} error={error} isEmpty={!loading && !error && !user} emptyMessage="No user found with this ID in your organization.">
      {user && (
        <div>
          <div className="ac-section-header">
            <div>
              <h1 className="ac-h1">{user.full_name}</h1>
              <p className="ac-subtitle">{user.email} · {user.roles.join(", ") || "No roles"}</p>
            </div>
            <StatusBadge status={user.is_active ? "ACTIVE" : "STORED"} label={user.is_active ? "Active" : "Inactive"} />
          </div>
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Technician Qualifications</h2>
          {qualifications.length === 0 ? (
            <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
              <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
                No qualifications are on record for this person yet.
              </p>
            </div>
          ) : (
            <div className="ac-flex ac-flex-col ac-gap-3">
              {qualifications.map((q) => (
                <div key={q.id} className="ac-card">
                  <div className="ac-flex ac-justify-between ac-items-center" style={{ marginBottom: 6 }}>
                    <span style={{ fontWeight: 600 }}>{q.aircraft_type} — {q.qualification_type}</span>
                    <StatusBadge {...genericStatusBadge(q.revoked ? "REVOKED" : "ACTIVE")} />
                  </div>
                  <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
                    Granted {new Date(q.granted_at).toLocaleDateString()}
                    {q.expires_at ? ` · Expires ${new Date(q.expires_at).toLocaleDateString()}` : " · No expiry on record"}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </RealDataPanel>
  );
}

export default function TechnicianWorkbenchPage({ params }: { params: { id: string } }) {
  const { isReal, hydrated } = useDataMode();
  if (!hydrated) return null;
  return isReal ? (
    <div>
      <Breadcrumbs
        items={[
          { label: "Dashboard", href: "/dashboard" },
          { label: "Maintenance", href: "/maintenance/projects" },
          { label: "Technicians", href: "/maintenance/technicians" },
          { label: "Detail" },
        ]}
      />
      <RealTechnicianDetail userId={params.id} />
    </div>
  ) : (
    <DemoTechnicianWorkbenchPage id={params.id} />
  );
}

function DemoTechnicianWorkbenchPage({ id }: { id: string }) {
  const technician = getTechnicianById(id);
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
          <div className="ac-card" style={{ borderColor: "var(--ac-status-review)", background: "var(--ac-status-review-bg)" }}>
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

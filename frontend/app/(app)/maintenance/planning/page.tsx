import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge, priorityBadge } from "@/components/status/StatusBadge";
import { getMaintenanceAnalytics, getTechnicianWorkload, getPartsAtRisk } from "@/lib/mock/ai/analytics";
import { upcomingMaintenanceEvents } from "@/lib/mock/maintenance";
import { getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
import { maintenanceProjects } from "@/lib/mock/maintenanceProjects";
import { workOrders } from "@/lib/mock/workOrders";
import { WorkOrderPlanningTable } from "./WorkOrderPlanningTable";

export default function MaintenancePlanningPage() {
  const maintenance = getMaintenanceAnalytics();
  const workload = getTechnicianWorkload();
  const partsAtRisk = getPartsAtRisk();
  const upcoming = upcomingMaintenanceEvents(10);

  const available = workload.filter((t) => t.openWorkOrders === 0 && t.onShift);

  const activeProjects = maintenanceProjects.filter((p) => p.status === "IN_PROGRESS" || p.status === "PLANNED");
  const readinessPercent = activeProjects.length > 0 ? Math.round(activeProjects.reduce((sum, p) => sum + p.progressPercent, 0) / activeProjects.length) : null;

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Maintenance", href: "/maintenance/projects" }, { label: "Planning" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Maintenance Planning</h1>
          <p className="ac-subtitle">Forward-looking resource and readiness planning — every value is derived from current demo data.</p>
        </div>
        <Link href="/maintenance/operations" className="ac-btn" style={{ fontSize: 12, padding: "4px 10px" }}>Operations Command Center →</Link>
      </div>

      <WorkOrderPlanningTable />

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Fleet Planning Overview</h2>
        <div className="ac-kpi-grid">
          <div className="ac-kpi-card">
            <p className="ac-kpi-label">Maintenance Backlog</p>
            <p className="ac-kpi-value">{maintenance.totalOpenWorkOrders}</p>
          </div>
          <div className="ac-kpi-card">
            <p className="ac-kpi-label">Waiting Parts</p>
            <p className="ac-kpi-value">{maintenance.waitingParts}</p>
          </div>
          <div className="ac-kpi-card">
            <p className="ac-kpi-label">Available Technicians</p>
            <p className="ac-kpi-value">{available.length}</p>
          </div>
          <div className="ac-kpi-card">
            <p className="ac-kpi-label">Operational Readiness</p>
            <p className="ac-kpi-value">{readinessPercent === null ? "—" : `${readinessPercent}%`}</p>
          </div>
        </div>
      </section>

      <div className="ac-grid-2 ac-section">
        <section>
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Upcoming Maintenance Planner</h2>
          <div className="ac-card" style={{ padding: 0 }}>
            {upcoming.length === 0 ? (
              <p className="ac-text-sm ac-text-muted" style={{ padding: 12 }}>Insufficient source data.</p>
            ) : (
              <table className="ac-table">
                <thead><tr><th>Date</th><th>Aircraft</th><th>Description</th></tr></thead>
                <tbody>
                  {upcoming.map((e) => {
                    const ac = getAircraftById(e.aircraftId);
                    return (
                      <tr key={e.id}>
                        <td className="ac-mono ac-text-sm">{e.date}</td>
                        <td>{ac ? <Link href={`/aircraft/${ac.id}`} className="ac-mono">{currentRegistration(ac)}</Link> : e.aircraftId}</td>
                        <td className="ac-text-sm">{e.description}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        </section>

        <section>
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Parts-at-Risk Planning</h2>
          <div className="ac-card" style={{ padding: 0 }}>
            {partsAtRisk.length === 0 ? (
              <p className="ac-text-sm ac-text-muted" style={{ padding: 12 }}>Insufficient source data.</p>
            ) : (
              <table className="ac-table">
                <thead><tr><th>Part</th><th>Status</th><th>Work Order</th></tr></thead>
                <tbody>
                  {partsAtRisk.map((p) => {
                    const wo = p.workOrderId ? workOrders.find((w) => w.id === p.workOrderId) : undefined;
                    return (
                      <tr key={p.partNumber}>
                        <td className="ac-mono">{p.partNumber}</td>
                        <td>{p.status.replace(/_/g, " ")}</td>
                        <td>{wo ? <Link href={`/maintenance/work-orders/${wo.id}`}>{wo.workOrderNumber} ({wo.priority})</Link> : "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        </section>
      </div>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Technician Capacity &amp; Resource Allocation</h2>
        <div className="ac-card" style={{ padding: 0 }}>
          <table className="ac-table">
            <thead><tr><th>Technician</th><th>Open Work Orders</th><th>Overdue</th><th>On Shift</th><th>Capacity</th></tr></thead>
            <tbody>
              {workload.map((t) => (
                <tr key={t.technicianId}>
                  <td><Link href={`/maintenance/technicians/${t.technicianId}`}>{t.name}</Link></td>
                  <td>{t.openWorkOrders}</td>
                  <td>{t.overdueWorkOrders}</td>
                  <td>{t.onShift ? "Yes" : "No"}</td>
                  <td>
                    <StatusBadge
                      status={t.openWorkOrders === 0 ? "COMPLIANT" : t.openWorkOrders > 1 ? "NON_COMPLIANT" : "REVIEW_REQUIRED"}
                      label={t.openWorkOrders === 0 ? "Available" : t.openWorkOrders > 1 ? "Overloaded" : "Assigned"}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Active Projects — Readiness</h2>
        <div className="ac-grid-2">
          {activeProjects.length === 0 ? (
            <p className="ac-text-sm ac-text-muted">Insufficient source data.</p>
          ) : (
            activeProjects.map((p) => (
              <Link key={p.id} href={`/maintenance/projects/${p.id}`} className="ac-card" style={{ display: "block" }}>
                <div className="ac-flex ac-justify-between ac-items-center">
                  <span className="ac-mono" style={{ fontWeight: 600 }}>{p.projectNumber}</span>
                  <StatusBadge {...priorityBadge(p.priority)} />
                </div>
                <p className="ac-text-sm ac-text-muted" style={{ margin: "4px 0 0" }}>{p.title} · {p.progressPercent}% complete</p>
              </Link>
            ))
          )}
        </div>
      </section>
    </div>
  );
}

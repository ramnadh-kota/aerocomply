import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge, priorityBadge } from "@/components/status/StatusBadge";
import { getOperationsAnalytics } from "@/lib/mock/ai/analytics";
import { maintenanceProjects } from "@/lib/mock/maintenanceProjects";
import { workOrders } from "@/lib/mock/workOrders";

export default function MaintenanceOperationsPage() {
  const ops = getOperationsAnalytics(["wo-1042"]);

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Maintenance", href: "/maintenance/projects" }, { label: "Operations" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Maintenance Operations</h1>
          <p className="ac-subtitle">Fleet-wide MRO operational command center — every value is derived from current demo data.</p>
        </div>
        <div className="ac-flex ac-gap-2">
          <Link href="/ai" className="ac-btn" style={{ fontSize: 12, padding: "4px 10px" }}>Ask AI</Link>
          <Link href="/reports/fleet-risk" className="ac-btn" style={{ fontSize: 12, padding: "4px 10px" }}>Generate Report</Link>
        </div>
      </div>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Fleet Maintenance</h2>
        <div className="ac-kpi-grid">
          <Link href="/aircraft" className="ac-kpi-card" style={{ display: "block" }}>
            <p className="ac-kpi-label">Aircraft Requiring Maintenance</p>
            <p className="ac-kpi-value">{ops.aircraftRequiringMaintenance.length}</p>
          </Link>
          <Link href="/maintenance/defects" className="ac-kpi-card" style={{ display: "block" }}>
            <p className="ac-kpi-label">Aircraft Grounded (heuristic)</p>
            <p className="ac-kpi-value">{ops.aircraftGrounded.length}</p>
          </Link>
          <Link href="/maintenance/projects" className="ac-kpi-card" style={{ display: "block" }}>
            <p className="ac-kpi-label">Open Projects</p>
            <p className="ac-kpi-value">{ops.openProjects}</p>
          </Link>
          <Link href="/maintenance/work-orders" className="ac-kpi-card" style={{ display: "block" }}>
            <p className="ac-kpi-label">Open Work Orders</p>
            <p className="ac-kpi-value">{ops.openWorkOrders}</p>
          </Link>
        </div>
        {ops.aircraftGrounded.length > 0 && (
          <p className="ac-text-sm ac-text-muted" style={{ marginTop: 6 }}>
            &ldquo;Grounded&rdquo; here is a prototype heuristic (an aircraft with an open HIGH/CRITICAL defect) — not a stored aircraft status.
          </p>
        )}
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Work Orders by Status</h2>
        <div className="ac-card">
          <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
            {(["DRAFT", "ASSIGNED", "IN_PROGRESS", "WAITING_PARTS", "WAITING_INSPECTION", "COMPLETED", "CANCELLED"] as const).map((s) => (
              <Link key={s} href="/maintenance/work-orders" className="ac-badge ac-badge-unknown">
                {s.replace(/_/g, " ")}: {ops.workOrderStatusCounts[s] ?? 0}
              </Link>
            ))}
          </div>
        </div>
      </section>

      <div className="ac-grid-2 ac-section">
        <section>
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Risk</h2>
          <div className="ac-flex ac-flex-col ac-gap-2">
            <Link href="/maintenance/work-orders" className="ac-card" style={{ display: "block" }}>
              <div className="ac-flex ac-justify-between"><span>Overdue Work</span><strong>{ops.overdue}</strong></div>
            </Link>
            <Link href="/maintenance/work-orders" className="ac-card" style={{ display: "block" }}>
              <div className="ac-flex ac-justify-between"><span>High-Priority Work</span><strong>{ops.highPriority}</strong></div>
            </Link>
            <Link href="/maintenance/defects" className="ac-card" style={{ display: "block" }}>
              <div className="ac-flex ac-justify-between"><span>Open Defects</span><strong>{ops.openDefects}</strong></div>
            </Link>
            <Link href="/maintenance/work-orders/wo-1042" className="ac-card" style={{ display: "block" }}>
              <div className="ac-flex ac-justify-between"><span>Unknown Checklist Items</span><strong>{ops.unknownChecklistWorkOrderIds.length}</strong></div>
            </Link>
            <Link href="/maintenance/inspections" className="ac-card" style={{ display: "block" }}>
              <div className="ac-flex ac-justify-between"><span>Pending Inspections</span><strong>{ops.pendingInspections}</strong></div>
            </Link>
          </div>
        </section>

        <section>
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Resources</h2>
          <p className="ac-eyebrow" style={{ marginBottom: 6 }}>Technician Workload</p>
          <div className="ac-card" style={{ padding: 0, marginBottom: 12 }}>
            <table className="ac-table">
              <thead><tr><th>Technician</th><th>Open</th><th>Overdue</th><th>Shift</th></tr></thead>
              <tbody>
                {ops.technicianWorkload.filter((t) => t.openWorkOrders > 0).map((t) => (
                  <tr key={t.technicianId}>
                    <td><Link href={`/maintenance/technicians/${t.technicianId}`}>{t.name}</Link></td>
                    <td>{t.openWorkOrders}</td>
                    <td>{t.overdueWorkOrders}</td>
                    <td>{t.onShift ? "On" : "Off"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="ac-eyebrow" style={{ marginBottom: 6 }}>Parts At Risk</p>
          <div className="ac-card" style={{ padding: 0 }}>
            <table className="ac-table">
              <thead><tr><th>Part</th><th>Status</th><th>Work Order</th></tr></thead>
              <tbody>
                {ops.partsAtRisk.length === 0 && (
                  <tr><td colSpan={3} className="ac-text-sm ac-text-muted" style={{ textAlign: "center", padding: 12 }}>No parts currently at risk.</td></tr>
                )}
                {ops.partsAtRisk.map((p) => {
                  const wo = p.workOrderId ? workOrders.find((w) => w.id === p.workOrderId) : undefined;
                  return (
                    <tr key={p.partNumber}>
                      <td className="ac-mono">{p.partNumber}</td>
                      <td>{p.status.replace(/_/g, " ")}</td>
                      <td>{wo ? <Link href={`/maintenance/work-orders/${wo.id}`}>{wo.workOrderNumber}</Link> : "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Active Projects</h2>
        <div className="ac-grid-2">
          {maintenanceProjects.filter((p) => p.status === "IN_PROGRESS" || p.status === "PLANNED").map((p) => (
            <Link key={p.id} href={`/maintenance/projects/${p.id}`} className="ac-card" style={{ display: "block" }}>
              <div className="ac-flex ac-justify-between ac-items-center">
                <span className="ac-mono" style={{ fontWeight: 600 }}>{p.projectNumber}</span>
                <StatusBadge {...priorityBadge(p.priority)} />
              </div>
              <p className="ac-text-sm ac-text-muted" style={{ margin: "4px 0 0" }}>{p.title} · {p.progressPercent}% complete</p>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}

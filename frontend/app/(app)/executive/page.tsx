import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { Timeline } from "@/components/timeline/Timeline";
import { getFleetAnalytics, getMaintenanceAnalytics, getComplianceAnalytics, getInspectionAnalytics, getTechnicianWorkload, getPartsAtRisk } from "@/lib/mock/ai/analytics";
import { upcomingMaintenanceEvents } from "@/lib/mock/maintenance";
import { getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
import { getRequirementById } from "@/lib/mock/regulations";
import { workOrders } from "@/lib/mock/workOrders";
import { auditEvents } from "@/lib/mock/audit";

const SUGGESTED_QUESTIONS = [
  "What is putting the fleet at risk?",
  "Which aircraft need attention?",
  "Which work orders are most likely to miss their target?",
  "What compliance issues need human review?",
  "Where are parts creating operational risk?",
  "Which inspections should be prioritized?",
];

export default function ExecutiveControlCenterPage() {
  const fleet = getFleetAnalytics();
  const maintenance = getMaintenanceAnalytics();
  const compliance = getComplianceAnalytics();
  const inspection = getInspectionAnalytics();
  const workload = getTechnicianWorkload().filter((t) => t.openWorkOrders > 0);
  const partsAtRisk = getPartsAtRisk();
  const regulatoryDeadlines = upcomingMaintenanceEvents(8).filter((e) => e.relatedRequirementId);
  const rankedAircraft = [...fleet.aircraftAtRisk].sort((a, b) => (a.risk === b.risk ? 0 : a.risk === "HIGH" ? -1 : 1));
  const recentAudit = auditEvents.slice(0, 8);

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Executive Control Center" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Executive Operations Control Center</h1>
          <p className="ac-subtitle">Fleet-wide compliance and maintenance cockpit — every value is derived from current demo data.</p>
        </div>
        <div className="ac-flex ac-gap-2">
          <Link href="/ai" className="ac-btn ac-btn-primary" style={{ fontSize: 12, padding: "4px 10px" }}>Ask AeroComply AI</Link>
          <Link href="/reports/fleet-risk" className="ac-btn" style={{ fontSize: 12, padding: "4px 10px" }}>Generate Executive Report</Link>
        </div>
      </div>

      {/* Top-level KPIs */}
      <section className="ac-section">
        <div className="ac-kpi-grid">
          <Link href="/aircraft" className="ac-kpi-card" style={{ display: "block" }}>
            <p className="ac-kpi-label">Fleet Health</p>
            <p className="ac-kpi-value">{fleet.fleetSize - fleet.aircraftAtRisk.length}/{fleet.fleetSize}</p>
          </Link>
          <Link href="/maintenance/operations" className="ac-kpi-card" style={{ display: "block" }}>
            <p className="ac-kpi-label">Maintenance Backlog</p>
            <p className="ac-kpi-value">{maintenance.totalOpenWorkOrders}</p>
          </Link>
          <Link href="/compliance" className="ac-kpi-card" style={{ display: "block" }}>
            <p className="ac-kpi-label">Compliance Risk</p>
            <p className="ac-kpi-value">{compliance.nonCompliant + compliance.reviewRequired}</p>
          </Link>
          <Link href="/maintenance/inspections" className="ac-kpi-card" style={{ display: "block" }}>
            <p className="ac-kpi-label">Pending Inspections</p>
            <p className="ac-kpi-value">{inspection.pending.length}</p>
          </Link>
          <Link href="/maintenance/parts" className="ac-kpi-card" style={{ display: "block" }}>
            <p className="ac-kpi-label">Parts Risk</p>
            <p className="ac-kpi-value">{partsAtRisk.length}</p>
          </Link>
          <Link href="/maintenance/work-orders" className="ac-kpi-card" style={{ display: "block" }}>
            <p className="ac-kpi-label">Overdue Work</p>
            <p className="ac-kpi-value">{maintenance.overdue.length}</p>
          </Link>
          <Link href="/aircraft" className="ac-kpi-card" style={{ display: "block" }}>
            <p className="ac-kpi-label">Aircraft at Risk</p>
            <p className="ac-kpi-value">{fleet.aircraftAtRisk.length}</p>
          </Link>
        </div>
      </section>

      <div className="ac-grid-2 ac-section">
        <section>
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Aircraft at Risk</h2>
          <div className="ac-card" style={{ padding: 0 }}>
            {rankedAircraft.length === 0 ? (
              <p className="ac-text-sm ac-text-muted" style={{ padding: 12 }}>Insufficient source data.</p>
            ) : (
              <table className="ac-table">
                <thead><tr><th>Aircraft</th><th>Risk</th></tr></thead>
                <tbody>
                  {rankedAircraft.map((a) => (
                    <tr key={a.aircraftId}>
                      <td><Link href={`/fleet/aircraft/${a.aircraftId}/health`} className="ac-mono">{a.registration}</Link></td>
                      <td><StatusBadge status={a.risk === "HIGH" ? "NON_COMPLIANT" : "REVIEW_REQUIRED"} label={a.risk} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>

        <section>
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Work Orders at Risk</h2>
          <div className="ac-card" style={{ padding: 0 }}>
            {maintenance.overdue.length === 0 ? (
              <p className="ac-text-sm ac-text-muted" style={{ padding: 12 }}>Insufficient source data.</p>
            ) : (
              <table className="ac-table">
                <thead><tr><th>Work Order</th><th>Due</th><th>Priority</th></tr></thead>
                <tbody>
                  {maintenance.overdue.map((w) => (
                    <tr key={w.id}>
                      <td><Link href={`/maintenance/work-orders/${w.id}`} className="ac-mono">{w.label}</Link></td>
                      <td className="ac-mono ac-text-sm">{w.dueDate}</td>
                      <td>{w.priority}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>
      </div>

      <div className="ac-grid-2 ac-section">
        <section>
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Parts at Risk</h2>
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
                        <td>{wo ? <Link href={`/maintenance/work-orders/${wo.id}`}>{wo.workOrderNumber}</Link> : "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        </section>

        <section>
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Regulatory Deadlines</h2>
          <div className="ac-card" style={{ padding: 0 }}>
            {regulatoryDeadlines.length === 0 ? (
              <p className="ac-text-sm ac-text-muted" style={{ padding: 12 }}>Insufficient source data.</p>
            ) : (
              <table className="ac-table">
                <thead><tr><th>Date</th><th>Aircraft</th><th>Requirement</th></tr></thead>
                <tbody>
                  {regulatoryDeadlines.map((e) => {
                    const req = getRequirementById(e.relatedRequirementId!);
                    const ac = getAircraftById(e.aircraftId);
                    return (
                      <tr key={e.id}>
                        <td className="ac-mono ac-text-sm">{e.date}</td>
                        <td>{ac ? <Link href={`/aircraft/${ac.id}`} className="ac-mono">{currentRegistration(ac)}</Link> : e.aircraftId}</td>
                        <td>{req ? <Link href={`/regulations/${req.id}`} className="ac-mono">{req.requirementNumber}</Link> : "—"}</td>
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
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Technician Capacity</h2>
        <div className="ac-card" style={{ padding: 0 }}>
          {workload.length === 0 ? (
            <p className="ac-text-sm ac-text-muted" style={{ padding: 12 }}>Insufficient source data.</p>
          ) : (
            <table className="ac-table">
              <thead><tr><th>Technician</th><th>Open</th><th>Overdue</th><th>On Shift</th></tr></thead>
              <tbody>
                {workload.map((t) => (
                  <tr key={t.technicianId}>
                    <td><Link href={`/maintenance/technicians/${t.technicianId}`}>{t.name}</Link></td>
                    <td>{t.openWorkOrders}</td>
                    <td>{t.overdueWorkOrders}</td>
                    <td>{t.onShift ? "Yes" : "No"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>

      <section className="ac-section">
        <div className="ac-card" style={{ borderStyle: "dashed" }}>
          <p className="ac-eyebrow" style={{ marginBottom: 8 }}>AI Operations Insight — Prototype</p>
          <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap", marginBottom: 8 }}>
            {SUGGESTED_QUESTIONS.map((q) => (
              <Link key={q} href={`/ai?q=${encodeURIComponent(q)}`} className="ac-btn" style={{ fontSize: 12, padding: "4px 8px" }}>
                {q}
              </Link>
            ))}
          </div>
          <p className="ac-text-sm" style={{ margin: 0, fontWeight: 600 }}>
            AI-assisted analysis — non-authoritative. Verify against source records before operational decisions.
          </p>
        </div>
      </section>

      <div className="ac-grid-2 ac-section">
        <section>
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Recent Audit Activity</h2>
          <div className="ac-card">
            {recentAudit.length === 0 ? (
              <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Insufficient source data.</p>
            ) : (
              <Timeline
                entries={recentAudit.map((e) => ({
                  id: e.id,
                  date: new Date(e.timestamp).toLocaleString(),
                  title: e.action.replace(/_/g, " ").replace(/\./g, " — "),
                  detail: `${e.actor} (${e.actorRole})`,
                }))}
              />
            )}
          </div>
          <p className="ac-text-sm ac-text-muted" style={{ marginTop: 6 }}>
            <Link href="/audit">Open full Audit Trail →</Link>
          </p>
        </section>

        <section>
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Quick Actions</h2>
          <div className="ac-flex ac-flex-col ac-gap-2">
            <Link href="/maintenance/operations" className="ac-card">Maintenance Operations →</Link>
            <Link href="/maintenance/inspections" className="ac-card">Inspection Queue →</Link>
            <Link href="/compliance" className="ac-card">Compliance Intelligence →</Link>
            <Link href="/reports" className="ac-card">Reports →</Link>
            <Link href="/organization/users" className="ac-card">Role &amp; User Management →</Link>
          </div>
        </section>
      </div>
    </div>
  );
}

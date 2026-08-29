import Link from "next/link";
import { StatusBadge } from "@/components/status/StatusBadge";
import { CoreLoopDiagram } from "@/components/core-loop/CoreLoopDiagram";
import { assessments } from "@/lib/mock/assessments";
import { getAircraftById, currentRegistration, getAircraftVariant } from "@/lib/mock/aircraft";
import { getRequirementById } from "@/lib/mock/regulations";
import { evidenceForAssessment } from "@/lib/mock/evidence";
import { overdueMaintenanceEvents, upcomingMaintenanceEvents } from "@/lib/mock/maintenance";
import { activeProjects } from "@/lib/mock/maintenanceProjects";
import { openWorkOrders, overdueWorkOrders, awaitingPartsWorkOrders, awaitingReviewWorkOrders } from "@/lib/mock/workOrders";
import { techniciansOnShift } from "@/lib/mock/technicians";
import { workOrderStatusBadge, priorityBadge, projectStatusBadge } from "@/components/status/StatusBadge";
import { inspectorReviews } from "@/lib/mock/inspectorReviews";
import { findings } from "@/lib/mock/findings";
import { getFleetAnalytics, getMaintenanceAnalytics, getComplianceAnalytics, getInspectionAnalytics } from "@/lib/mock/ai/analytics";
import { ViewingAsBadge } from "@/components/layout/ViewingAsBadge";

const KPIS = [
  { label: "Total Aircraft", value: "128", href: "/aircraft" },
  { label: "Applicable Requirements", value: "1,846", href: "/regulations" },
  { label: "Assessments Requiring Review", value: "14", href: "/assessments" },
  { label: "Insufficient Data", value: "7", href: "/assessments" },
  { label: "Critical Compliance Issues", value: "3", href: "/assessments" },
];

const DISTRIBUTION = [
  { label: "Compliant", pct: 92, color: "var(--ac-status-compliant)" },
  { label: "Review Required", pct: 5, color: "var(--ac-status-review)" },
  { label: "Insufficient Data", pct: 2, color: "var(--ac-status-insufficient)" },
  { label: "Non-Compliant", pct: 1, color: "var(--ac-status-non-compliant)" },
];

const ATTENTION_ITEMS = [
  { text: "3 assessments require engineering review", href: "/assessments" },
  { text: "2 aircraft have incomplete configuration evidence", href: "/aircraft" },
  { text: "1 component installation history has a missing removal date", href: "/components" },
  { text: "1 applicability condition cannot be resolved", href: "/assessments/asmt-1" },
];

export default function DashboardPage() {
  const recent = [...assessments].sort((a, b) => b.evaluatedAt.localeCompare(a.evaluatedAt)).slice(0, 6);
  const openReviews = assessments.filter((a) => a.humanDecision === "PENDING" || a.humanDecision === "REQUEST_MORE_EVIDENCE");
  const overdue = overdueMaintenanceEvents();
  const upcoming = upcomingMaintenanceEvents(5);
  const projects = activeProjects();
  const openWOs = openWorkOrders();
  const overdueWOs = overdueWorkOrders();
  const awaitingPartsWOs = awaitingPartsWorkOrders();
  const awaitingReviewWOs = awaitingReviewWorkOrders();
  const onShift = techniciansOnShift();
  const criticalWOs = openWOs.filter((w) => w.priority === "CRITICAL" || w.priority === "HIGH").slice(0, 5);
  const inspectionsAwaitingReview = inspectorReviews.filter((r) => r.status === "PENDING_INSPECTION").length;
  const checklistExceptions = findings.filter((f) => f.requiresDefect).length;
  const fleetAnalytics = getFleetAnalytics();
  const maintAnalytics = getMaintenanceAnalytics();
  const complianceAnalytics = getComplianceAnalytics();
  const inspectionAnalytics = getInspectionAnalytics();

  return (
    <div>
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Compliance Intelligence</h1>
          <p className="ac-subtitle">Fleet regulatory applicability and assessment overview</p>
        </div>
      </div>

      <section className="ac-section">
        <div className="ac-kpi-grid">
          {KPIS.map((kpi) => (
            <Link key={kpi.label} href={kpi.href} className="ac-kpi-card" style={{ display: "block" }}>
              <p className="ac-kpi-label">{kpi.label}</p>
              <p className="ac-kpi-value">{kpi.value}</p>
            </Link>
          ))}
        </div>
      </section>

      <section className="ac-section">
        <div className="ac-card">
          <p className="ac-eyebrow" style={{ marginBottom: 10 }}>
            The AeroComply Loop
          </p>
          <CoreLoopDiagram />
        </div>
      </section>

      <section className="ac-section">
        <div className="ac-kpi-grid">
          <Link href="/maintenance/projects" className="ac-kpi-card" style={{ display: "block" }}>
            <p className="ac-kpi-label">Active Maintenance Projects</p>
            <p className="ac-kpi-value">{projects.length}</p>
          </Link>
          <Link href="/maintenance/work-orders" className="ac-kpi-card" style={{ display: "block" }}>
            <p className="ac-kpi-label">Open Work Orders</p>
            <p className="ac-kpi-value">{openWOs.length}</p>
          </Link>
          <Link href="/maintenance/work-orders" className="ac-kpi-card" style={{ display: "block" }}>
            <p className="ac-kpi-label">Overdue Tasks</p>
            <p className="ac-kpi-value">{overdueWOs.length}</p>
          </Link>
          <Link href="/maintenance/technicians" className="ac-kpi-card" style={{ display: "block" }}>
            <p className="ac-kpi-label">Technicians On Shift</p>
            <p className="ac-kpi-value">{onShift.length}</p>
          </Link>
          <Link href="/maintenance/parts" className="ac-kpi-card" style={{ display: "block" }}>
            <p className="ac-kpi-label">Awaiting Parts</p>
            <p className="ac-kpi-value">{awaitingPartsWOs.length}</p>
          </Link>
          <Link href="/maintenance/work-orders" className="ac-kpi-card" style={{ display: "block" }}>
            <p className="ac-kpi-label">Work Orders Waiting Inspection</p>
            <p className="ac-kpi-value">{awaitingReviewWOs.length}</p>
          </Link>
          <Link href="/maintenance/inspections" className="ac-kpi-card" style={{ display: "block" }}>
            <p className="ac-kpi-label">Inspections Awaiting Review</p>
            <p className="ac-kpi-value">{inspectionsAwaitingReview}</p>
          </Link>
          <Link href="/maintenance/defects" className="ac-kpi-card" style={{ display: "block" }}>
            <p className="ac-kpi-label">Checklist Exceptions</p>
            <p className="ac-kpi-value">{checklistExceptions}</p>
          </Link>
        </div>
      </section>

      <section className="ac-section">
        <div className="ac-section-header">
          <h2 className="ac-h2">AI &amp; Operations Intelligence</h2>
          <span className="ac-text-sm ac-text-muted">AI Prototype · Non-authoritative</span>
        </div>
        <div className="ac-grid-4" style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "var(--ac-space-4)" }}>
          <div className="ac-card">
            <p className="ac-kpi-label">Fleet Risk</p>
            <p className="ac-kpi-value">{fleetAnalytics.aircraftAtRisk.length} / {fleetAnalytics.fleetSize}</p>
            <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>aircraft at elevated risk</p>
          </div>
          <div className="ac-card">
            <p className="ac-kpi-label">Maintenance Risk</p>
            <p className="ac-kpi-value">{maintAnalytics.overdue.length}</p>
            <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>overdue work orders</p>
          </div>
          <div className="ac-card">
            <p className="ac-kpi-label">Compliance Exposure</p>
            <p className="ac-kpi-value">{complianceAnalytics.nonCompliant + complianceAnalytics.reviewRequired}</p>
            <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>assessments needing attention</p>
          </div>
          <div className="ac-card">
            <p className="ac-kpi-label">Inspection Queue</p>
            <p className="ac-kpi-value">{inspectionAnalytics.pending.length}</p>
            <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>awaiting review</p>
          </div>
        </div>
        <div className="ac-flex ac-gap-2 ac-items-center" style={{ marginTop: 12, flexWrap: "wrap" }}>
          <Link href="/ai" className="ac-btn ac-btn-primary">Ask AeroComply AI</Link>
          <Link href="/executive" className="ac-btn">Executive Intelligence</Link>
          <Link href="/maintenance/operations" className="ac-btn">Maintenance Operations</Link>
          <Link href="/maintenance/inspections" className="ac-btn">Inspection Queue</Link>
          <Link href="/compliance" className="ac-btn">Compliance Intelligence</Link>
          <Link href="/reports/fleet-risk" className="ac-btn">Generate Operations Report</Link>
          <Link href="/reports" className="ac-btn">Reports</Link>
          <Link href="/organization/roles" className="ac-btn">Role Management</Link>
          <ViewingAsBadge />
        </div>
      </section>

      <section className="ac-section">
        <div className="ac-section-header">
          <h2 className="ac-h2">Maintenance Operations</h2>
          <Link href="/maintenance/projects" className="ac-text-sm">View all →</Link>
        </div>
        <div className="ac-grid-2">
          <div>
            <p className="ac-eyebrow" style={{ marginBottom: 8 }}>Active Projects</p>
            <div className="ac-flex ac-flex-col ac-gap-2">
              {projects.map((p) => {
                const ac = getAircraftById(p.aircraftId);
                return (
                  <Link key={p.id} href={`/maintenance/projects/${p.id}`} className="ac-card" style={{ display: "block" }}>
                    <div className="ac-flex ac-justify-between ac-items-center">
                      <span className="ac-mono" style={{ fontWeight: 600, fontSize: 13 }}>{p.title}</span>
                      <StatusBadge {...projectStatusBadge(p.status)} />
                    </div>
                    <p className="ac-text-sm ac-text-muted" style={{ margin: "4px 0 0" }}>
                      {ac ? currentRegistration(ac) : p.aircraftId} · {p.progressPercent}% complete
                    </p>
                  </Link>
                );
              })}
            </div>
          </div>
          <div>
            <p className="ac-eyebrow" style={{ marginBottom: 8 }}>Critical Work Orders</p>
            <div className="ac-flex ac-flex-col ac-gap-2">
              {criticalWOs.map((w) => (
                <Link key={w.id} href={`/maintenance/work-orders/${w.id}`} className="ac-card" style={{ display: "block" }}>
                  <div className="ac-flex ac-justify-between ac-items-center">
                    <span className="ac-mono" style={{ fontWeight: 600, fontSize: 13 }}>{w.workOrderNumber}</span>
                    <div className="ac-flex ac-gap-2">
                      <StatusBadge {...priorityBadge(w.priority)} />
                      <StatusBadge {...workOrderStatusBadge(w.status)} />
                    </div>
                  </div>
                  <p className="ac-text-sm ac-text-muted" style={{ margin: "4px 0 0" }}>{w.title} · Due {w.dueDate}</p>
                </Link>
              ))}
            </div>
          </div>
        </div>
      </section>

      {awaitingReviewWOs.length > 0 && (
        <section className="ac-section">
          <div className="ac-card" style={{ borderColor: "var(--ac-status-insufficient)", background: "rgba(154,107,255,0.06)" }}>
            <p className="ac-eyebrow" style={{ color: "var(--ac-status-insufficient)", marginBottom: 6 }}>AI Maintenance Insight — Prototype</p>
            <p style={{ margin: 0, fontSize: 13, fontWeight: 600 }}>
              {projects[0]?.title ?? "The active check"} is currently 8% behind the planned schedule.
            </p>
            <p className="ac-text-sm ac-text-secondary" style={{ margin: "6px 0" }}>Potential contributors:</p>
            <ul style={{ margin: "0 0 8px", paddingLeft: 18, fontSize: 13 }}>
              {overdueWOs.length > 0 && <li>{overdueWOs.length} overdue task{overdueWOs.length > 1 ? "s" : ""}</li>}
              {awaitingPartsWOs.length > 0 && <li>{awaitingPartsWOs.length} part{awaitingPartsWOs.length > 1 ? "s" : ""} awaiting receipt</li>}
              <li>{awaitingReviewWOs.length} compliance/task review pending</li>
            </ul>
            <p className="ac-text-sm" style={{ margin: 0 }}>
              Recommended action: Prioritize <Link href={`/maintenance/work-orders/${awaitingReviewWOs[0].id}`} className="ac-mono">{awaitingReviewWOs[0].workOrderNumber}</Link> and the pending compliance review.
            </p>
          </div>
        </section>
      )}

      <section className="ac-section">
        <div className="ac-section-header">
          <h2 className="ac-h2">Fleet Compliance Overview</h2>
          <span className="ac-text-sm ac-text-muted">128 aircraft (demo scenario)</span>
        </div>
        <div className="ac-card">
          <div className="ac-flex" style={{ height: 10, borderRadius: 6, overflow: "hidden", marginBottom: 14 }}>
            {DISTRIBUTION.map((d) => (
              <div key={d.label} style={{ width: `${d.pct}%`, background: d.color }} title={`${d.label}: ${d.pct}%`} />
            ))}
          </div>
          <div className="ac-flex ac-gap-6" style={{ flexWrap: "wrap" }}>
            {DISTRIBUTION.map((d) => (
              <div key={d.label} className="ac-flex ac-items-center ac-gap-2 ac-text-sm">
                <span aria-hidden="true" style={{ width: 8, height: 8, borderRadius: "50%", background: d.color, display: "inline-block" }} />
                <span>{d.label}</span>
                <span className="ac-text-muted">{d.pct}%</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="ac-section">
        <div className="ac-section-header">
          <h2 className="ac-h2">Recent Assessments</h2>
          <Link href="/assessments" className="ac-text-sm">
            View all →
          </Link>
        </div>
        <div className="ac-card" style={{ padding: 0 }}>
          <table className="ac-table">
            <thead>
              <tr>
                <th>Requirement</th>
                <th>Aircraft</th>
                <th>Registration</th>
                <th>Assessment Date</th>
                <th>System Result</th>
                <th>Human Decision</th>
                <th>Evidence</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {recent.map((a) => {
                const aircraft = a.subjectType === "AIRCRAFT" ? getAircraftById(a.subjectId) : undefined;
                const requirement = getRequirementById(a.regulatoryRequirementId);
                const variant = aircraft ? getAircraftVariant(aircraft.aircraftVariantId) : undefined;
                const evCount = evidenceForAssessment(a.id).length;
                return (
                  <tr key={a.id}>
                    <td>
                      <Link href={`/regulations/${requirement?.id}`} className="ac-mono">
                        {requirement?.requirementNumber}
                      </Link>
                    </td>
                    <td>{variant?.modelDesignation ?? "—"}</td>
                    <td>
                      <Link href={`/aircraft/${aircraft?.id}`} className="ac-mono">
                        {aircraft ? currentRegistration(aircraft) : a.subjectId}
                      </Link>
                    </td>
                    <td>{new Date(a.evaluatedAt).toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" })}</td>
                    <td>
                      <StatusBadge status={a.systemResult} />
                    </td>
                    <td className="ac-text-sm">{a.humanDecision.replace(/_/g, " ")}</td>
                    <td className="ac-text-sm">
                      {evCount} Evidence
                    </td>
                    <td>
                      <Link href={`/assessments/${a.id}`}>
                        <StatusBadge status={a.finalStatus} />
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <div className="ac-grid-2 ac-section">
        <section>
          <div className="ac-section-header">
            <h2 className="ac-h2">Upcoming AD/SB Deadlines</h2>
            <Link href="/audit" className="ac-text-sm">View all →</Link>
          </div>
          <div className="ac-card" style={{ padding: 0 }}>
            <table className="ac-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Aircraft</th>
                  <th>Event</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {upcoming.length === 0 && (
                  <tr><td colSpan={4} className="ac-text-sm ac-text-muted" style={{ textAlign: "center", padding: 16 }}>No scheduled items.</td></tr>
                )}
                {upcoming.map((m) => {
                  const ac = getAircraftById(m.aircraftId);
                  return (
                    <tr key={m.id}>
                      <td className="ac-mono ac-text-sm">{m.date}</td>
                      <td>
                        <Link href={`/aircraft/${m.aircraftId}`} className="ac-mono">{ac ? currentRegistration(ac) : m.aircraftId}</Link>
                      </td>
                      <td className="ac-text-sm">{m.description}</td>
                      <td><StatusBadge status="PENDING" label="Scheduled" /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>

        <section>
          <div className="ac-section-header">
            <h2 className="ac-h2">Overdue Compliance Items</h2>
            <Link href="/audit" className="ac-text-sm">View all →</Link>
          </div>
          <div className="ac-card" style={{ padding: 0 }}>
            <table className="ac-table">
              <thead>
                <tr>
                  <th>Due</th>
                  <th>Aircraft</th>
                  <th>Event</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {overdue.length === 0 && (
                  <tr><td colSpan={4} className="ac-text-sm ac-text-muted" style={{ textAlign: "center", padding: 16 }}>Nothing overdue.</td></tr>
                )}
                {overdue.map((m) => {
                  const ac = getAircraftById(m.aircraftId);
                  return (
                    <tr key={m.id}>
                      <td className="ac-mono ac-text-sm">{m.date}</td>
                      <td>
                        <Link href={`/aircraft/${m.aircraftId}`} className="ac-mono">{ac ? currentRegistration(ac) : m.aircraftId}</Link>
                      </td>
                      <td className="ac-text-sm">{m.description}</td>
                      <td><StatusBadge status="NON_COMPLIANT" label="Overdue" /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <section className="ac-section">
        <div className="ac-section-header">
          <h2 className="ac-h2">Open Review Decisions</h2>
          <Link href="/assessments" className="ac-text-sm">View all →</Link>
        </div>
        <div className="ac-card" style={{ padding: 0 }}>
          <table className="ac-table">
            <thead>
              <tr>
                <th>Requirement</th>
                <th>Aircraft</th>
                <th>System Result</th>
                <th>Human Decision</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {openReviews.length === 0 && (
                <tr><td colSpan={5} className="ac-text-sm ac-text-muted" style={{ textAlign: "center", padding: 16 }}>No open review decisions.</td></tr>
              )}
              {openReviews.map((a) => {
                const aircraft = a.subjectType === "AIRCRAFT" ? getAircraftById(a.subjectId) : undefined;
                const requirement = getRequirementById(a.regulatoryRequirementId);
                return (
                  <tr key={a.id}>
                    <td className="ac-mono">{requirement?.requirementNumber}</td>
                    <td>
                      <Link href={`/aircraft/${aircraft?.id ?? ""}`} className="ac-mono">{aircraft ? currentRegistration(aircraft) : a.subjectId}</Link>
                    </td>
                    <td><StatusBadge status={a.systemResult} /></td>
                    <td className="ac-text-sm">{a.humanDecision.replace(/_/g, " ")}</td>
                    <td>
                      <Link href={`/assessments/${a.id}/review`} className="ac-btn">Review</Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 12 }}>
          Attention Required
        </h2>
        <div className="ac-card">
          <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
            {ATTENTION_ITEMS.map((item) => (
              <li key={item.text} style={{ padding: "8px 0", borderBottom: "1px solid var(--ac-border-subtle)" }}>
                <Link href={item.href} className="ac-flex ac-items-center ac-gap-2" style={{ fontSize: 13 }}>
                  <span aria-hidden="true" style={{ color: "var(--ac-status-review)" }}>
                    ⚠
                  </span>
                  {item.text}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      </section>
    </div>
  );
}

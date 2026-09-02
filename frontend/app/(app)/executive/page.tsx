import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { Timeline } from "@/components/timeline/Timeline";
import { getFleetAnalytics, getMaintenanceAnalytics, getComplianceAnalytics, getInspectionAnalytics, getTechnicianWorkload, getPartsAtRisk, getAircraftAnalytics, requirementLabel, getControlTowerSummary, getMaintenanceControlCenterSummary, getReleaseQueue, getAutomationQueue, getQuarantinedParts } from "@/lib/mock/ai/analytics";
import { upcomingMaintenanceEvents } from "@/lib/mock/maintenance";
import { getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
import { getRequirementById } from "@/lib/mock/regulations";
import { workOrders, workOrdersForAircraft, isOverdue } from "@/lib/mock/workOrders";
import { defects, defectsForAircraft } from "@/lib/mock/defects";
import { assessmentsForAircraft } from "@/lib/mock/assessments";
import { auditEvents } from "@/lib/mock/audit";
import { PLATFORM_AI_NAME } from "@/lib/brand";

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
  // M12.7.1/M12.8 — the Control Tower and Control Center now exist and give
  // this page a real answer for what used to be hardcoded "Insufficient
  // source data." (AOG Exposure had no derivation before M12.1). Reusing
  // the same summary functions those pages render — never a second
  // AOG/risk calculation.
  const towerSummary = getControlTowerSummary();
  const controlCenterSummary = getMaintenanceControlCenterSummary();
  const regulatoryDeadlines = upcomingMaintenanceEvents(8).filter((e) => e.relatedRequirementId);
  const rankedAircraft = [...fleet.aircraftAtRisk].sort((a, b) => (a.risk === b.risk ? 0 : a.risk === "HIGH" ? -1 : 1));
  const recentAudit = auditEvents.slice(0, 8);

  const bottlenecks = [
    { stage: "Waiting on Parts", count: maintenance.waitingParts, href: "/maintenance/parts" },
    { stage: "Waiting Inspection", count: maintenance.waitingInspection, href: "/maintenance/inspections" },
    { stage: "Overdue", count: maintenance.overdue.length, href: "/maintenance/work-orders" },
  ].sort((a, b) => b.count - a.count);
  const primaryBottleneck = bottlenecks.find((b) => b.count > 0);

  // M8.12 — commercially meaningful MRO KPIs, computed only where real
  // source data supports them. Never a fabricated financial figure — cost/
  // downtime data doesn't exist in this model, so those are explicit
  // "Insufficient source data." rather than an invented number.
  const repeatDefectGroups = new Map<string, number>();
  for (const d of defects) {
    const key = `${d.aircraftId}::${d.ataChapter}`;
    repeatDefectGroups.set(key, (repeatDefectGroups.get(key) ?? 0) + 1);
  }
  const repeatDefectCount = Array.from(repeatDefectGroups.values()).filter((n) => n > 1).length;
  const mroKpis: { label: string; value: string; href: string }[] = [
    { label: "Overdue Work Orders", value: String(maintenance.overdue.length), href: "/maintenance/work-orders" },
    { label: "Blocked (Waiting Parts/Inspection)", value: String(maintenance.waitingParts + maintenance.waitingInspection), href: "/maintenance/operations" },
    { label: "Parts Delays", value: String(partsAtRisk.length), href: "/maintenance/parts" },
    { label: "Inspection Backlog", value: String(inspection.pending.length), href: "/maintenance/inspections" },
    { label: "Compliance Exposure", value: String(compliance.nonCompliant + compliance.reviewRequired), href: "/compliance" },
    { label: "Evidence Gaps (Assessments)", value: String(compliance.insufficientData), href: "/compliance" },
    { label: "Repeat Defects (same aircraft/ATA chapter)", value: String(repeatDefectCount), href: "/maintenance/defects" },
    { label: "AOG Exposure", value: String(towerSummary.aog), href: "/maintenance/control-tower" },
    { label: "Aircraft Availability", value: `${towerSummary.operational}/${towerSummary.totalAircraft} operational`, href: "/maintenance/control-tower" },
    { label: "Critical Work Orders", value: String(controlCenterSummary.criticalWorkOrders), href: "/maintenance/control-center" },
    { label: "Material Blockers", value: String(controlCenterSummary.materialShortages), href: "/maintenance/material-readiness" },
    // M14.12 — operational intelligence: reuses the M14.1/M13/M14.2
    // functions, never a second calculation.
    { label: "Release Queue", value: String(getReleaseQueue().length), href: "/maintenance/planning" },
    { label: "Automation Queue", value: String(getAutomationQueue().length), href: "/automation" },
    { label: "Quarantined Parts", value: String(getQuarantinedParts().length), href: "/maintenance/parts" },
  ];

  const riskSummaryPoints: string[] = [];
  if (fleet.aircraftAtRisk.length > 0) riskSummaryPoints.push(`${fleet.aircraftAtRisk.length} of ${fleet.fleetSize} aircraft show elevated risk.`);
  if (maintenance.overdue.length > 0) riskSummaryPoints.push(`${maintenance.overdue.length} work order(s) are overdue.`);
  if (compliance.nonCompliant + compliance.reviewRequired > 0) riskSummaryPoints.push(`${compliance.nonCompliant + compliance.reviewRequired} assessment(s) need human review.`);
  if (partsAtRisk.length > 0) riskSummaryPoints.push(`${partsAtRisk.length} part(s) are at risk.`);
  if (riskSummaryPoints.length === 0) riskSummaryPoints.push("No significant fleet, maintenance, or compliance risk currently identified.");

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Executive Control Center" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Executive Operations Control Center</h1>
          <p className="ac-subtitle">Fleet-wide compliance and maintenance cockpit — every value is derived from current demo data.</p>
        </div>
        <div className="ac-flex ac-gap-2">
          <Link href="/ai" className="ac-btn ac-btn-primary" style={{ fontSize: 12, padding: "4px 10px" }}>Ask {PLATFORM_AI_NAME}</Link>
          <Link href="/reports/fleet-risk" className="ac-btn" style={{ fontSize: 12, padding: "4px 10px" }}>Generate Executive Report</Link>
          <Link href="/reports/maintenance-operations" className="ac-btn" style={{ fontSize: 12, padding: "4px 10px" }}>Generate Operations Report</Link>
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

      <section className="ac-section">
        <div className="ac-card" style={{ borderColor: "var(--ac-status-insufficient)", background: "rgba(154,107,255,0.06)" }}>
          <p className="ac-eyebrow" style={{ color: "var(--ac-status-insufficient)", marginBottom: 6 }}>Executive Risk Summary — Prototype</p>
          <ul style={{ margin: "0 0 8px", paddingLeft: 18, fontSize: 13 }}>
            {riskSummaryPoints.map((p, idx) => <li key={idx}>{p}</li>)}
          </ul>
          {primaryBottleneck && (
            <p className="ac-text-sm" style={{ margin: 0 }}>
              Primary operational bottleneck: <Link href={primaryBottleneck.href} className="ac-mono">{primaryBottleneck.stage}</Link> ({primaryBottleneck.count})
            </p>
          )}
        </div>
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>MRO KPI Summary</h2>
        <div className="ac-kpi-grid">
          {mroKpis.map((k) => (
            <Link key={k.label} href={k.href} className="ac-kpi-card" style={{ display: "block" }}>
              <p className="ac-kpi-label">{k.label}</p>
              <p className="ac-kpi-value" style={{ fontSize: k.value === "Insufficient source data." ? 13 : undefined }}>{k.value}</p>
            </Link>
          ))}
        </div>
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Operational Bottlenecks</h2>
        <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
          {bottlenecks.map((b) => (
            <Link key={b.stage} href={b.href} className="ac-card" style={{ display: "block", minWidth: 160 }}>
              <p className="ac-kpi-label">{b.stage}</p>
              <p className="ac-kpi-value">{b.count}</p>
            </Link>
          ))}
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
                <thead><tr><th>Aircraft</th><th>Risk</th><th>Why?</th></tr></thead>
                <tbody>
                  {rankedAircraft.map((a) => {
                    // M7.8 — Executive Traceability: no black-box risk score.
                    // Every risk is backed by the same explainable reasons
                    // computed in getAircraftAnalytics, drilled down to the
                    // real work orders/defects/assessments behind them.
                    const detail = getAircraftAnalytics(a.aircraftId);
                    const overdueWos = workOrdersForAircraft(a.aircraftId).filter((w) => isOverdue(w));
                    const seriousDefects = defectsForAircraft(a.aircraftId).filter((d) => d.status === "OPEN" && (d.severity === "HIGH" || d.severity === "CRITICAL"));
                    const reviewAssessments = assessmentsForAircraft(a.aircraftId).filter((asmt) => asmt.finalStatus === "REVIEW_REQUIRED" || asmt.finalStatus === "NON_COMPLIANT");
                    return (
                      <tr key={a.aircraftId}>
                        <td><Link href={`/fleet/aircraft/${a.aircraftId}/health`} className="ac-mono">{a.registration}</Link></td>
                        <td><StatusBadge status={a.risk === "HIGH" ? "NON_COMPLIANT" : "REVIEW_REQUIRED"} label={a.risk} /></td>
                        <td>
                          <details>
                            <summary className="ac-text-sm" style={{ cursor: "pointer" }}>Reason</summary>
                            <div className="ac-text-sm ac-text-muted" style={{ marginTop: 6 }}>
                              {detail ? (
                                <ul style={{ margin: 0, paddingLeft: 16 }}>
                                  {detail.reasons.map((r, i) => <li key={i}>{r}</li>)}
                                </ul>
                              ) : "Insufficient source data."}
                              {overdueWos.length > 0 && (
                                <p style={{ margin: "4px 0 0" }}>
                                  Work Orders: {overdueWos.map((w, i) => <span key={w.id}>{i > 0 && ", "}<Link href={`/maintenance/work-orders/${w.id}`} className="ac-mono">{w.workOrderNumber}</Link></span>)}
                                </p>
                              )}
                              {seriousDefects.length > 0 && (
                                <p style={{ margin: "4px 0 0" }}>Defects: {seriousDefects.map((d) => d.id).join(", ")}</p>
                              )}
                              {reviewAssessments.length > 0 && (
                                <p style={{ margin: "4px 0 0" }}>
                                  Regulation: {reviewAssessments.map((asmt, i) => <span key={asmt.id}>{i > 0 && ", "}<Link href={`/assessments/${asmt.id}`} className="ac-mono">{requirementLabel(asmt.regulatoryRequirementId)}</Link></span>)}
                                </p>
                              )}
                            </div>
                          </details>
                        </td>
                      </tr>
                    );
                  })}
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

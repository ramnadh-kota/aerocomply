import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { getComplianceAnalytics, getInspectionAnalytics } from "@/lib/mock/ai/analytics";
import { aircraft, getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
import { assessmentsForAircraft, assessmentsForRequirement } from "@/lib/mock/assessments";
import { getRequirementById, regulatoryRequirements } from "@/lib/mock/regulations";
import { upcomingMaintenanceEvents } from "@/lib/mock/maintenance";
import { evidenceForAssessment } from "@/lib/mock/evidence";
import { defectsForAircraft } from "@/lib/mock/defects";
import { parts } from "@/lib/mock/parts";

export default function CompliancePage() {
  const analytics = getComplianceAnalytics();

  const allAssessments = aircraft.flatMap((a) => assessmentsForAircraft(a.id));
  const openGaps = allAssessments
    .filter((asmt) => asmt.finalStatus === "NON_COMPLIANT" || asmt.finalStatus === "REVIEW_REQUIRED" || asmt.finalStatus === "INSUFFICIENT_DATA")
    .sort((a, b) => b.evaluatedAt.localeCompare(a.evaluatedAt));

  const upcomingDeadlines = upcomingMaintenanceEvents(8).filter((e) => e.relatedRequirementId);

  const withEvidence = allAssessments.filter((a) => evidenceForAssessment(a.id).length > 0).length;
  const evidenceCompletenessPercent = allAssessments.length > 0 ? Math.round((withEvidence / allAssessments.length) * 100) : null;

  const riskByAircraft = aircraft
    .map((a) => {
      const asmts = assessmentsForAircraft(a.id);
      const gaps = asmts.filter((asmt) => asmt.finalStatus === "NON_COMPLIANT" || asmt.finalStatus === "REVIEW_REQUIRED").length;
      const openDefects = defectsForAircraft(a.id).filter((d) => d.status === "OPEN").length;
      return { aircraftId: a.id, registration: currentRegistration(a), gaps, openDefects, score: gaps + openDefects };
    })
    .filter((r) => r.score > 0)
    .sort((a, b) => b.score - a.score);

  // M4.5 — Audit Readiness Score: an explainable average of real, existing
  // drivers. Never a black-box number — every driver is shown alongside it.
  const inspectionAnalytics = getInspectionAnalytics();
  const inspectionTotal = inspectionAnalytics.approved + inspectionAnalytics.rejected + inspectionAnalytics.returned + inspectionAnalytics.pending.length;
  const requiredInspectionsPercent = inspectionTotal > 0 ? Math.round((inspectionAnalytics.approved / inspectionTotal) * 100) : null;

  const partsTraceablePercent = parts.length > 0 ? Math.round((parts.filter((p) => p.status === "IN_STOCK").length / parts.length) * 100) : null;

  const mappedRequirements = regulatoryRequirements.filter((r) => assessmentsForRequirement(r.id).length > 0).length;
  const regulatoryMappingPercent = regulatoryRequirements.length > 0 ? Math.round((mappedRequirements / regulatoryRequirements.length) * 100) : null;

  const readinessDrivers = [
    { label: "Evidence completeness", value: evidenceCompletenessPercent },
    { label: "Required inspections approved", value: requiredInspectionsPercent },
    { label: "Parts traceability (in stock)", value: partsTraceablePercent },
    { label: "Regulatory mapping", value: regulatoryMappingPercent },
  ];
  const knownDrivers = readinessDrivers.filter((d) => d.value !== null) as { label: string; value: number }[];
  const readinessScore = knownDrivers.length > 0 ? Math.round(knownDrivers.reduce((s, d) => s + d.value, 0) / knownDrivers.length) : null;
  const criticalDataMissing = readinessDrivers.some((d) => d.value === null);
  const unknownRecordsCount = openGaps.filter((a) => a.finalStatus === "INSUFFICIENT_DATA").length;

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Compliance" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Compliance Intelligence</h1>
          <p className="ac-subtitle">Fleet-wide compliance workspace — every value is derived from current demo data.</p>
        </div>
        <div className="ac-flex ac-gap-2">
          <Link href="/regulations" className="ac-btn" style={{ fontSize: 12, padding: "4px 10px" }}>Regulations</Link>
          <Link href="/assessments" className="ac-btn" style={{ fontSize: 12, padding: "4px 10px" }}>Assessments</Link>
          <Link href="/ai" className="ac-btn" style={{ fontSize: 12, padding: "4px 10px" }}>Ask AI</Link>
          <Link href="/reports/compliance-weekly" className="ac-btn" style={{ fontSize: 12, padding: "4px 10px" }}>Generate Report</Link>
          <Link href="/compliance/pre-audit" className="ac-btn" style={{ fontSize: 12, padding: "4px 10px" }}>Pre-Audit Dossier →</Link>
          <Link href="/compliance/regulatory-register" className="ac-btn" style={{ fontSize: 12, padding: "4px 10px" }}>Regulatory Register →</Link>
        </div>
      </div>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Compliance Health</h2>
        <div className="ac-kpi-grid">
          {analytics.kpis.map((k) => (
            <div key={k.label} className="ac-kpi-card">
              <p className="ac-kpi-label">{k.label}</p>
              <p className="ac-kpi-value">{k.value}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Compliance Distribution</h2>
        <div className="ac-card">
          <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
            <Link href="/assessments"><StatusBadge status="COMPLIANT" label={`Compliant: ${analytics.compliant}`} /></Link>
            <Link href="/assessments"><StatusBadge status="NON_COMPLIANT" label={`Non-Compliant: ${analytics.nonCompliant}`} /></Link>
            <Link href="/assessments"><StatusBadge status="REVIEW_REQUIRED" label={`Review Required: ${analytics.reviewRequired}`} /></Link>
            <Link href="/assessments"><StatusBadge status="INSUFFICIENT_DATA" label={`Unknown: ${analytics.insufficientData}`} /></Link>
          </div>
          <p className="ac-text-sm ac-text-muted" style={{ marginTop: 8 }}>
            &ldquo;Unknown&rdquo; (Insufficient Data) is a distinct outcome — it is never treated as compliant or non-compliant.
          </p>
        </div>
      </section>

      <div className="ac-grid-2 ac-section">
        <section>
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Open Gaps — Human Review Needed</h2>
          <div className="ac-card" style={{ padding: 0 }}>
            {openGaps.length === 0 ? (
              <p className="ac-text-sm ac-text-muted" style={{ padding: 12 }}>Insufficient source data.</p>
            ) : (
              <table className="ac-table">
                <thead><tr><th>Requirement</th><th>Aircraft</th><th>Status</th></tr></thead>
                <tbody>
                  {openGaps.slice(0, 10).map((asmt) => {
                    const req = getRequirementById(asmt.regulatoryRequirementId);
                    const ac = asmt.subjectType === "AIRCRAFT" ? getAircraftById(asmt.subjectId) : undefined;
                    return (
                      <tr key={asmt.id}>
                        <td>{req ? <Link href={`/regulations/${req.id}`} className="ac-mono">{req.requirementNumber}</Link> : "—"}</td>
                        <td>{ac ? <Link href={`/aircraft/${ac.id}`} className="ac-mono">{currentRegistration(ac)}</Link> : asmt.subjectId}</td>
                        <td><Link href={`/assessments/${asmt.id}`}><StatusBadge status={asmt.finalStatus} /></Link></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        </section>

        <section>
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Upcoming Regulatory Deadlines</h2>
          <div className="ac-card" style={{ padding: 0 }}>
            {upcomingDeadlines.length === 0 ? (
              <p className="ac-text-sm ac-text-muted" style={{ padding: 12 }}>Insufficient source data.</p>
            ) : (
              <table className="ac-table">
                <thead><tr><th>Date</th><th>Aircraft</th><th>Requirement</th></tr></thead>
                <tbody>
                  {upcomingDeadlines.map((e) => {
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
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Audit Readiness Score</h2>
        <div className="ac-card">
          {readinessScore === null ? (
            <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Readiness cannot be fully determined — Insufficient source data.</p>
          ) : (
            <>
              <div className="ac-flex ac-items-center ac-gap-3" style={{ marginBottom: 10 }}>
                <p className="ac-kpi-value" style={{ fontSize: 32, margin: 0 }}>{readinessScore}%</p>
                <StatusBadge status={readinessScore >= 90 ? "COMPLIANT" : readinessScore >= 70 ? "REVIEW_REQUIRED" : "NON_COMPLIANT"} label="Audit Readiness" />
              </div>
              <p className="ac-text-sm ac-text-secondary" style={{ marginBottom: 8 }}>Drivers:</p>
              <ul style={{ margin: "0 0 8px", paddingLeft: 18, fontSize: 13 }}>
                {readinessDrivers.map((d) => (
                  <li key={d.label}>{d.label}: {d.value === null ? "Insufficient source data." : `${d.value}%`}</li>
                ))}
                <li>Open findings: {openGaps.length}</li>
                <li>UNKNOWN records: {unknownRecordsCount}</li>
              </ul>
              {criticalDataMissing && (
                <p className="ac-text-sm" style={{ color: "var(--ac-status-review)", margin: 0 }}>
                  One or more drivers could not be computed from current source data — this score should be treated as partial, not complete.
                </p>
              )}
            </>
          )}
        </div>
      </section>

      <div className="ac-grid-2 ac-section">
        <section>
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Evidence Completeness</h2>
          <div className="ac-card">
            {evidenceCompletenessPercent === null ? (
              <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Insufficient source data.</p>
            ) : (
              <>
                <div className="ac-flex ac-items-center ac-gap-2" style={{ marginBottom: 6 }}>
                  <div style={{ width: 120, height: 6, borderRadius: 4, background: "var(--ac-border)", overflow: "hidden" }}>
                    <div style={{ width: `${evidenceCompletenessPercent}%`, height: "100%", background: "var(--ac-accent)" }} />
                  </div>
                  <span className="ac-text-sm ac-text-muted">{evidenceCompletenessPercent}%</span>
                </div>
                <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>{withEvidence} of {allAssessments.length} assessments have at least one linked evidence record.</p>
              </>
            )}
          </div>
        </section>

        <section>
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Risk Concentration by Aircraft</h2>
          <div className="ac-card" style={{ padding: 0 }}>
            {riskByAircraft.length === 0 ? (
              <p className="ac-text-sm ac-text-muted" style={{ padding: 12 }}>Insufficient source data.</p>
            ) : (
              <table className="ac-table">
                <thead><tr><th>Aircraft</th><th>Compliance Gaps</th><th>Open Defects</th></tr></thead>
                <tbody>
                  {riskByAircraft.map((r) => (
                    <tr key={r.aircraftId}>
                      <td><Link href={`/fleet/aircraft/${r.aircraftId}/health`} className="ac-mono">{r.registration}</Link></td>
                      <td>{r.gaps}</td>
                      <td>{r.openDefects}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>
      </div>

      <section className="ac-section">
        <div className="ac-card">
          <p className="ac-eyebrow" style={{ marginBottom: 6 }}>Traceability</p>
          <p className="ac-text-sm ac-text-secondary" style={{ margin: 0 }}>
            Every requirement flows Requirement → Assessment → Aircraft → Evidence → Human Review → Audit Trail. Open the{" "}
            <Link href="/audit" className="ac-mono">Audit Trail</Link> for the full chronological record.
          </p>
        </div>
      </section>
    </div>
  );
}

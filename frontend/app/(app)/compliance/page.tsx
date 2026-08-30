import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { getComplianceAnalytics } from "@/lib/mock/ai/analytics";
import { aircraft, getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
import { assessmentsForAircraft } from "@/lib/mock/assessments";
import { getRequirementById } from "@/lib/mock/regulations";
import { upcomingMaintenanceEvents } from "@/lib/mock/maintenance";
import { evidenceForAssessment } from "@/lib/mock/evidence";
import { defectsForAircraft } from "@/lib/mock/defects";

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

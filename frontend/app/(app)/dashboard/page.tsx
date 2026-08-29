import Link from "next/link";
import { StatusBadge } from "@/components/status/StatusBadge";
import { CoreLoopDiagram } from "@/components/core-loop/CoreLoopDiagram";
import { assessments } from "@/lib/mock/assessments";
import { getAircraftById, currentRegistration, getAircraftVariant } from "@/lib/mock/aircraft";
import { getRequirementById } from "@/lib/mock/regulations";
import { evidenceForAssessment } from "@/lib/mock/evidence";

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

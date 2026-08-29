"use client";

import Link from "next/link";
import { notFound } from "next/navigation";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { WhyPanel } from "@/components/assessments/WhyPanel";
import { ConditionTree } from "@/components/rule-tree/ConditionTree";
import { EvidenceCard } from "@/components/evidence/EvidenceCard";
import { Timeline } from "@/components/timeline/Timeline";
import { getAssessmentById, lineageFor } from "@/lib/mock/assessments";
import { getRequirementById, getRuleForRequirement } from "@/lib/mock/regulations";
import { getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
import { getEngineById } from "@/lib/mock/engines";
import { evidenceForAssessment } from "@/lib/mock/evidence";
import { evaluateTree } from "@/lib/mock/kleene";

export default function AssessmentDetailPage({ params }: { params: { id: string } }) {
  const assessment = getAssessmentById(params.id);
  if (!assessment) notFound();

  const requirement = getRequirementById(assessment.regulatoryRequirementId)!;
  const rule = getRuleForRequirement(requirement.id);
  const subjectLabel =
    assessment.subjectType === "AIRCRAFT"
      ? (() => {
          const a = getAircraftById(assessment.subjectId);
          return a ? currentRegistration(a) : assessment.subjectId;
        })()
      : getEngineById(assessment.subjectId)?.serialNumber ?? assessment.subjectId;
  const subjectHref = assessment.subjectType === "AIRCRAFT" ? `/aircraft/${assessment.subjectId}` : `/engines/${assessment.subjectId}`;

  const leafResults = Object.fromEntries(assessment.conditionEvaluations.map((e) => [e.conditionId, e.result]));
  const treeResults = rule ? evaluateTree(rule.rootCondition, leafResults) : undefined;

  const evidence = evidenceForAssessment(assessment.id);
  const lineage = lineageFor(assessment.id);

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Assessments", href: "/assessments" }, { label: assessment.id }]} />

      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1 ac-mono">{assessment.id}</h1>
          <p className="ac-subtitle">
            <Link href={`/regulations/${requirement.id}`} className="ac-mono">{requirement.requirementNumber}</Link> ·{" "}
            <Link href={subjectHref} className="ac-mono">{subjectLabel}</Link>
          </p>
        </div>
        <div className="ac-flex ac-gap-2">
          <StatusBadge status={assessment.systemResult} />
          <Link href={`/assessments/${assessment.id}/review`} className="ac-btn ac-btn-primary">
            Open Human Review
          </Link>
        </div>
      </div>

      <div className="ac-grid-3 ac-section">
        <div className="ac-card">
          <p className="ac-kpi-label">Assessment Date</p>
          <p style={{ fontWeight: 600, marginTop: 4 }}>{new Date(assessment.evaluatedAt).toLocaleDateString()}</p>
        </div>
        <div className="ac-card">
          <p className="ac-kpi-label">As-of Timestamp</p>
          <p style={{ fontWeight: 600, marginTop: 4 }} className="ac-mono">{new Date(assessment.evaluatedAt).toISOString().replace("T", " ").slice(0, 19)} UTC</p>
        </div>
        <div className="ac-card">
          <p className="ac-kpi-label">Data Version</p>
          <p style={{ fontWeight: 600, marginTop: 4 }} className="ac-mono">{assessment.configurationSnapshot.dataVersion}</p>
        </div>
      </div>

      {rule && (
        <section className="ac-section">
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Applicability Decision</h2>
          <div className="ac-card">
            <ConditionTree node={rule.rootCondition} results={treeResults} />
            <hr className="ac-divider" />
            <div className="ac-flex ac-items-center ac-gap-3">
              <span className="ac-text-sm ac-text-muted">Result:</span>
              <StatusBadge status={assessment.systemResult} />
              {assessment.systemResult === "INSUFFICIENT_DATA" || assessment.systemResult === "REVIEW_REQUIRED" ? (
                <span className="ac-text-sm" style={{ color: "var(--ac-status-insufficient)" }}>
                  Unknown is not false — see explanation below.
                </span>
              ) : null}
            </div>
          </div>
        </section>
      )}

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Why?</h2>
        <div className="ac-card">
          <WhyPanel evaluations={assessment.conditionEvaluations} />
        </div>
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Configuration Snapshot</h2>
        <div className="ac-card">
          <p className="ac-eyebrow" style={{ color: "var(--ac-status-insufficient)", marginBottom: 10 }}>
            Assessment Snapshot — Non-Authoritative Historical Record
          </p>
          <div className="ac-flex ac-flex-col ac-gap-2" style={{ fontSize: 13 }}>
            <div><span className="ac-text-muted">Aircraft: </span>{assessment.configurationSnapshot.aircraftVariant}</div>
            <div><span className="ac-text-muted">MSN: </span>{assessment.configurationSnapshot.msn}</div>
            <div><span className="ac-text-muted">Registration: </span>{assessment.configurationSnapshot.registration}</div>
            {assessment.configurationSnapshot.engines.map((e, idx) => (
              <div key={idx}><span className="ac-text-muted">{e.position.replace("_", " ")}: </span>{e.engineType} ({e.serialNumber})</div>
            ))}
            {assessment.configurationSnapshot.components.map((c, idx) => (
              <div key={idx}><span className="ac-text-muted">Component ({c.position}): </span>{c.partNumber}</div>
            ))}
          </div>
          <hr className="ac-divider" />
          <p className="ac-text-sm" style={{ margin: 0, color: "var(--ac-text-muted)" }}>
            This snapshot records the configuration evaluated for this assessment. It is not the
            authoritative current aircraft configuration — the interval-history tables (
            <span className="ac-mono">EngineInstallation</span>, <span className="ac-mono">ComponentInstallation</span>,{" "}
            <span className="ac-mono">RegistrationHistory</span>) remain the sole source of truth. See{" "}
            <Link href={`${subjectHref}/configuration`}>the live configuration timeline</Link> for the current record.
          </p>
        </div>
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Evidence</h2>
        {evidence.length === 0 && <p className="ac-text-sm ac-text-muted">No evidence linked to this assessment yet.</p>}
        <div className="ac-grid-2">
          {evidence.map((e) => (
            <EvidenceCard key={e.id} evidence={e} />
          ))}
        </div>
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Human Decision</h2>
        <div className="ac-card">
          {assessment.humanDecisionBy ? (
            <div className="ac-flex ac-flex-col ac-gap-1" style={{ fontSize: 13 }}>
              <div><span className="ac-text-muted">Decision: </span>{assessment.humanDecision.replace(/_/g, " ")}</div>
              <div><span className="ac-text-muted">Decision Maker: </span>{assessment.humanDecisionBy} ({assessment.humanDecisionByRole})</div>
              <div><span className="ac-text-muted">Timestamp: </span>{assessment.humanDecisionAt ? new Date(assessment.humanDecisionAt).toLocaleString() : "—"}</div>
              {assessment.overrideReason && <div><span className="ac-text-muted">Override Reason: </span>{assessment.overrideReason}</div>}
            </div>
          ) : (
            <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>No human decision recorded yet.</p>
          )}
          <p className="ac-text-sm" style={{ marginTop: 12, color: "var(--ac-text-muted)" }}>
            The rules engine produces the system result above. It does not make the final compliance
            decision — an authorized human does, via <Link href={`/assessments/${assessment.id}/review`}>Human Review</Link>.
          </p>
        </div>
      </section>

      {lineage.length > 1 && (
        <section className="ac-section">
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Assessment History</h2>
          <div className="ac-card">
            <Timeline
              entries={lineage.map((a) => ({
                id: a.id,
                date: new Date(a.evaluatedAt).toLocaleString(),
                title: (
                  <Link href={`/assessments/${a.id}`} className="ac-mono">
                    {a.id}
                  </Link>
                ),
                detail: (
                  <span className="ac-flex ac-items-center ac-gap-2">
                    System: <StatusBadge status={a.systemResult} /> Human: {a.humanDecision.replace(/_/g, " ")}
                    {a.id === assessment.id && <span className="ac-eyebrow" style={{ color: "var(--ac-accent-hover)" }}>(this assessment)</span>}
                  </span>
                ),
                accent: a.id === assessment.id ? "highlight" : "default",
              }))}
            />
            <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
              Every assessment above is immutable once created. A re-evaluation always creates a new
              row — historical results are never overwritten.
            </p>
          </div>
        </section>
      )}
    </div>
  );
}

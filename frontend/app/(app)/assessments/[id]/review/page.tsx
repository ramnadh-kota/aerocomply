"use client";

import { useState } from "react";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { WhyPanel } from "@/components/assessments/WhyPanel";
import { EvidenceCard } from "@/components/evidence/EvidenceCard";
import { getAssessmentById } from "@/lib/mock/assessments";
import { getRequirementById } from "@/lib/mock/regulations";
import { getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
import { evidenceForAssessment } from "@/lib/mock/evidence";

type DecisionOption = "CONFIRM_APPLICABLE" | "CONFIRM_NOT_APPLICABLE" | "REQUEST_MORE_EVIDENCE" | "OVERRIDE_WITH_JUSTIFICATION";

const OPTIONS: { value: DecisionOption; label: string }[] = [
  { value: "CONFIRM_APPLICABLE", label: "Confirm Applicable" },
  { value: "CONFIRM_NOT_APPLICABLE", label: "Confirm Not Applicable" },
  { value: "REQUEST_MORE_EVIDENCE", label: "Request More Evidence" },
  { value: "OVERRIDE_WITH_JUSTIFICATION", label: "Override With Justification" },
];

export default function AssessmentReviewPage({ params }: { params: { id: string } }) {
  const assessment = getAssessmentById(params.id);
  if (!assessment) notFound();

  const requirement = getRequirementById(assessment.regulatoryRequirementId)!;
  const aircraft = assessment.subjectType === "AIRCRAFT" ? getAircraftById(assessment.subjectId) : undefined;
  const evidence = evidenceForAssessment(assessment.id);

  const [decision, setDecision] = useState<DecisionOption | null>(null);
  const [comment, setComment] = useState("");
  const [submitted, setSubmitted] = useState<{ decision: DecisionOption; comment: string; at: string } | null>(null);

  const requiresJustification = decision === "OVERRIDE_WITH_JUSTIFICATION";
  const canSubmit = decision !== null && (!requiresJustification || comment.trim().length > 0);

  function handleSubmit() {
    if (!decision || !canSubmit) return;
    setSubmitted({ decision, comment, at: new Date().toISOString() });
  }

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Dashboard", href: "/dashboard" },
          { label: "Assessments", href: "/assessments" },
          { label: assessment.id, href: `/assessments/${assessment.id}` },
          { label: "Review" },
        ]}
      />

      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Human Review</h1>
          <p className="ac-subtitle">
            {requirement.requirementNumber} · {aircraft ? currentRegistration(aircraft) : assessment.subjectId}
          </p>
        </div>
      </div>

      <div className="ac-card" style={{ marginBottom: "var(--ac-space-4)", background: "var(--ac-accent-muted)", border: "1px solid var(--ac-accent)" }}>
        <p className="ac-text-sm" style={{ margin: 0 }}>
          The rules engine produced the result below. It does <strong>not</strong> make the final compliance
          decision — only an authorized human can, using this screen.
        </p>
      </div>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>System Result</h2>
        <div className="ac-card">
          <StatusBadge status={assessment.systemResult} />
        </div>
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>System Explanation</h2>
        <div className="ac-card">
          <WhyPanel evaluations={assessment.conditionEvaluations} />
        </div>
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Evidence</h2>
        <div className="ac-grid-2">
          {evidence.map((e) => (
            <EvidenceCard key={e.id} evidence={e} />
          ))}
        </div>
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Engineer Decision</h2>
        <div className="ac-card">
          {submitted ? (
            <div>
              <p style={{ fontWeight: 600, color: "var(--ac-status-compliant)" }}>
                ✓ Decision recorded: {OPTIONS.find((o) => o.value === submitted.decision)?.label}
              </p>
              {submitted.comment && <p className="ac-text-sm ac-text-secondary">&ldquo;{submitted.comment}&rdquo;</p>}
              <p className="ac-text-sm ac-text-muted">
                Priya Nair · Compliance Engineer · {new Date(submitted.at).toLocaleString()}
              </p>
              <p className="ac-text-sm ac-text-muted" style={{ marginTop: 10 }}>
                Prototype note: this decision is held in local component state only and is not
                persisted — the real M1 backend will insert an immutable, versioned assessment row
                per ADR-005.
              </p>
              <Link href={`/assessments/${assessment.id}`} className="ac-btn" style={{ marginTop: 10 }}>
                Back to Assessment
              </Link>
            </div>
          ) : (
            <div>
              <fieldset style={{ border: "none", padding: 0, margin: 0 }}>
                <legend className="ac-text-sm ac-text-secondary" style={{ marginBottom: 10 }}>
                  Choose a decision
                </legend>
                <div className="ac-flex ac-flex-col ac-gap-2">
                  {OPTIONS.map((opt) => (
                    <label key={opt.value} className="ac-flex ac-items-center ac-gap-2" style={{ fontSize: 13 }}>
                      <input type="radio" name="decision" value={opt.value} checked={decision === opt.value} onChange={() => setDecision(opt.value)} />
                      {opt.label}
                    </label>
                  ))}
                </div>
              </fieldset>

              <label className="ac-flex ac-flex-col ac-gap-2" style={{ marginTop: 16 }}>
                <span className="ac-text-sm ac-text-secondary">
                  Comment {requiresJustification && <span style={{ color: "var(--ac-status-non-compliant)" }}>(required for override)</span>}
                </span>
                <textarea
                  className="ac-input"
                  rows={3}
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  placeholder={requiresJustification ? "Explain why you are overriding the system result…" : "Optional comment…"}
                />
              </label>

              <button className="ac-btn ac-btn-primary" style={{ marginTop: 16 }} disabled={!canSubmit} onClick={handleSubmit}>
                Submit Decision
              </button>
              {requiresJustification && comment.trim().length === 0 && (
                <p className="ac-text-sm" style={{ color: "var(--ac-status-non-compliant)", marginTop: 8 }}>
                  A justification is required to override the system result.
                </p>
              )}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

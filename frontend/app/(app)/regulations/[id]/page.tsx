"use client";

import Link from "next/link";
import { notFound } from "next/navigation";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { ConditionTree } from "@/components/rule-tree/ConditionTree";
import { CoreLoopDiagram } from "@/components/core-loop/CoreLoopDiagram";
import { AIPlaceholder } from "@/components/ai/AIPlaceholder";
import { StatusBadge } from "@/components/status/StatusBadge";
import { getRequirementById, getDocumentById, getAuthorityById, getRuleForRequirement } from "@/lib/mock/regulations";
import { assessmentsForRequirement } from "@/lib/mock/assessments";
import { getAircraftById, currentRegistration } from "@/lib/mock/aircraft";

export default function RequirementDetailPage({ params }: { params: { id: string } }) {
  const requirement = getRequirementById(params.id);
  if (!requirement) notFound();

  const document = getDocumentById(requirement.regulatoryDocumentId)!;
  const authority = getAuthorityById(document.regulatoryAuthorityId)!;
  const rule = getRuleForRequirement(requirement.id);
  const assessed = assessmentsForRequirement(requirement.id);

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Regulations", href: "/regulations" }, { label: requirement.requirementNumber }]} />

      <div className="ac-card" style={{ marginBottom: "var(--ac-space-4)", borderColor: "var(--ac-status-review)", background: "rgba(232,163,61,0.06)" }}>
        <p className="ac-text-sm" style={{ margin: 0 }}>
          ⚠ Fictional demo record. Not a real, current, or legally binding requirement.
        </p>
      </div>

      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">{requirement.requirementNumber}</h1>
          <p className="ac-subtitle">&ldquo;{document.title}&rdquo;</p>
        </div>
        <StatusBadge status={document.sourceStatus === "PUBLISHED" ? "VERIFIED" : "PENDING"} label={document.sourceStatus} />
      </div>

      <div className="ac-grid-3 ac-section">
        <div className="ac-card">
          <p className="ac-kpi-label">Authority</p>
          <p style={{ fontWeight: 600, marginTop: 4 }}>{authority.code} — {authority.name}</p>
        </div>
        <div className="ac-card">
          <p className="ac-kpi-label">Revision</p>
          <p style={{ fontWeight: 600, marginTop: 4 }}>{document.revision}</p>
        </div>
        <div className="ac-card">
          <p className="ac-kpi-label">Effective</p>
          <p style={{ fontWeight: 600, marginTop: 4 }}>{document.effectiveDate}</p>
        </div>
      </div>

      <section className="ac-section">
        <div className="ac-card">
          <p className="ac-eyebrow" style={{ marginBottom: 10 }}>The AeroComply Loop for this Requirement</p>
          <CoreLoopDiagram compact />
        </div>
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Description</h2>
        <div className="ac-card">
          <p style={{ margin: 0, fontSize: 13, lineHeight: 1.7 }}>{requirement.description}</p>
          <p className="ac-text-sm ac-text-muted" style={{ marginTop: 10 }}>Compliance time: {requirement.complianceTime}</p>
        </div>
      </section>

      {rule && (
        <section className="ac-section">
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Applicability</h2>
          <div className="ac-card">
            <p className="ac-text-sm ac-text-muted" style={{ marginBottom: 12 }}>
              Structured, versioned interpretation ({rule.ruleVersion}) of the applicability paragraph above. Click a node to expand or collapse.
            </p>
            <ConditionTree node={rule.rootCondition} />
          </div>
        </section>
      )}

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Assessed Aircraft</h2>
        <div className="ac-card" style={{ padding: 0 }}>
          <table className="ac-table">
            <thead>
              <tr>
                <th>Aircraft</th>
                <th>System Result</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {assessed.length === 0 && (
                <tr>
                  <td colSpan={3} className="ac-text-sm ac-text-muted" style={{ textAlign: "center", padding: 20 }}>
                    No aircraft assessed against this requirement yet.
                  </td>
                </tr>
              )}
              {assessed.map((a) => {
                const aircraft = a.subjectType === "AIRCRAFT" ? getAircraftById(a.subjectId) : undefined;
                return (
                  <tr key={a.id}>
                    <td>
                      <Link href={`/aircraft/${aircraft?.id ?? ""}`} className="ac-mono">
                        {aircraft ? currentRegistration(aircraft) : a.subjectId}
                      </Link>
                    </td>
                    <td>
                      <StatusBadge status={a.systemResult} />
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
        <AIPlaceholder />
      </section>
    </div>
  );
}

"use client";

import { useState } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { regulatoryRequirements } from "@/lib/mock/regulations";
import { assessmentsForRequirement } from "@/lib/mock/assessments";
import { evidenceForAssessment } from "@/lib/mock/evidence";
import { getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
import type { RequirementType } from "@/lib/mock/types";

const TYPES: RequirementType[] = ["AD", "SB", "REGULATION", "RULE", "AMC", "GM", "SIB", "NOTICE", "OTHER"];

export default function RegulatoryRegisterPage() {
  const [typeFilter, setTypeFilter] = useState<string>("ALL");

  const rows = regulatoryRequirements
    .filter((r) => typeFilter === "ALL" || r.requirementType === typeFilter)
    .map((req) => {
      const assessments = assessmentsForRequirement(req.id);
      const latest = [...assessments].sort((a, b) => b.evaluatedAt.localeCompare(a.evaluatedAt))[0];
      const evidenceCount = latest ? evidenceForAssessment(latest.id).length : 0;
      const gap = !latest || latest.finalStatus === "NON_COMPLIANT" || latest.finalStatus === "REVIEW_REQUIRED" || latest.finalStatus === "INSUFFICIENT_DATA";
      return { req, assessments, latest, evidenceCount, gap };
    });

  const openGapCount = rows.filter((r) => r.gap).length;

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Compliance", href: "/compliance" }, { label: "Regulatory Register" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Regulatory Register — AD / SB &amp; Gap Packager</h1>
          <p className="ac-subtitle">{rows.length} requirement(s) shown · {openGapCount} with an open gap or UNKNOWN status. Applicability and status are never inferred from missing evidence.</p>
        </div>
      </div>

      <div className="ac-flex ac-gap-2 ac-section" style={{ flexWrap: "wrap" }}>
        <button className="ac-btn" style={typeFilter === "ALL" ? { borderColor: "var(--ac-accent)", color: "var(--ac-accent-hover)" } : undefined} onClick={() => setTypeFilter("ALL")}>All</button>
        {TYPES.map((t) => (
          <button key={t} className="ac-btn" style={typeFilter === t ? { borderColor: "var(--ac-accent)", color: "var(--ac-accent-hover)" } : undefined} onClick={() => setTypeFilter(t)}>{t}</button>
        ))}
      </div>

      <div className="ac-card" style={{ padding: 0 }}>
        <table className="ac-table">
          <thead>
            <tr>
              <th>Requirement</th>
              <th>Type</th>
              <th>Compliance Time</th>
              <th>Applicable Aircraft</th>
              <th>Evidence</th>
              <th>Status</th>
              <th>Gap</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ req, assessments, latest, evidenceCount, gap }) => (
              <tr key={req.id}>
                <td><Link href={`/regulations/${req.id}`} className="ac-mono">{req.requirementNumber}</Link></td>
                <td>{req.requirementType}</td>
                <td className="ac-text-sm">{req.complianceTime}</td>
                <td className="ac-text-sm">
                  {assessments.length === 0 ? "Insufficient source data." : (
                    assessments.map((a, idx) => {
                      const ac = a.subjectType === "AIRCRAFT" ? getAircraftById(a.subjectId) : undefined;
                      return (
                        <span key={a.id}>
                          {idx > 0 && ", "}
                          {ac ? <Link href={`/aircraft/${ac.id}`} className="ac-mono">{currentRegistration(ac)}</Link> : a.subjectId}
                        </span>
                      );
                    })
                  )}
                </td>
                <td>{latest ? evidenceCount : "—"}</td>
                <td>{latest ? <Link href={`/assessments/${latest.id}`}><StatusBadge status={latest.finalStatus} /></Link> : <StatusBadge status="INSUFFICIENT_DATA" label="No assessment" />}</td>
                <td>{gap ? <StatusBadge status="NON_COMPLIANT" label="Open" /> : <StatusBadge status="COMPLIANT" label="Closed" />}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

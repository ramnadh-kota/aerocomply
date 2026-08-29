"use client";

import { useState } from "react";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { StatusBadge } from "@/components/status/StatusBadge";
import { assessments } from "@/lib/mock/assessments";
import { getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
import { getRequirementById } from "@/lib/mock/regulations";
import type { ApplicabilityAssessment, SystemResult } from "@/lib/mock/types";

export default function AssessmentsListPage() {
  const [filter, setFilter] = useState<SystemResult | "ALL">("ALL");

  const rows = assessments.filter((a) => filter === "ALL" || a.systemResult === filter).sort((a, b) => b.evaluatedAt.localeCompare(a.evaluatedAt));

  const columns: Column<ApplicabilityAssessment>[] = [
    { key: "id", header: "Assessment", render: (a) => <span className="ac-mono">{a.id}</span> },
    { key: "req", header: "Requirement", render: (a) => <span className="ac-mono">{getRequirementById(a.regulatoryRequirementId)?.requirementNumber}</span> },
    {
      key: "subject",
      header: "Subject",
      render: (a) => {
        if (a.subjectType !== "AIRCRAFT") return a.subjectId;
        const ac = getAircraftById(a.subjectId);
        return ac ? currentRegistration(ac) : a.subjectId;
      },
    },
    { key: "date", header: "Date", render: (a) => new Date(a.evaluatedAt).toLocaleDateString(), sortValue: (a) => a.evaluatedAt },
    { key: "system", header: "System Result", render: (a) => <StatusBadge status={a.systemResult} /> },
    { key: "human", header: "Human Decision", render: (a) => a.humanDecision.replace(/_/g, " ") },
    { key: "final", header: "Status", render: (a) => <StatusBadge status={a.finalStatus} /> },
  ];

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Assessments" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Assessments</h1>
          <p className="ac-subtitle">{rows.length} of {assessments.length} shown</p>
        </div>
      </div>

      <div className="ac-flex ac-gap-2 ac-section" style={{ flexWrap: "wrap" }}>
        {(["ALL", "APPLICABLE", "NOT_APPLICABLE", "REVIEW_REQUIRED", "INSUFFICIENT_DATA"] as const).map((f) => (
          <button key={f} className="ac-btn" style={filter === f ? { borderColor: "var(--ac-accent)", color: "var(--ac-accent-hover)" } : undefined} onClick={() => setFilter(f)}>
            {f.replace(/_/g, " ")}
          </button>
        ))}
      </div>

      <div className="ac-card" style={{ padding: 0 }}>
        <DataTable columns={columns} rows={rows} getRowHref={(a) => `/assessments/${a.id}`} />
      </div>
    </div>
  );
}

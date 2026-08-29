"use client";

import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { regulatoryRequirements, getDocumentById, getAuthorityById } from "@/lib/mock/regulations";
import { assessmentsForRequirement } from "@/lib/mock/assessments";
import type { RegulatoryRequirement } from "@/lib/mock/types";

interface Row {
  requirement: RegulatoryRequirement;
  authorityCode: string;
  docNumber: string;
  title: string;
  revision: string;
  effectiveDate: string;
  aircraftCount: number;
}

function buildRows(): Row[] {
  return regulatoryRequirements.map((r) => {
    const doc = getDocumentById(r.regulatoryDocumentId)!;
    const authority = getAuthorityById(doc.regulatoryAuthorityId)!;
    const assessed = assessmentsForRequirement(r.id);
    const applicableCount = assessed.filter((a) => a.systemResult === "APPLICABLE").length;
    return {
      requirement: r,
      authorityCode: authority.code,
      docNumber: doc.docNumber,
      title: doc.title,
      revision: doc.revision,
      effectiveDate: doc.effectiveDate,
      aircraftCount: applicableCount,
    };
  });
}

export default function RegulationsLibraryPage() {
  const rows = buildRows();

  const columns: Column<Row>[] = [
    { key: "authority", header: "Authority", render: (r) => r.authorityCode, sortValue: (r) => r.authorityCode },
    { key: "doc", header: "Document", render: (r) => <span className="ac-mono">{r.docNumber}</span>, sortValue: (r) => r.docNumber },
    { key: "title", header: "Requirement", render: (r) => r.title, sortValue: (r) => r.title },
    { key: "rev", header: "Revision", render: (r) => r.revision },
    { key: "effective", header: "Effective Date", render: (r) => r.effectiveDate, sortValue: (r) => r.effectiveDate },
    { key: "type", header: "Type", render: (r) => r.requirement.requirementType },
    { key: "applicability", header: "Applicability", render: (r) => (r.aircraftCount > 0 ? `Applicable — ${r.aircraftCount} aircraft` : "Not yet assessed") },
  ];

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Regulations" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Regulatory Library</h1>
          <p className="ac-subtitle">
            {rows.length} requirements · <strong>Fictional demo records</strong> — not real, current, or legally binding requirements
          </p>
        </div>
      </div>
      <div className="ac-card" style={{ padding: 0 }}>
        <DataTable columns={columns} rows={rows} getRowHref={(r) => `/regulations/${r.requirement.id}`} />
      </div>
    </div>
  );
}

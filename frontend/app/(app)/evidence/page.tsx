"use client";

import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { StatusBadge } from "@/components/status/StatusBadge";
import { evidence } from "@/lib/mock/evidence";
import { getAssessmentById } from "@/lib/mock/assessments";
import { getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
import { getEngineById } from "@/lib/mock/engines";
import type { Evidence } from "@/lib/mock/types";

const TYPE_LABEL: Record<Evidence["evidenceType"], string> = {
  MAINTENANCE_RECORD: "Maintenance Record",
  OEM_DOCUMENT: "OEM Document",
  INSPECTION_RECORD: "Inspection Record",
  UPLOADED_DOCUMENT: "Uploaded File",
  STRUCTURED_RECORD_REFERENCE: "Structured Record Reference",
  REGULATORY_DOCUMENT: "Regulatory Document",
};

export default function EvidenceListPage() {
  const columns: Column<Evidence>[] = [
    { key: "id", header: "Evidence ID", render: (e) => <span className="ac-mono" id={e.id}>{e.id}</span> },
    { key: "type", header: "Type", render: (e) => TYPE_LABEL[e.evidenceType] },
    { key: "source", header: "Source", render: (e) => <span className="ac-mono">{e.sourceLabel}</span> },
    { key: "date", header: "Uploaded/Referenced", render: (e) => new Date(e.uploadedOrReferencedAt).toLocaleDateString(), sortValue: (e) => e.uploadedOrReferencedAt },
    {
      key: "assessment",
      header: "Assessment",
      render: (e) => {
        const a = getAssessmentById(e.applicabilityAssessmentId);
        return a ? <Link href={`/assessments/${a.id}`} className="ac-mono">{a.id}</Link> : e.applicabilityAssessmentId;
      },
    },
    {
      key: "related",
      header: "Related Aircraft/Engine",
      render: (e) => {
        const a = getAssessmentById(e.applicabilityAssessmentId);
        if (!a) return "—";
        if (a.subjectType === "AIRCRAFT") {
          const ac = getAircraftById(a.subjectId);
          return ac ? <Link href={`/aircraft/${ac.id}`} className="ac-mono">{currentRegistration(ac)}</Link> : a.subjectId;
        }
        const eng = getEngineById(a.subjectId);
        return eng ? <Link href={`/engines/${eng.id}`} className="ac-mono">{eng.serialNumber}</Link> : a.subjectId;
      },
    },
    { key: "status", header: "Status", render: (e) => <StatusBadge status={e.verificationStatus} /> },
  ];

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Evidence" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Evidence</h1>
          <p className="ac-subtitle">
            {evidence.length} evidence records · every record is scoped to exactly one assessment — this is not a general document library
          </p>
        </div>
      </div>
      <div className="ac-card" style={{ padding: 0 }}>
        <DataTable columns={columns} rows={evidence} />
      </div>
    </div>
  );
}

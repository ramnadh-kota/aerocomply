"use client";

import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { StatusBadge } from "@/components/status/StatusBadge";
import { regulatoryRequirements, regulatoryDocuments, getDocumentById, getAuthorityById } from "@/lib/mock/regulations";
import { assessmentsForRequirement } from "@/lib/mock/assessments";
import { MOCK_TODAY } from "@/lib/mock/workOrders";
import type { RegulatoryRequirement } from "@/lib/mock/types";

// M0.9 — regulatory-source honesty banner + "recently published" surface.
// Every RegulatoryDocument in this dataset is a hand-seeded, explicitly
// fictional demo record (see lib/mock/regulations.ts header) — there is no
// live DGCA/FAA/EASA feed wired into this prototype. Rather than let the
// clean table styling imply a live sync that doesn't exist, this page says
// so directly. "Recently published" below is real arithmetic over the
// dataset's actual publicationDate field, not a live-update detector.
function daysSincePublication(dateStr: string): number {
  return Math.round((new Date(MOCK_TODAY).getTime() - new Date(dateStr).getTime()) / 86400000);
}

interface Row {
  requirement: RegulatoryRequirement;
  authorityCode: string;
  docNumber: string;
  title: string;
  revision: string;
  effectiveDate: string;
  complianceTime: string;
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
      complianceTime: r.complianceTime,
      aircraftCount: applicableCount,
    };
  });
}

const RECENT_WINDOW_DAYS = 30;

export default function RegulationsLibraryPage() {
  const rows = buildRows();
  const recentlyPublished = [...regulatoryDocuments]
    .map((d) => ({ doc: d, daysSince: daysSincePublication(d.publicationDate), authority: getAuthorityById(d.regulatoryAuthorityId) }))
    .filter((d) => d.daysSince >= 0 && d.daysSince <= RECENT_WINDOW_DAYS)
    .sort((a, b) => a.daysSince - b.daysSince);

  const columns: Column<Row>[] = [
    { key: "authority", header: "Authority", render: (r) => r.authorityCode, sortValue: (r) => r.authorityCode },
    { key: "doc", header: "Document", render: (r) => <span className="ac-mono">{r.docNumber}</span>, sortValue: (r) => r.docNumber },
    { key: "title", header: "Requirement", render: (r) => r.title, sortValue: (r) => r.title },
    { key: "rev", header: "Revision", render: (r) => r.revision },
    { key: "effective", header: "Effective Date", render: (r) => r.effectiveDate, sortValue: (r) => r.effectiveDate },
    { key: "type", header: "Type", render: (r) => r.requirement.requirementType },
    { key: "deadline", header: "Compliance Deadline", render: (r) => <span className="ac-text-sm">{r.complianceTime}</span> },
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

      <section className="ac-section">
        <div className="ac-card">
          <div className="ac-flex ac-items-center ac-gap-2" style={{ marginBottom: 6 }}>
            <StatusBadge status="INSUFFICIENT_DATA" label="NOT CONFIGURED" />
            <p className="ac-eyebrow" style={{ margin: 0 }}>Regulatory Source Sync</p>
          </div>
          <p className="ac-text-sm ac-text-secondary" style={{ margin: 0 }}>
            No live DGCA / FAA / EASA feed is connected to this prototype. Every record below is a synchronized, hand-seeded
            demo dataset, not a live regulatory lookup — treat &quot;recently published&quot; as arithmetic over that dataset&apos;s
            recorded publication dates, not a detector of real-world regulatory change.
          </p>
        </div>
      </section>

      {recentlyPublished.length > 0 && (
        <section className="ac-section">
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Recently Published (last {RECENT_WINDOW_DAYS} days, by dataset date)</h2>
          <div style={{ display: "grid", gap: 8 }}>
            {recentlyPublished.map(({ doc, daysSince, authority }) => (
              <Link key={doc.id} href={`/regulations`} className="ac-card" style={{ display: "block" }}>
                <div className="ac-flex ac-justify-between ac-items-center" style={{ flexWrap: "wrap", gap: 8 }}>
                  <div>
                    <span className="ac-mono" style={{ fontWeight: 600 }}>{doc.docNumber}</span>{" "}
                    <span className="ac-text-sm ac-text-muted">{authority?.code ?? "Unknown authority"} · {doc.docType}</span>
                    <p className="ac-text-sm" style={{ margin: "2px 0 0" }}>{doc.title}</p>
                  </div>
                  <span className="ac-text-sm ac-text-muted">{daysSince === 0 ? "Published today" : `${daysSince}d ago`}</span>
                </div>
              </Link>
            ))}
          </div>
        </section>
      )}

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>All Requirements</h2>
        <div className="ac-card" style={{ padding: 0 }}>
          <DataTable columns={columns} rows={rows} getRowHref={(r) => `/regulations/${r.requirement.id}`} />
        </div>
      </section>
    </div>
  );
}

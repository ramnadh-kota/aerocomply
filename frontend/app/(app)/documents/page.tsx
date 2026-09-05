"use client";

import { useMemo, useState } from "react";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { StatusBadge } from "@/components/status/StatusBadge";
import {
  getAllDocuments,
  documentTypeOptions,
  EMPTY_DOCUMENT_CATEGORIES,
  type LibraryDocument,
  type LibraryDocumentStatus,
} from "@/lib/mock/documentLibrary";

// Document Library — aggregates document-like records that already exist
// across regulations, evidence, part certificates, and vendor records into
// one searchable view. This prototype has no object storage: every row
// links to the real underlying record's own detail page rather than a file
// download or preview, because no file content exists to open.

const STATUS_BADGE: Record<LibraryDocumentStatus, { status: Parameters<typeof StatusBadge>[0]["status"]; label: string }> = {
  Published: { status: "COMPLIANT", label: "Published" },
  Superseded: { status: "UNKNOWN", label: "Superseded" },
  Withdrawn: { status: "NON_COMPLIANT", label: "Withdrawn" },
  Draft: { status: "PENDING", label: "Draft" },
  Verified: { status: "VERIFIED", label: "Verified" },
  Unverified: { status: "UNVERIFIED", label: "Unverified" },
  Missing: { status: "REVIEW_REQUIRED", label: "Missing" },
  "Reference Unknown": { status: "INSUFFICIENT_DATA", label: "Reference Unknown" },
  Accepted: { status: "COMPLIANT", label: "Accepted" },
  Rejected: { status: "NON_COMPLIANT", label: "Rejected" },
  Submitted: { status: "PENDING", label: "Submitted" },
  "On File": { status: "ACTIVE", label: "On File" },
};

export default function DocumentLibraryPage() {
  const allDocuments = useMemo(() => getAllDocuments(), []);
  const [query, setQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState<"ALL" | LibraryDocument["type"]>("ALL");
  const [statusFilter, setStatusFilter] = useState<"ALL" | LibraryDocumentStatus>("ALL");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return allDocuments.filter((d) => {
      if (typeFilter !== "ALL" && d.type !== typeFilter) return false;
      if (statusFilter !== "ALL" && d.status !== statusFilter) return false;
      if (q && !d.title.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [allDocuments, query, typeFilter, statusFilter]);

  const statusOptions = useMemo(() => {
    const set = new Set<LibraryDocumentStatus>();
    allDocuments.forEach((d) => set.add(d.status));
    return Array.from(set).sort();
  }, [allDocuments]);

  const columns: Column<LibraryDocument>[] = [
    { key: "title", header: "Title", render: (d) => d.title, sortValue: (d) => d.title },
    { key: "type", header: "Type", render: (d) => d.type, sortValue: (d) => d.type },
    { key: "authority", header: "Authority / Source", render: (d) => d.authority ?? "—" },
    { key: "revision", header: "Revision", render: (d) => d.revision ?? "—" },
    { key: "effective", header: "Effective / Date", render: (d) => d.effectiveDate ?? "—", sortValue: (d) => d.effectiveDate ?? "" },
    { key: "status", header: "Status", render: (d) => <StatusBadge {...STATUS_BADGE[d.status]} /> },
  ];

  const countsByType = useMemo(() => {
    const map = new Map<string, number>();
    allDocuments.forEach((d) => map.set(d.type, (map.get(d.type) ?? 0) + 1));
    return map;
  }, [allDocuments]);

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Documents" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Document Library</h1>
          <p className="ac-subtitle">
            {filtered.length} of {allDocuments.length} documents shown — aggregated from regulatory documents, compliance
            evidence, execution evidence, part certificates, and vendor certifications already recorded elsewhere in this
            prototype. There is no object storage in this prototype — each row links to its real underlying record, not a
            file download.
          </p>
        </div>
      </div>

      <div className="ac-card" style={{ marginBottom: 16 }}>
        <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
          <input
            className="ac-input"
            style={{ flex: "1 1 240px" }}
            placeholder="Search document title…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Search documents"
          />
          <select
            className="ac-input"
            style={{ width: 220 }}
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value as "ALL" | LibraryDocument["type"])}
            aria-label="Filter by document type"
          >
            <option value="ALL">All Types</option>
            {documentTypeOptions().map((t) => (
              <option key={t} value={t}>
                {t} ({countsByType.get(t) ?? 0})
              </option>
            ))}
          </select>
          <select
            className="ac-input"
            style={{ width: 200 }}
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as "ALL" | LibraryDocumentStatus)}
            aria-label="Filter by status"
          >
            <option value="ALL">All Statuses</option>
            {statusOptions.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
      </div>

      <section className="ac-section">
        <div className="ac-card" style={{ padding: 0 }}>
          <DataTable
            columns={columns}
            rows={filtered}
            getRowHref={(d) => d.href}
            emptyMessage="No documents match this filter."
          />
        </div>
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Categories With No Records Yet</h2>
        <div style={{ display: "grid", gap: 8 }}>
          {EMPTY_DOCUMENT_CATEGORIES.map((c) => (
            <div key={c.type} className="ac-card">
              <div className="ac-flex ac-items-center ac-gap-2" style={{ marginBottom: 4 }}>
                <StatusBadge status="UNKNOWN" label="0 records" />
                <p className="ac-eyebrow" style={{ margin: 0 }}>{c.type}</p>
              </div>
              <p className="ac-text-sm ac-text-secondary" style={{ margin: 0 }}>{c.reason}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

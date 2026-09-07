"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { StatusBadge, partStatusBadge, traceabilityStatusBadge } from "@/components/status/StatusBadge";
import { parts } from "@/lib/mock/parts";
import { getWorkOrderById } from "@/lib/mock/workOrders";
import { getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
import { certificatesForPart, traceabilityStatusForPart } from "@/lib/mock/partTraceability";
import { useMroState } from "@/lib/mro-state/MroStateContext";
import type { Part, CertificateVerificationStatus, TraceabilityStatus } from "@/lib/mock/types";

// M7.2 — Parts Traceability Workspace. Extends the existing Parts &
// Inventory list (kept as the single parts table — no second parts system)
// with search/filter and traceability-aware columns, and links each row to
// the new /maintenance/parts/[id] traceability chain view.

export default function PartsInventoryPage() {
  const { submissions } = useMroState();
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [certFilter, setCertFilter] = useState<string>("ALL");
  const [traceFilter, setTraceFilter] = useState<string>("ALL");

  function certStatusForPart(partId: string): CertificateVerificationStatus | "NONE" {
    const certs = certificatesForPart(partId);
    return certs.length > 0 ? certs[0].verificationStatus : "NONE";
  }

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return parts.filter((p) => {
      if (statusFilter !== "ALL" && p.status !== statusFilter) return false;
      if (certFilter !== "ALL" && certStatusForPart(p.id) !== certFilter) return false;
      if (traceFilter !== "ALL" && traceabilityStatusForPart(p.id) !== (traceFilter as TraceabilityStatus)) return false;
      if (!q) return true;
      const aircraft = p.installedAircraftId ? getAircraftById(p.installedAircraftId) : undefined;
      const wo = p.workOrderId ? getWorkOrderById(p.workOrderId) : undefined;
      const haystack = [
        p.partNumber,
        p.serialNumber ?? "",
        aircraft ? currentRegistration(aircraft) : "",
        wo?.workOrderNumber ?? "",
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(q);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, statusFilter, certFilter, traceFilter]);

  const columns: Column<Part>[] = [
    { key: "pn", header: "Part Number", render: (p) => <span className="ac-mono">{p.partNumber}</span>, sortValue: (p) => p.partNumber },
    { key: "sn", header: "Serial / Batch", render: (p) => <span className="ac-mono">{p.serialNumber ?? p.batchOrLot ?? "—"}</span> },
    { key: "desc", header: "Description", render: (p) => p.description },
    { key: "status", header: "Status", render: (p) => <StatusBadge {...partStatusBadge(p.status)} /> },
    {
      key: "aircraft",
      header: "Aircraft",
      render: (p) => {
        if (!p.installedAircraftId) return <span className="ac-text-sm ac-text-muted">—</span>;
        const a = getAircraftById(p.installedAircraftId);
        return a ? <Link href={`/aircraft/${a.id}`} className="ac-mono">{currentRegistration(a)}</Link> : "Insufficient source data.";
      },
    },
    {
      key: "workOrder",
      header: "Work Order",
      render: (p) => {
        const wo = p.workOrderId ? getWorkOrderById(p.workOrderId) : undefined;
        if (!wo) return <span className="ac-text-sm ac-text-muted">—</span>;
        const record = submissions[wo.id];
        return (
          <span className="ac-flex ac-items-center ac-gap-2">
            <Link href={`/maintenance/work-orders/${wo.id}`} className="ac-mono">{wo.workOrderNumber}</Link>
            {record && <span className="ac-text-sm ac-text-muted">({record.submissionStatus === "SUBMITTED" ? "submitted" : "in progress"})</span>}
          </span>
        );
      },
    },
    {
      key: "cert",
      header: "Certificate",
      render: (p) => {
        const status = certStatusForPart(p.id);
        if (status === "NONE") return <span className="ac-text-sm ac-text-muted">Insufficient source data.</span>;
        return <StatusBadge {...traceabilityStatusForVerificationBadge(status)} />;
      },
    },
    {
      key: "trace",
      header: "Traceability",
      render: (p) => <StatusBadge {...traceabilityStatusBadge(traceabilityStatusForPart(p.id))} />,
    },
  ];

  function traceabilityStatusForVerificationBadge(status: CertificateVerificationStatus) {
    // local shim so the Certificate column reuses the same badge component
    // family as partStatusBadge/traceabilityStatusBadge without a duplicate map
    return { status: status === "PRESENT" ? ("COMPLIANT" as const) : status === "MISSING" ? ("REVIEW_REQUIRED" as const) : status === "NOT_VERIFIED" ? ("UNVERIFIED" as const) : ("INSUFFICIENT_DATA" as const), label: status.replace(/_/g, " ") };
  }

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Maintenance", href: "/maintenance/projects" }, { label: "Parts & Traceability" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Parts &amp; Traceability</h1>
          <p className="ac-subtitle">{filtered.length} of {parts.length} parts shown — search and filter by identity, status, certificate, or traceability completeness.</p>
        </div>
      </div>

      <div className="ac-card" style={{ marginBottom: 16 }}>
        <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
          <input
            className="ac-input"
            style={{ flex: "1 1 240px" }}
            placeholder="Search part number, serial, aircraft, or work order…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Search parts"
          />
          <select className="ac-input" style={{ width: 180 }} value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} aria-label="Filter by part status">
            <option value="ALL">All Statuses</option>
            <option value="IN_STOCK">In Stock</option>
            <option value="ORDERED">Ordered</option>
            <option value="AWAITING_RECEIPT">Awaiting Receipt</option>
          </select>
          <select className="ac-input" style={{ width: 200 }} value={certFilter} onChange={(e) => setCertFilter(e.target.value)} aria-label="Filter by certificate status">
            <option value="ALL">All Certificate Statuses</option>
            <option value="PRESENT">Certificate Present</option>
            <option value="MISSING">Certificate Missing</option>
            <option value="REFERENCE_UNKNOWN">Reference Unknown</option>
            <option value="NOT_VERIFIED">Not Verified</option>
            <option value="NONE">No Certificate Record</option>
          </select>
          <select className="ac-input" style={{ width: 180 }} value={traceFilter} onChange={(e) => setTraceFilter(e.target.value)} aria-label="Filter by traceability status">
            <option value="ALL">All Traceability Statuses</option>
            <option value="TRACEABLE">Traceable</option>
            <option value="PARTIAL">Partial</option>
            <option value="UNKNOWN">Unknown</option>
          </select>
        </div>
      </div>

      <div className="ac-card" style={{ padding: 0 }}>
        <DataTable columns={columns} rows={filtered} getRowHref={(p) => `/maintenance/parts/${p.id}`} emptyMessage="No parts match the current filters." />
      </div>
    </div>
  );
}

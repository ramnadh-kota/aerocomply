"use client";

import { useMemo, useState } from "react";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { StatusBadge } from "@/components/status/StatusBadge";
import { aircraft, aircraftVariants, getAircraftVariant, getAircraftType, currentRegistration } from "@/lib/mock/aircraft";
import { currentEnginesForAircraft, getEngineById, getEngineType } from "@/lib/mock/engines";
import { assessmentsForAircraft, latestAssessmentForAircraft } from "@/lib/mock/assessments";
import { getOrganizationById } from "@/lib/mock/organizations";
import { maintenanceEventsForAircraft } from "@/lib/mock/maintenance";
import type { Aircraft, MaintenanceEventStatus } from "@/lib/mock/types";

interface Row {
  aircraft: Aircraft;
  registration: string;
  typeDesignation: string;
  variantDesignation: string;
  operatorName: string;
  engineConfig: string;
  lastAssessmentDate: string | null;
  complianceLabel: "COMPLIANT" | "NON_COMPLIANT" | "REVIEW_REQUIRED" | "INSUFFICIENT_DATA" | "UNKNOWN";
  openAssessmentCount: number;
  maintenanceStatus: "OVERDUE" | "AWAITING_ACTION" | "SCHEDULED" | "UP_TO_DATE";
}

const MAINTENANCE_PRIORITY: MaintenanceEventStatus[] = ["OVERDUE", "AWAITING_REVIEW", "AWAITING_EVIDENCE", "IN_PROGRESS", "SCHEDULED"];

function deriveMaintenanceStatus(events: ReturnType<typeof maintenanceEventsForAircraft>): Row["maintenanceStatus"] {
  for (const status of MAINTENANCE_PRIORITY) {
    if (events.some((e) => e.status === status)) {
      if (status === "OVERDUE") return "OVERDUE";
      if (status === "SCHEDULED") return "SCHEDULED";
      return "AWAITING_ACTION";
    }
  }
  return "UP_TO_DATE";
}

function buildRows(): Row[] {
  return aircraft.map((a) => {
    const variant = getAircraftVariant(a.aircraftVariantId)!;
    const type = getAircraftType(variant.aircraftTypeId)!;
    const operator = getOrganizationById(a.operatorOrgId);
    const engines = currentEnginesForAircraft(a.id);
    const engineTypeLabel = engines.length
      ? Array.from(new Set(engines.map((e) => getEngineType(getEngineById(e.engineId)!.engineTypeId)!.modelDesignation))).join(", ")
      : "—";
    const lastAssessment = latestAssessmentForAircraft(a.id);
    const openAssessmentCount = assessmentsForAircraft(a.id).filter(
      (asmt) => asmt.humanDecision === "PENDING" || asmt.humanDecision === "REQUEST_MORE_EVIDENCE"
    ).length;
    return {
      aircraft: a,
      registration: currentRegistration(a),
      typeDesignation: type.designation,
      variantDesignation: variant.modelDesignation,
      operatorName: operator?.name ?? "—",
      engineConfig: engineTypeLabel,
      lastAssessmentDate: lastAssessment?.evaluatedAt ?? null,
      complianceLabel: lastAssessment?.finalStatus ?? "UNKNOWN",
      openAssessmentCount,
      maintenanceStatus: deriveMaintenanceStatus(maintenanceEventsForAircraft(a.id)),
    };
  });
}

export default function AircraftListPage() {
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("ALL");
  const [operatorFilter, setOperatorFilter] = useState("ALL");
  const [complianceFilter, setComplianceFilter] = useState("ALL");
  const [maintenanceFilter, setMaintenanceFilter] = useState("ALL");

  const rows = useMemo(buildRows, []);
  const operators = useMemo(() => Array.from(new Set(rows.map((r) => r.operatorName))), [rows]);
  const types = useMemo(() => Array.from(new Set(aircraftVariants.map((v) => getAircraftType(v.aircraftTypeId)!.designation))), []);

  const filtered = rows.filter((r) => {
    const q = search.trim().toLowerCase();
    if (q && !r.registration.toLowerCase().includes(q) && !r.aircraft.msn.toLowerCase().includes(q)) return false;
    if (typeFilter !== "ALL" && r.typeDesignation !== typeFilter) return false;
    if (operatorFilter !== "ALL" && r.operatorName !== operatorFilter) return false;
    if (complianceFilter !== "ALL" && r.complianceLabel !== complianceFilter) return false;
    if (maintenanceFilter !== "ALL" && r.maintenanceStatus !== maintenanceFilter) return false;
    return true;
  });

  const columns: Column<Row>[] = [
    { key: "registration", header: "Registration", render: (r) => <span className="ac-mono">{r.registration}</span>, sortValue: (r) => r.registration },
    { key: "type", header: "Aircraft Type", render: (r) => r.typeDesignation, sortValue: (r) => r.typeDesignation },
    { key: "variant", header: "Variant", render: (r) => r.variantDesignation, sortValue: (r) => r.variantDesignation },
    { key: "msn", header: "MSN", render: (r) => <span className="ac-mono">{r.aircraft.msn}</span>, sortValue: (r) => r.aircraft.msn },
    { key: "operator", header: "Operator", render: (r) => r.operatorName, sortValue: (r) => r.operatorName },
    { key: "status", header: "Status", render: (r) => <StatusBadge status={r.aircraft.status} /> },
    { key: "engines", header: "Current Engine Configuration", render: (r) => r.engineConfig },
    {
      key: "lastAssessment",
      header: "Last Assessment",
      render: (r) => (r.lastAssessmentDate ? new Date(r.lastAssessmentDate).toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" }) : "—"),
      sortValue: (r) => r.lastAssessmentDate ?? "",
    },
    { key: "compliance", header: "Compliance", render: (r) => <StatusBadge status={r.complianceLabel} /> },
    { key: "openAssessments", header: "Open Assessments", render: (r) => r.openAssessmentCount, sortValue: (r) => r.openAssessmentCount },
    {
      key: "maintenance",
      header: "Maintenance Status",
      render: (r) => {
        const map = {
          OVERDUE: { status: "NON_COMPLIANT" as const, label: "Overdue" },
          AWAITING_ACTION: { status: "REVIEW_REQUIRED" as const, label: "Awaiting Action" },
          SCHEDULED: { status: "PENDING" as const, label: "Scheduled" },
          UP_TO_DATE: { status: "COMPLIANT" as const, label: "Up to Date" },
        };
        const m = map[r.maintenanceStatus];
        return <StatusBadge status={m.status} label={m.label} />;
      },
    },
  ];

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Aircraft" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Aircraft Fleet</h1>
          <p className="ac-subtitle">{filtered.length} of {rows.length} aircraft shown</p>
        </div>
      </div>

      <div className="ac-card ac-section" style={{ padding: "var(--ac-space-4)" }}>
        <div className="ac-flex ac-gap-3" style={{ flexWrap: "wrap" }}>
          <input
            type="search"
            placeholder="Search registration or MSN…"
            className="ac-input"
            style={{ maxWidth: 260 }}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            aria-label="Search aircraft"
          />
          <select className="ac-input" style={{ width: 180 }} value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} aria-label="Filter by aircraft type">
            <option value="ALL">All Aircraft Types</option>
            {types.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
          <select className="ac-input" style={{ width: 200 }} value={operatorFilter} onChange={(e) => setOperatorFilter(e.target.value)} aria-label="Filter by operator">
            <option value="ALL">All Operators</option>
            {operators.map((o) => (
              <option key={o} value={o}>{o}</option>
            ))}
          </select>
          <select className="ac-input" style={{ width: 200 }} value={complianceFilter} onChange={(e) => setComplianceFilter(e.target.value)} aria-label="Filter by compliance status">
            <option value="ALL">All Compliance Statuses</option>
            <option value="COMPLIANT">Compliant</option>
            <option value="NON_COMPLIANT">Non-Compliant</option>
            <option value="REVIEW_REQUIRED">Review Required</option>
            <option value="INSUFFICIENT_DATA">Insufficient Data</option>
          </select>
          <select className="ac-input" style={{ width: 190 }} value={maintenanceFilter} onChange={(e) => setMaintenanceFilter(e.target.value)} aria-label="Filter by maintenance status">
            <option value="ALL">All Maintenance Statuses</option>
            <option value="OVERDUE">Overdue</option>
            <option value="AWAITING_ACTION">Awaiting Action</option>
            <option value="SCHEDULED">Scheduled</option>
            <option value="UP_TO_DATE">Up to Date</option>
          </select>
        </div>
      </div>

      <div className="ac-card" style={{ padding: 0 }}>
        <DataTable columns={columns} rows={filtered} getRowHref={(r) => `/aircraft/${r.aircraft.id}`} emptyMessage="No aircraft match the current filters." />
      </div>
    </div>
  );
}

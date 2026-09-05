"use client";

import { Suspense, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge, riskLevelBadge } from "@/components/status/StatusBadge";
import { maintenancePrograms, maintenanceRequirements, requirementsForProgram } from "@/lib/mock/maintenanceProgram";
import { aircraft, getAircraftVariant, getAircraftType, currentRegistration } from "@/lib/mock/aircraft";
import { workOrdersForAircraft } from "@/lib/mock/workOrders";
import {
  getFleetMaintenanceDue,
  getMaintenanceDueForAircraft,
  getDeferredItemsForAircraft,
  getAircraftOperationalRisk,
  type MaintenanceDueStatus,
} from "@/lib/mock/ai/analytics";

// M17 — due-status badge mapping, local to this page (not a shared
// component change) since this is the only page rendering all five
// MaintenanceDueStatus values in one table.
const DUE_STATUS_BADGE: Record<MaintenanceDueStatus, { status: Parameters<typeof StatusBadge>[0]["status"]; label: string }> = {
  CURRENT: { status: "COMPLIANT", label: "CURRENT" },
  DUE_SOON: { status: "PENDING", label: "DUE SOON" },
  DUE: { status: "REVIEW_REQUIRED", label: "DUE" },
  OVERDUE: { status: "NON_COMPLIANT", label: "OVERDUE" },
  UNKNOWN: { status: "INSUFFICIENT_DATA", label: "UNKNOWN" },
};

// M0.6 — fleet operational status derived entirely from the SAME canonical
// engines the rest of the app already uses (getMaintenanceDueForAircraft,
// getDeferredItemsForAircraft, workOrdersForAircraft, getAircraftOperationalRisk).
// This is presentation-only aggregation — no new business calculation.
type FleetFilter = "ALL" | "ATTENTION" | "OVERDUE" | "DUE_SOON" | "IN_MAINTENANCE" | "AWAITING_INSPECTION" | "DEFERRED";

const FILTERS: { key: FleetFilter; label: string }[] = [
  { key: "ALL", label: "All" },
  { key: "ATTENTION", label: "Attention Required" },
  { key: "OVERDUE", label: "Overdue" },
  { key: "DUE_SOON", label: "Due Soon" },
  { key: "IN_MAINTENANCE", label: "In Maintenance" },
  { key: "AWAITING_INSPECTION", label: "Awaiting Inspection" },
  { key: "DEFERRED", label: "Deferred" },
];

function buildAircraftSummary(a: (typeof aircraft)[number]) {
  const registration = currentRegistration(a);
  const variant = getAircraftVariant(a.aircraftVariantId);
  const type = variant ? getAircraftType(variant.aircraftTypeId) : undefined;
  const due = getMaintenanceDueForAircraft(a.id);
  const overdue = due.filter((d) => d.dueStatus === "OVERDUE");
  const dueSoon = due.filter((d) => d.dueStatus === "DUE_SOON" || d.dueStatus === "DUE");
  const unknown = due.filter((d) => d.dueStatus === "UNKNOWN");
  const workOrders = workOrdersForAircraft(a.id);
  const openWorkOrders = workOrders.filter((w) => w.status !== "COMPLETED" && w.status !== "CANCELLED");
  const awaitingInspection = workOrders.filter((w) => w.status === "WAITING_INSPECTION");
  const deferred = getDeferredItemsForAircraft(a.id).filter((d) => d.status !== "CLOSED");
  const risk = getAircraftOperationalRisk(a.id);

  const nextDue = [...overdue, ...dueSoon].sort((x, y) => (x.dueStatus === "OVERDUE" ? -1 : 1) - (y.dueStatus === "OVERDUE" ? -1 : 1))[0];

  // Single operational status derived from the same priority ordering used
  // fleet-wide (overdue beats due-soon beats deferred beats current) — no
  // separate status calculation, just a display-priority pick over data
  // already computed by the canonical engines above.
  let status: "OVERDUE" | "DUE_SOON" | "DEFERRED" | "AWAITING_INSPECTION" | "CURRENT" | "UNKNOWN";
  if (overdue.length > 0) status = "OVERDUE";
  else if (awaitingInspection.length > 0) status = "AWAITING_INSPECTION";
  else if (dueSoon.length > 0) status = "DUE_SOON";
  else if (deferred.length > 0) status = "DEFERRED";
  else if (due.length > 0 && due.every((d) => d.dueStatus === "UNKNOWN")) status = "UNKNOWN";
  else status = "CURRENT";

  const attentionRequired = overdue.length > 0 || awaitingInspection.length > 0 || (risk?.risk === "HIGH");

  return {
    aircraftId: a.id,
    registration,
    typeLabel: type && variant ? `${type.manufacturer} ${variant.modelDesignation}` : "Insufficient source data.",
    overdueCount: overdue.length,
    dueSoonCount: dueSoon.length,
    unknownCount: unknown.length,
    openWorkOrderCount: openWorkOrders.length,
    awaitingInspectionCount: awaitingInspection.length,
    deferredCount: deferred.length,
    risk: risk?.risk ?? null,
    status,
    attentionRequired,
    nextDueDescription: nextDue?.description ?? null,
    nextDueRemaining: nextDue?.remaining ?? null,
  };
}

const STATUS_BADGE: Record<ReturnType<typeof buildAircraftSummary>["status"], { status: Parameters<typeof StatusBadge>[0]["status"]; label: string }> = {
  OVERDUE: { status: "NON_COMPLIANT", label: "OVERDUE" },
  DUE_SOON: { status: "PENDING", label: "DUE SOON" },
  DEFERRED: { status: "REVIEW_REQUIRED", label: "DEFERRED" },
  AWAITING_INSPECTION: { status: "REVIEW_REQUIRED", label: "AWAITING INSPECTION" },
  CURRENT: { status: "COMPLIANT", label: "CURRENT" },
  UNKNOWN: { status: "INSUFFICIENT_DATA", label: "UNKNOWN" },
};

// M15 — Maintenance Program foundation. Every record here is explicitly
// DEMO DATA (see lib/mock/maintenanceProgram.ts header) — a prototype
// program built to exercise the interval/applicability/forecasting
// architecture, not a real approved aircraft maintenance program. This page
// says so directly rather than letting the clean table styling imply
// authority the data doesn't have.

export default function MaintenanceProgramPage() {
  return (
    <Suspense fallback={<div className="ac-card">Loading maintenance program…</div>}>
      <MaintenanceProgramBody />
    </Suspense>
  );
}

function MaintenanceProgramBody() {
  const searchParams = useSearchParams();
  const initialFilter = (searchParams.get("filter")?.toUpperCase() as FleetFilter | null) ?? null;
  const normalizedInitial: FleetFilter =
    initialFilter === "OVERDUE" || initialFilter === "DUE_SOON" || initialFilter === "ATTENTION" ||
    initialFilter === "IN_MAINTENANCE" || initialFilter === "AWAITING_INSPECTION" || initialFilter === "DEFERRED"
      ? initialFilter
      : "ALL";
  const [filter, setFilter] = useState<FleetFilter>(normalizedInitial);

  const dueRows = getFleetMaintenanceDue().flatMap((f) => f.items.map((i) => ({ registration: f.registration, aircraftId: f.aircraftId, ...i })));

  const fleetSummary = useMemo(() => aircraft.map(buildAircraftSummary), []);

  const filtered = useMemo(() => {
    switch (filter) {
      case "ATTENTION":
        return fleetSummary.filter((f) => f.attentionRequired);
      case "OVERDUE":
        return fleetSummary.filter((f) => f.overdueCount > 0);
      case "DUE_SOON":
        return fleetSummary.filter((f) => f.dueSoonCount > 0);
      case "IN_MAINTENANCE":
        return fleetSummary.filter((f) => f.openWorkOrderCount > 0);
      case "AWAITING_INSPECTION":
        return fleetSummary.filter((f) => f.awaitingInspectionCount > 0);
      case "DEFERRED":
        return fleetSummary.filter((f) => f.deferredCount > 0);
      default:
        return fleetSummary;
    }
  }, [fleetSummary, filter]);

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Maintenance Program" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Maintenance Program</h1>
          <p className="ac-subtitle">
            Prototype architecture for maintenance-program intervals and applicability. Every record below is explicitly demo
            data, not an approved maintenance program — see each requirement&apos;s source.
          </p>
        </div>
      </div>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Fleet Maintenance Status</h2>
        <p className="ac-text-sm ac-text-muted" style={{ marginBottom: 10 }}>
          One card per aircraft, derived from the same maintenance-due, deferred-item, and work-order data used throughout
          this platform. Selecting a filter narrows the list below — it does not recalculate anything.
        </p>

        <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap", marginBottom: 14 }}>
          {FILTERS.map((f) => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={`ac-btn${filter === f.key ? " ac-btn-primary" : ""}`}
              style={{ fontSize: 13, padding: "6px 12px", minHeight: 36 }}
            >
              {f.label}
            </button>
          ))}
        </div>

        <div style={{ display: "grid", gap: 10 }}>
          {filtered.map((f) => {
            const badge = STATUS_BADGE[f.status];
            return (
              <Link
                key={f.aircraftId}
                href={`/aircraft/${f.aircraftId}`}
                className="ac-card"
                style={{ display: "block", textDecoration: "none", color: "inherit" }}
              >
                <div className="ac-flex ac-justify-between ac-items-center" style={{ flexWrap: "wrap", gap: 8, marginBottom: 8 }}>
                  <div className="ac-flex ac-items-center ac-gap-2" style={{ flexWrap: "wrap" }}>
                    <span className="ac-mono" style={{ fontWeight: 700, fontSize: 16 }}>{f.registration}</span>
                    <span className="ac-text-sm ac-text-muted">{f.typeLabel}</span>
                  </div>
                  <div className="ac-flex ac-items-center ac-gap-2">
                    {f.risk && <StatusBadge {...riskLevelBadge(f.risk)} />}
                    <StatusBadge status={badge.status} label={badge.label} />
                  </div>
                </div>

                <div className="ac-flex ac-gap-3" style={{ flexWrap: "wrap" }}>
                  <span className="ac-text-sm"><strong>{f.overdueCount}</strong> overdue</span>
                  <span className="ac-text-sm"><strong>{f.dueSoonCount}</strong> due soon</span>
                  <span className="ac-text-sm"><strong>{f.openWorkOrderCount}</strong> open work order{f.openWorkOrderCount === 1 ? "" : "s"}</span>
                  <span className="ac-text-sm"><strong>{f.awaitingInspectionCount}</strong> awaiting inspection</span>
                  <span className="ac-text-sm"><strong>{f.deferredCount}</strong> deferred item{f.deferredCount === 1 ? "" : "s"}</span>
                  {f.unknownCount > 0 && <span className="ac-text-sm ac-text-muted">{f.unknownCount} unknown-status item{f.unknownCount === 1 ? "" : "s"}</span>}
                </div>

                {f.nextDueDescription && (
                  <p className="ac-text-sm ac-text-muted" style={{ margin: "8px 0 0" }}>
                    Next: {f.nextDueDescription} — {f.nextDueRemaining}
                  </p>
                )}
              </Link>
            );
          })}
          {filtered.length === 0 && (
            <div className="ac-card"><p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>No aircraft match this filter.</p></div>
          )}
        </div>
      </section>

      {maintenancePrograms.map((p) => (
        <section className="ac-section" key={p.id}>
          <div className="ac-card">
            <div className="ac-flex ac-justify-between" style={{ flexWrap: "wrap", gap: 10, marginBottom: 8 }}>
              <div>
                <p className="ac-eyebrow" style={{ marginBottom: 4 }}>{p.name}</p>
                <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Revision {p.revision} · Effective {p.effectiveDate}</p>
              </div>
              <StatusBadge status={p.status === "ACTIVE" ? "COMPLIANT" : p.status === "DRAFT" ? "PENDING" : "INSUFFICIENT_DATA"} label={p.status} />
            </div>
            <p className="ac-text-sm" style={{ margin: "0 0 12px", fontWeight: 600 }}>Source: {p.source}</p>
            <div className="ac-card" style={{ padding: 0, overflowX: "auto" }}>
              <table className="ac-table">
                <thead><tr><th>ATA</th><th>Requirement</th><th>Interval</th><th>Task Reference</th></tr></thead>
                <tbody>
                  {requirementsForProgram(p.id).map((r) => (
                    <tr key={r.id}>
                      <td className="ac-mono">{r.ataChapter}</td>
                      <td className="ac-text-sm">{r.description}</td>
                      <td className="ac-text-sm">
                        {r.intervalType === "FH" && `${r.fhInterval} FH`}
                        {r.intervalType === "FC" && `${r.fcInterval} FC`}
                        {r.intervalType === "CALENDAR" && `${r.calendarIntervalDays} days`}
                        {r.intervalType === "FH_OR_CALENDAR" && `${r.fhInterval} FH or ${r.calendarIntervalDays} days`}
                        {r.intervalType === "FC_OR_CALENDAR" && `${r.fcInterval} FC or ${r.calendarIntervalDays} days`}
                        {r.intervalType === "FH_AND_FC" && `${r.fhInterval} FH and ${r.fcInterval} FC`}
                      </td>
                      <td className="ac-mono ac-text-sm">{r.taskReference ?? "Insufficient source data."}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      ))}

      {maintenanceRequirements.length === 0 && (
        <div className="ac-card"><p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>No maintenance program on file.</p></div>
      )}

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Requirement-Level Due Status</h2>
        <p className="ac-text-sm ac-text-muted" style={{ marginBottom: 10 }}>
          One row per (aircraft, requirement) pair the requirement applies to. Computed from real accomplishment records
          (lib/mock/maintenanceAccomplishments.ts) and current aircraft utilization — never from a work order&apos;s planned or
          scheduled date. UNKNOWN rows state why.
        </p>
        <div className="ac-card" style={{ padding: 0, overflowX: "auto" }}>
          <table className="ac-table">
            <thead>
              <tr><th>Aircraft</th><th>Requirement</th><th>Basis</th><th>Last Accomplished</th><th>Next Due</th><th>Remaining</th><th>Status</th><th>Note</th></tr>
            </thead>
            <tbody>
              {dueRows.map((r) => {
                const badge = DUE_STATUS_BADGE[r.dueStatus];
                return (
                  <tr key={`${r.aircraftId}-${r.requirementId}`}>
                    <td><Link href={`/aircraft/${r.aircraftId}`} className="ac-mono">{r.registration}</Link></td>
                    <td className="ac-text-sm">{r.description}</td>
                    <td>{r.basis}</td>
                    <td className="ac-text-sm">{r.lastAccomplished}</td>
                    <td className="ac-text-sm">{r.nextDue}</td>
                    <td className="ac-text-sm">{r.remaining}</td>
                    <td><StatusBadge status={badge.status} label={badge.label} /></td>
                    <td className="ac-text-sm ac-text-muted">{r.dataQualityNote}</td>
                  </tr>
                );
              })}
              {dueRows.length === 0 && (
                <tr><td colSpan={8} className="ac-text-sm ac-text-muted" style={{ textAlign: "center", padding: 16 }}>No requirement currently applies to any aircraft.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="ac-section">
        <p className="ac-text-sm ac-text-muted">
          Ask Lisa (&quot;what maintenance is coming due for VT-ABC&quot;, &quot;what maintenance is overdue?&quot;) for the same
          data with an explanation.
        </p>
      </section>
    </div>
  );
}

"use client";

// Live-data versions of pages that previously contained only sample data. Each one reads the corresponding backend
// API through the existing typed client; Demo sessions still render the original sample-data page (see withLive).

import type React from "react";
import { useEffect, useState } from "react";
import Link from "next/link";
import { PageHeader } from "@/components/layout/PageHeader";
import { StatusBadge } from "@/components/status/StatusBadge";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { useSession } from "@/lib/auth/SessionContext";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import { LiveDetail, LiveList } from "@/components/live/LiveViews";
import { formatScalar } from "@/lib/live/format";
import { evidenceApi, type BackendEvidence } from "@/lib/api/evidence";
import { partsApi, type BackendPart } from "@/lib/api/parts";
import { vendorsApi, type BackendVendor } from "@/lib/api/vendors";
import { procurementRequestsApi, type BackendProcurementRequest } from "@/lib/api/procurementRequests";
import { purchaseOrdersApi, type BackendPurchaseOrder } from "@/lib/api/purchaseOrders";
import { regulatoryRequirementsApi, type BackendRegulatoryRequirement } from "@/lib/api/compliance";
import { assessmentsApi, type BackendAssessment } from "@/lib/api/assessments";
import { findingsApi, type BackendFinding } from "@/lib/api/findings";
import { proactiveApi, type BackendProactiveAlert } from "@/lib/api/proactive";
import { fleetComponentsApi, type FleetComponent } from "@/lib/api/fleetComponents";
import { maintenanceRequirementsApi, type BackendMaintenanceRequirement } from "@/lib/api/maintenanceRequirements";

const date = (v: string | null | undefined) => formatScalar("created_at", v ?? null);
const yesNo = (b: boolean) => (b ? "Yes" : "No");

// ---------------------------------------------------------------- evidence
export function LiveEvidenceList() {
  return (
    <LiveList<BackendEvidence>
      title="Evidence"
      subtitle="Evidence register for your organization."
      breadcrumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Evidence" }]}
      load={(t) => evidenceApi.list(t, { limit: 200 })}
      columns={[
        { header: "Title", render: (e) => e.title || e.id.slice(0, 8) },
        { header: "Type", render: (e) => e.evidence_type ?? "—" },
        { header: "Status", render: (e) => <StatusBadge status={e.status === "ACCEPTED" ? "COMPLIANT" : e.status === "REJECTED" ? "NON_COMPLIANT" : "REVIEW_REQUIRED"} label={e.status} /> },
        { header: "Verification", render: (e) => e.verification_status ?? "—" },
        { header: "Captured", render: (e) => date(e.captured_at ?? e.created_at) },
      ]}
      rowHref={(e) => `/compliance/evidence/${e.id}`}
      emptyMessage="No evidence has been recorded yet."
      searchText={(e) => `${e.title ?? ""} ${e.evidence_type ?? ""} ${e.status}`}
    />
  );
}

// ---------------------------------------------------------------- parts
export function LivePartsList() {
  return (
    <LiveList<BackendPart>
      title="Parts"
      subtitle="Part inventory and serviceability."
      breadcrumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Procurement", href: "/procurement" }, { label: "Parts" }]}
      load={partsApi.list}
      columns={[
        { header: "Part number", render: (p) => p.part_number },
        { header: "Description", render: (p) => p.description },
        { header: "Condition", render: (p) => p.condition ?? "—" },
        { header: "Serviceability", render: (p) => p.serviceability_status },
        { header: "On hand", render: (p) => p.quantity_on_hand },
        { header: "Available", render: (p) => p.available_quantity },
        { header: "Quarantined", render: (p) => p.quantity_quarantined },
      ]}
      rowHref={(p) => `/maintenance/parts/${p.id}`}
      emptyMessage="No parts in inventory."
      searchText={(p) => `${p.part_number} ${p.description} ${p.manufacturer ?? ""}`}
    />
  );
}

export function LivePartDetail() {
  return (
    <LiveDetail<BackendPart>
      breadcrumbs={(p) => [{ label: "Dashboard", href: "/dashboard" }, { label: "Parts", href: "/procurement/parts" }, { label: p?.part_number ?? "…" }]}
      title={(p) => `${p.part_number} — ${p.description}`}
      load={partsApi.get}
      notFound="Part not found."
    />
  );
}

// ---------------------------------------------------------------- vendors
export function LiveVendorsList() {
  return (
    <LiveList<BackendVendor>
      title="Vendors"
      subtitle="Approved vendors and reliability."
      breadcrumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Procurement", href: "/procurement" }, { label: "Vendors" }]}
      load={vendorsApi.list}
      columns={[
        { header: "Vendor", render: (v) => v.name },
        { header: "Location", render: (v) => v.location ?? "—" },
        { header: "Approved", render: (v) => yesNo(v.approved) },
        { header: "Reliability", render: (v) => (v.reliability_score === null ? "—" : v.reliability_score) },
        { header: "Certifications", render: (v) => v.certifications ?? "—" },
      ]}
      rowHref={(v) => `/procurement/vendors/${v.id}`}
      emptyMessage="No vendors registered."
      searchText={(v) => `${v.name} ${v.location ?? ""} ${v.certifications ?? ""}`}
    />
  );
}

export function LiveVendorDetail() {
  return (
    <LiveDetail<BackendVendor>
      breadcrumbs={(v) => [{ label: "Dashboard", href: "/dashboard" }, { label: "Vendors", href: "/procurement/vendors" }, { label: v?.name ?? "…" }]}
      title={(v) => v.name}
      load={vendorsApi.get}
      notFound="Vendor not found."
    />
  );
}

// ---------------------------------------------------------------- procurement requests (approval queue)
export function LiveRequestsList() {
  return (
    <LiveList<BackendProcurementRequest>
      title="Procurement Approvals"
      subtitle="Procurement requests and their approval status."
      breadcrumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Procurement", href: "/procurement" }, { label: "Approvals" }]}
      load={(t) => procurementRequestsApi.list(t)}
      columns={[
        { header: "Part number", render: (r) => r.part_number },
        { header: "Description", render: (r) => r.description },
        { header: "Qty", render: (r) => r.quantity },
        { header: "Priority", render: (r) => r.priority },
        { header: "Status", render: (r) => r.status },
        { header: "Requested", render: (r) => date(r.created_at) },
      ]}
      rowHref={(r) => `/procurement/approvals/${r.id}`}
      emptyMessage="No procurement requests."
      searchText={(r) => `${r.part_number} ${r.description} ${r.status} ${r.priority}`}
    />
  );
}

export function LiveRequestDetail() {
  return (
    <LiveDetail<BackendProcurementRequest>
      breadcrumbs={(r) => [{ label: "Dashboard", href: "/dashboard" }, { label: "Approvals", href: "/procurement/approvals" }, { label: r?.part_number ?? "…" }]}
      title={(r) => `Request — ${r.part_number}`}
      load={procurementRequestsApi.get}
      notFound="Procurement request not found."
    />
  );
}

// ---------------------------------------------------------------- purchase order detail
export function LivePurchaseOrderDetail() {
  return (
    <LiveDetail<BackendPurchaseOrder>
      breadcrumbs={(p) => [{ label: "Dashboard", href: "/dashboard" }, { label: "Purchase Orders", href: "/procurement/purchase-orders" }, { label: p?.po_number ?? "…" }]}
      title={(p) => `PO ${p.po_number}`}
      load={purchaseOrdersApi.get}
      notFound="Purchase order not found."
      extra={(p) => (
        <div className="ac-card" style={{ padding: 0, overflowX: "auto" }}>
          <table className="ac-table" style={{ width: "100%" }}>
            <thead><tr><th>Part number</th><th>Description</th><th>Qty</th><th>Received</th><th>Unit price</th></tr></thead>
            <tbody>
              {p.lines.map((l) => (
                <tr key={l.id}>
                  <td>{l.part_number}</td><td>{l.description}</td><td>{l.quantity}</td><td>{l.received_quantity}</td>
                  <td>{formatScalar("unit_price_cents", l.unit_price_cents)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    />
  );
}

// ---------------------------------------------------------------- regulations
export function LiveRegulationsList() {
  return (
    <LiveList<BackendRegulatoryRequirement>
      title="Regulations"
      subtitle="Regulatory requirements registered for your organization."
      breadcrumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Regulations" }]}
      load={regulatoryRequirementsApi.list}
      columns={[
        { header: "Requirement", render: (r) => r.requirement_number },
        { header: "Authority", render: (r) => r.authority },
        { header: "Title", render: (r) => r.title },
        { header: "Effective", render: (r) => date(r.effective_date) },
        { header: "Compliance time", render: (r) => r.compliance_time ?? "—" },
      ]}
      rowHref={(r) => `/regulations/${r.id}`}
      emptyMessage="No regulatory requirements registered."
      searchText={(r) => `${r.requirement_number} ${r.authority} ${r.title}`}
    />
  );
}

export function LiveRegulationDetail() {
  return (
    <LiveDetail<BackendRegulatoryRequirement>
      breadcrumbs={(r) => [{ label: "Dashboard", href: "/dashboard" }, { label: "Regulations", href: "/regulations" }, { label: r?.requirement_number ?? "…" }]}
      title={(r) => `${r.authority} ${r.requirement_number}`}
      load={regulatoryRequirementsApi.get}
      notFound="Requirement not found."
    />
  );
}

// ---------------------------------------------------------------- assessments
export function LiveAssessmentsList() {
  return (
    <LiveList<BackendAssessment>
      title="Assessments"
      subtitle="Compliance assessments and their latest run status."
      breadcrumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Assessments" }]}
      load={assessmentsApi.list}
      columns={[
        { header: "Name", render: (a) => a.name },
        { header: "Scope", render: (a) => a.scope_type },
        { header: "Status", render: (a) => a.status },
        { header: "Created", render: (a) => date(a.created_at) },
      ]}
      rowHref={(a) => `/assessments/${a.id}`}
      emptyMessage="No assessments yet."
      searchText={(a) => `${a.name} ${a.scope_type} ${a.status}`}
    />
  );
}

export function LiveAssessmentDetail() {
  return (
    <LiveDetail<BackendAssessment>
      breadcrumbs={(a) => [{ label: "Dashboard", href: "/dashboard" }, { label: "Assessments", href: "/assessments" }, { label: a?.name ?? "…" }]}
      title={(a) => a.name}
      load={assessmentsApi.get}
      notFound="Assessment not found."
      extra={(a) => (
        <p className="ac-text-sm">
          Scoring, findings, risks and roadmap are available under{" "}
          <Link href={`/assessment-intelligence`} className="ac-link">Assessment Intelligence</Link>.
          {a.status === "COMPLETE" ? "" : " Run the assessment to produce a snapshot."}
        </p>
      )}
    />
  );
}

// ---------------------------------------------------------------- procurement home
export function LiveProcurementHome() {
  const { accessToken, isAuthenticated } = useSession();
  const [counts, setCounts] = useState<{ parts: number; vendors: number; requests: number; pos: number; openRequests: number } | null>(null);
  const [error, setError] = useState<NormalizedApiError | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!isAuthenticated || !accessToken) return;
    let off = false;
    Promise.all([partsApi.list(accessToken), vendorsApi.list(accessToken), procurementRequestsApi.list(accessToken), purchaseOrdersApi.list(accessToken)])
      .then(([p, v, r, o]) => {
        if (!off) setCounts({ parts: p.length, vendors: v.length, requests: r.length, pos: o.length,
          openRequests: r.filter((x) => !["CLOSED", "REJECTED", "RECEIVED"].includes(x.status)).length });
      })
      .catch((e) => { if (!off) setError(normalizeApiError(e)); })
      .finally(() => { if (!off) setLoading(false); });
    return () => { off = true; };
  }, [accessToken, isAuthenticated]);

  const tiles = counts && [
    { label: "Parts", value: counts.parts, href: "/procurement/parts" },
    { label: "Vendors", value: counts.vendors, href: "/procurement/vendors" },
    { label: "Open requests", value: counts.openRequests, href: "/procurement/approvals" },
    { label: "Purchase orders", value: counts.pos, href: "/procurement/purchase-orders" },
  ];
  return (
    <div>
      <PageHeader breadcrumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Procurement" }]} title="Procurement" subtitle="Parts, vendors, requests and purchase orders." />
      <RealDataPanel loading={loading} error={error} isEmpty={!counts} emptyMessage="No procurement data.">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 16 }}>
          {tiles?.map((t) => (
            <Link key={t.label} href={t.href} className="ac-card" style={{ padding: 16, textDecoration: "none" }}>
              <span className="ac-text-sm ac-text-muted">{t.label}</span>
              <div style={{ fontSize: 28, fontWeight: 700 }}>{t.value}</div>
            </Link>
          ))}
        </div>
      </RealDataPanel>
    </div>
  );
}

// ---------------------------------------------------------------- defects (findings)
export function LiveDefectsList() {
  return (
    <LiveList<BackendFinding>
      title="Defects & Findings"
      subtitle="Findings raised against your assets, with severity and status."
      breadcrumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Maintenance" }, { label: "Defects" }]}
      load={(t) => findingsApi.listForOrganization(t)}
      columns={[
        { header: "Title", render: (f) => f.title },
        { header: "Severity", render: (f) => f.severity },
        { header: "Status", render: (f) => f.status },
        { header: "Discovered", render: (f) => date(f.discovered_at) },
      ]}
      rowHref={(f) => `/findings/${f.id}`}
      emptyMessage="No findings recorded."
      searchText={(f) => `${f.title} ${f.severity} ${f.status}`}
    />
  );
}

// ---------------------------------------------------------------- notifications (proactive alerts)
export function LiveNotifications() {
  return (
    <LiveList<BackendProactiveAlert>
      title="Notifications"
      subtitle="Deterministic alerts derived from your maintenance, compliance and telemetry data."
      breadcrumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Notifications" }]}
      load={proactiveApi.getAlerts}
      columns={[
        { header: "Alert", render: (a) => a.title },
        { header: "Severity", render: (a) => a.severity },
        { header: "Category", render: (a) => a.category },
        { header: "Detail", render: (a) => a.message },
      ]}
      emptyMessage="No active alerts."
      searchText={(a) => `${a.title} ${a.category} ${a.severity} ${a.message}`}
    />
  );
}

// ---------------------------------------------------------------- maintenance program (requirement register)
export function LiveMaintenanceProgram() {
  return (
    <LiveList<BackendMaintenanceRequirement>
      title="Maintenance Program"
      subtitle="Maintenance requirements and their intervals (flight hours, cycles, calendar)."
      breadcrumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Maintenance Program" }]}
      load={maintenanceRequirementsApi.list}
      columns={[
        { header: "Task reference", render: (r) => r.task_reference ?? r.id.slice(0, 8) },
        { header: "Description", render: (r) => r.description },
        { header: "ATA", render: (r) => r.ata_chapter },
        { header: "Interval basis", render: (r) => r.interval_type },
        { header: "FH", render: (r) => r.fh_interval ?? "—" },
        { header: "FC", render: (r) => r.fc_interval ?? "—" },
        { header: "Calendar (days)", render: (r) => r.calendar_interval_days ?? "—" },
      ]}
      emptyMessage="No maintenance requirements defined."
      searchText={(r) => `${r.task_reference ?? ""} ${r.description} ${r.ata_chapter}`}
    />
  );
}

// ---------------------------------------------------------------- components and engines (one register, two views)
function componentColumns(): { header: string; render: (c: FleetComponent) => React.ReactNode }[] {
  return [
    { header: "Name", render: (c) => c.name },
    { header: "Type", render: (c) => c.component_type },
    { header: "Serial number", render: (c) => c.serial_number ?? "—" },
    { header: "Installed on", render: (c) => c.asset_registration ?? "— (not installed)" },
    { header: "Status", render: (c) => c.status },
  ];
}

export function LiveComponentsList() {
  return (
    <LiveList<FleetComponent>
      title="Components"
      subtitle="Serialized components across your fleet."
      breadcrumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Components" }]}
      load={(t) => fleetComponentsApi.list(t, { limit: 200 })}
      columns={componentColumns()}
      rowHref={(c) => `/components/${c.id}`}
      emptyMessage="No components recorded."
      searchText={(c) => `${c.name} ${c.component_type} ${c.serial_number ?? ""} ${c.asset_registration ?? ""}`}
    />
  );
}

export function LiveComponentDetail() {
  return (
    <LiveDetail<FleetComponent>
      breadcrumbs={(c) => [{ label: "Dashboard", href: "/dashboard" }, { label: "Components", href: "/components" }, { label: c?.name ?? "…" }]}
      title={(c) => c.name}
      load={fleetComponentsApi.get}
      notFound="Component not found."
    />
  );
}

export function LiveEnginesList() {
  return (
    <LiveList<FleetComponent>
      title="Engines"
      subtitle="Engines installed across your fleet (components of type ENGINE)."
      breadcrumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Engines" }]}
      load={(t) => fleetComponentsApi.list(t, { component_type: "ENGINE", limit: 200 })}
      columns={componentColumns()}
      rowHref={(c) => `/engines/${c.id}`}
      emptyMessage="No engines recorded."
      searchText={(c) => `${c.name} ${c.serial_number ?? ""} ${c.asset_registration ?? ""} ${c.model ?? ""}`}
    />
  );
}

export function LiveEngineDetail() {
  return (
    <LiveDetail<FleetComponent>
      breadcrumbs={(c) => [{ label: "Dashboard", href: "/dashboard" }, { label: "Engines", href: "/engines" }, { label: c?.name ?? "…" }]}
      title={(c) => c.name}
      load={fleetComponentsApi.get}
      notFound="Engine not found."
    />
  );
}

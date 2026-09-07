import Link from "next/link";
import { notFound } from "next/navigation";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
import { getWorkOrderById, workOrdersForAircraft } from "@/lib/mock/workOrders";
import { getChecklistByWorkOrderId } from "@/lib/mock/checklists";
import {
  getWorkOrderCostSummary,
  getAircraftCostSummary,
  laborCostsForWorkOrder,
  partCostsForWorkOrder,
  vendorCostsForWorkOrder,
  customerChargeForWorkOrder,
  type CostCoverage,
} from "@/lib/mock/finance";
import { getTechnicianById } from "@/lib/mock/technicians";
import { getPartById } from "@/lib/mock/parts";
import { getOrganizationById } from "@/lib/mock/organizations";

// M10.5 — Financial drill-down. Accepts either a work order id ("wo-...")
// or an aircraft id ("ac-...") — the two real id shapes already used
// throughout this repository — rather than a second route for aircraft
// finance. Shows the full Aircraft -> Work Order -> Labor/Parts/Vendor ->
// Cost -> Customer Charge -> Margin chain and marks every missing link
// explicitly.

function coverageBadge(c: CostCoverage): { status: Parameters<typeof StatusBadge>[0]["status"]; label: string } {
  switch (c) {
    case "CALCULATED": return { status: "COMPLIANT", label: "Calculated" };
    case "PARTIAL": return { status: "REVIEW_REQUIRED", label: "Partial Data" };
    default: return { status: "INSUFFICIENT_DATA", label: "Insufficient Data" };
  }
}

function money(n: number | null, currency = "USD"): string {
  if (n === null) return "Insufficient source data.";
  return `${currency} ${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function AircraftFinanceDetail({ aircraftId }: { aircraftId: string }) {
  const aircraft = getAircraftById(aircraftId);
  if (!aircraft) notFound();
  const wos = workOrdersForAircraft(aircraftId);
  const summary = getAircraftCostSummary(aircraftId, wos.map((w) => w.id));
  if (!summary) notFound();
  const costedWos = wos.map((w) => getWorkOrderCostSummary(w.id)!).filter((s) => s.coverage !== "INSUFFICIENT_DATA");

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "MRO Financial Intelligence", href: "/finance" }, { label: summary.registration }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">{summary.registration} — Financial Detail</h1>
          <p className="ac-subtitle">{summary.workOrdersWithCostData} of {summary.totalWorkOrders} work orders on this aircraft have recorded cost data.</p>
        </div>
        <StatusBadge {...coverageBadge(summary.coverage)} />
      </div>

      <section className="ac-section">
        <div className="ac-kpi-grid">
          <div className="ac-kpi-card"><p className="ac-kpi-label">Total Cost</p><p className="ac-kpi-value">{money(summary.totalCost)}</p></div>
          <div className="ac-kpi-card"><p className="ac-kpi-label">Labor</p><p className="ac-kpi-value">{money(summary.laborCost)}</p></div>
          <div className="ac-kpi-card"><p className="ac-kpi-label">Parts</p><p className="ac-kpi-value">{money(summary.partsCost)}</p></div>
          <div className="ac-kpi-card"><p className="ac-kpi-label">Vendor</p><p className="ac-kpi-value">{money(summary.vendorCost)}</p></div>
          <div className="ac-kpi-card"><p className="ac-kpi-label">Customer Charge</p><p className="ac-kpi-value">{money(summary.customerCharge)}</p></div>
          <div className="ac-kpi-card"><p className="ac-kpi-label">Gross Margin</p><p className="ac-kpi-value">{money(summary.grossMargin)}</p></div>
        </div>
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Work Orders</h2>
        <div className="ac-card" style={{ padding: 0 }}>
          <table className="ac-table">
            <thead><tr><th>Work Order</th><th>Total Cost</th><th>Customer Charge</th><th>Status</th></tr></thead>
            <tbody>
              {costedWos.length === 0 && <tr><td colSpan={4} className="ac-text-sm ac-text-muted" style={{ textAlign: "center", padding: 16 }}>Insufficient source data.</td></tr>}
              {costedWos.map((s) => (
                <tr key={s.workOrderId}>
                  <td><Link href={`/finance/${s.workOrderId}`} className="ac-mono">{s.workOrderNumber}</Link></td>
                  <td>{money(s.totalCost)}</td>
                  <td>{money(s.customerCharge)}</td>
                  <td><StatusBadge {...coverageBadge(s.coverage)} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {wos.length > costedWos.length && (
          <p className="ac-text-sm ac-text-muted" style={{ marginTop: 6 }}>{wos.length - costedWos.length} other work order(s) on this aircraft have no cost data recorded.</p>
        )}
      </section>
    </div>
  );
}

function WorkOrderFinanceDetail({ workOrderId }: { workOrderId: string }) {
  const wo = getWorkOrderById(workOrderId);
  if (!wo) notFound();
  const summary = getWorkOrderCostSummary(workOrderId);
  if (!summary) notFound();
  const aircraft = getAircraftById(wo.aircraftId);
  const checklist = getChecklistByWorkOrderId(workOrderId);
  const labor = laborCostsForWorkOrder(workOrderId);
  const parts = partCostsForWorkOrder(workOrderId);
  const vendor = vendorCostsForWorkOrder(workOrderId);
  const charge = customerChargeForWorkOrder(workOrderId);
  const customerOrg = charge ? getOrganizationById(charge.customerOrgId) : undefined;

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "MRO Financial Intelligence", href: "/finance" }, { label: wo.workOrderNumber }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">{wo.workOrderNumber} — Where the Money Went</h1>
          <p className="ac-subtitle">{wo.title} · {aircraft ? <Link href={`/aircraft/${aircraft.id}`}>{currentRegistration(aircraft)}</Link> : "Insufficient source data."}</p>
        </div>
        <StatusBadge {...coverageBadge(summary.coverage)} />
      </div>

      {summary.coverage === "INSUFFICIENT_DATA" ? (
        <div className="ac-card"><p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Insufficient source data. No labor, parts, or vendor cost records exist for this work order.</p></div>
      ) : (
        <>
          <section className="ac-section">
            <div className="ac-kpi-grid">
              <div className="ac-kpi-card"><p className="ac-kpi-label">Labor</p><p className="ac-kpi-value">{money(summary.laborCost)}</p></div>
              <div className="ac-kpi-card"><p className="ac-kpi-label">Parts</p><p className="ac-kpi-value">{money(summary.partsCost)}</p></div>
              <div className="ac-kpi-card"><p className="ac-kpi-label">Vendor</p><p className="ac-kpi-value">{money(summary.vendorCost)}</p></div>
              <div className="ac-kpi-card"><p className="ac-kpi-label">Total Cost</p><p className="ac-kpi-value">{money(summary.totalCost)}</p></div>
              <div className="ac-kpi-card"><p className="ac-kpi-label">Customer Charge</p><p className="ac-kpi-value">{money(summary.customerCharge)}</p></div>
              <div className="ac-kpi-card">
                <p className="ac-kpi-label">Gross Margin</p>
                <p className="ac-kpi-value">{money(summary.grossMargin)}</p>
                {summary.marginPercent !== null && <p className="ac-text-sm ac-text-muted" style={{ margin: "4px 0 0" }}>{summary.marginPercent}% margin</p>}
              </div>
            </div>
          </section>

          <div className="ac-grid-2 ac-section">
            <section>
              <h2 className="ac-h2" style={{ marginBottom: 10 }}>Labor</h2>
              <div className="ac-card">
                {labor.length === 0 ? <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Insufficient source data.</p> : labor.map((l) => (
                  <p key={l.id} className="ac-text-sm" style={{ margin: "0 0 6px" }}>
                    {getTechnicianById(l.technicianId)?.name ?? l.technicianId}: {l.hours}h × {money(l.hourlyRate)}/hr = {money(l.amount)}
                  </p>
                ))}
              </div>
            </section>
            <section>
              <h2 className="ac-h2" style={{ marginBottom: 10 }}>Parts</h2>
              <div className="ac-card">
                {parts.length === 0 ? <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Insufficient source data.</p> : parts.map((p) => (
                  <p key={p.id} className="ac-text-sm" style={{ margin: "0 0 6px" }}>
                    <Link href={`/maintenance/parts/${p.partId}`} className="ac-mono">{getPartById(p.partId)?.partNumber ?? p.partId}</Link>: {p.quantity} × {money(p.unitCost)} = {money(p.amount)}
                  </p>
                ))}
              </div>
            </section>
          </div>

          <section className="ac-section">
            <h2 className="ac-h2" style={{ marginBottom: 10 }}>Vendor</h2>
            <div className="ac-card">
              {vendor.length === 0 ? <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Insufficient source data.</p> : vendor.map((v) => (
                <p key={v.id} className="ac-text-sm" style={{ margin: "0 0 6px" }}>{v.vendorName}: {v.description} — {money(v.amount)} ({v.date})</p>
              ))}
            </div>
          </section>

          <section className="ac-section">
            <h2 className="ac-h2" style={{ marginBottom: 10 }}>Customer Charge</h2>
            <div className="ac-card">
              {!charge ? (
                <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Insufficient source data. No customer charge record exists for this work order.</p>
              ) : (
                <>
                  <p className="ac-text-sm" style={{ margin: "0 0 4px" }}>Customer: {customerOrg?.name ?? "Insufficient source data."}</p>
                  <p className="ac-text-sm" style={{ margin: "0 0 4px" }}>Labor charge: {money(charge.laborCharge)} · Parts charge: {money(charge.partsCharge)} · Other: {money(charge.otherCharge)}</p>
                  <p className="ac-text-sm" style={{ margin: 0, fontWeight: 600 }}>Total charge: {money(charge.totalCharge)}</p>
                </>
              )}
            </div>
          </section>
        </>
      )}

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Traceability</h2>
        <div className="ac-card">
          <p className="ac-text-sm ac-text-secondary" style={{ margin: "0 0 6px" }}>
            Aircraft ({aircraft ? currentRegistration(aircraft) : "Insufficient source data."}) → Work Order ({wo.workOrderNumber}) → Tasks ({checklist ? checklist.title : "Insufficient source data."}) → Labor ({labor.length > 0 ? `${labor.length} record(s)` : "Insufficient source data."}) → Parts ({parts.length > 0 ? `${parts.length} record(s)` : "Insufficient source data."}) → Vendor ({vendor.length > 0 ? `${vendor.length} record(s)` : "Insufficient source data."}) → Cost ({money(summary.totalCost)}) → Customer Charge ({money(summary.customerCharge)}) → Margin ({summary.marginPercent !== null ? `${summary.marginPercent}%` : "Insufficient source data."}).
          </p>
          {summary.missing.length > 0 && (
            <ul style={{ margin: "6px 0 0", paddingLeft: 18, fontSize: 12, color: "var(--ac-status-review)" }}>
              {summary.missing.map((m, i) => <li key={i}>{m}</li>)}
            </ul>
          )}
        </div>
      </section>
    </div>
  );
}

export default function FinanceDetailPage({ params }: { params: { id: string } }) {
  if (params.id.startsWith("ac-")) return <AircraftFinanceDetail aircraftId={params.id} />;
  if (params.id.startsWith("wo-")) return <WorkOrderFinanceDetail workOrderId={params.id} />;
  notFound();
}

import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { aircraft, currentRegistration } from "@/lib/mock/aircraft";
import { workOrders, workOrdersForAircraft } from "@/lib/mock/workOrders";
import {
  getWorkOrderCostSummary,
  getAircraftCostSummary,
  getFleetFinancialSummary,
  workOrderIdsWithCostData,
  highestCostPartCost,
  highestVendorSpend,
  vendorCosts,
  type CostCoverage,
} from "@/lib/mock/finance";

// M10.3/M10.4 — MRO Financial Intelligence dashboard. Reuses the same page
// composition primitives (ac-kpi-grid, ac-card, plain <table>) as every
// other Server Component dashboard in the app (Executive, Compliance) — no
// new charting architecture. Cost data exists for only 3 of the fleet's 10
// work orders (see lib/mock/finance.ts); every section makes that coverage
// gap explicit rather than presenting a fabricated complete picture.

function coverageBadge(c: CostCoverage): { status: Parameters<typeof StatusBadge>[0]["status"]; label: string } {
  switch (c) {
    case "CALCULATED": return { status: "COMPLIANT", label: "Calculated" };
    case "PARTIAL": return { status: "REVIEW_REQUIRED", label: "Partial Data" };
    default: return { status: "INSUFFICIENT_DATA", label: "Insufficient Data" };
  }
}

function money(n: number | null, currency: string): string {
  if (n === null) return "Insufficient source data.";
  const formatted = n.toLocaleString(undefined, { maximumFractionDigits: 0 });
  return currency ? `${currency} ${formatted}` : formatted;
}

export default function FinancePage() {
  const allWoIds = workOrders.map((w) => w.id);
  const fleet = getFleetFinancialSummary(allWoIds);
  const woIdsWithData = workOrderIdsWithCostData();
  const summaries = woIdsWithData.map((id) => getWorkOrderCostSummary(id)!).filter(Boolean);

  // Section 2 — Cost by Aircraft
  const aircraftCosts = aircraft
    .map((a) => getAircraftCostSummary(a.id, workOrdersForAircraft(a.id).map((w) => w.id)))
    .filter((s) => s && s.coverage !== "INSUFFICIENT_DATA") as NonNullable<ReturnType<typeof getAircraftCostSummary>>[];
  const maxAircraftCost = Math.max(1, ...aircraftCosts.map((a) => a.totalCost));

  // Section 6 — Vendor Expenditure
  const vendorNames = Array.from(new Set(vendorCosts.map((v) => v.vendorName)));
  const vendorRollup = vendorNames.map((name) => {
    const rows = vendorCosts.filter((v) => v.vendorName === name);
    return { name, spend: rows.reduce((s, v) => s + v.amount, 0), orders: rows.length };
  });

  const topPart = highestCostPartCost();
  const topVendor = highestVendorSpend();
  const mostExpensiveWo = [...summaries].sort((a, b) => b.totalCost - a.totalCost)[0];
  const bestMarginWo = summaries.filter((s) => s.marginPercent !== null).sort((a, b) => (b.marginPercent ?? 0) - (a.marginPercent ?? 0))[0];

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "MRO Financial Intelligence" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">MRO Financial Intelligence</h1>
          <p className="ac-subtitle">
            Operational cost intelligence, not accounting software. {fleet.workOrdersWithCostData} of {fleet.totalWorkOrders} work orders have recorded cost data — the remainder show &ldquo;Insufficient source data.&rdquo;, never a fabricated $0.
          </p>
        </div>
        <StatusBadge {...coverageBadge(fleet.coverage)} />
      </div>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Financial Overview</h2>
        <div className="ac-kpi-grid">
          <div className="ac-kpi-card"><p className="ac-kpi-label">Total MRO Cost</p><p className="ac-kpi-value">{money(fleet.totalCost, "USD")}</p></div>
          <div className="ac-kpi-card"><p className="ac-kpi-label">Labor Cost</p><p className="ac-kpi-value">{money(fleet.laborCost, "USD")}</p></div>
          <div className="ac-kpi-card"><p className="ac-kpi-label">Parts Cost</p><p className="ac-kpi-value">{money(fleet.partsCost, "USD")}</p></div>
          <div className="ac-kpi-card"><p className="ac-kpi-label">Vendor Spend</p><p className="ac-kpi-value">{money(fleet.vendorCost, "USD")}</p></div>
          <div className="ac-kpi-card">
            <p className="ac-kpi-label">Customer Charges</p>
            <p className="ac-kpi-value">{money(fleet.customerCharge, "USD")}</p>
            <p className="ac-text-sm ac-text-muted" style={{ margin: "4px 0 0" }}>{fleet.workOrdersWithCharge} of {fleet.workOrdersWithCostData} costed work order(s) have a charge on file</p>
          </div>
          <div className="ac-kpi-card"><p className="ac-kpi-label">Gross Margin</p><p className="ac-kpi-value">{money(fleet.grossMargin, "USD")}</p></div>
        </div>
      </section>

      <div className="ac-grid-2 ac-section">
        <section>
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Section 2 — Cost by Aircraft</h2>
          <div className="ac-card">
            {aircraftCosts.length === 0 ? (
              <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Insufficient source data.</p>
            ) : (
              aircraftCosts.map((a) => (
                <Link key={a.aircraftId} href={`/finance/${a.aircraftId}`} style={{ display: "block", marginBottom: 12, textDecoration: "none", color: "inherit" }}>
                  <div className="ac-flex ac-justify-between ac-text-sm" style={{ marginBottom: 3 }}>
                    <span className="ac-mono">{a.registration}</span>
                    <span className="ac-text-muted">{money(a.totalCost, "USD")} · {a.workOrdersWithCostData}/{a.totalWorkOrders} WO costed</span>
                  </div>
                  <div style={{ width: "100%", height: 10, borderRadius: 4, background: "var(--ac-border)", overflow: "hidden" }}>
                    <div style={{ width: `${(a.totalCost / maxAircraftCost) * 100}%`, height: "100%", background: "var(--ac-accent)" }} />
                  </div>
                </Link>
              ))
            )}
          </div>
        </section>

        <section>
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Section 3 — Cost Composition</h2>
          <div className="ac-card">
            {fleet.totalCost === 0 ? (
              <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Insufficient source data.</p>
            ) : (
              <>
                {[
                  { label: "Labor", value: fleet.laborCost },
                  { label: "Parts", value: fleet.partsCost },
                  { label: "Vendor", value: fleet.vendorCost },
                ].map((c) => (
                  <div key={c.label} style={{ marginBottom: 8 }}>
                    <div className="ac-flex ac-justify-between ac-text-sm" style={{ marginBottom: 3 }}>
                      <span>{c.label}</span>
                      <span className="ac-text-muted">{money(c.value, "USD")} ({Math.round((c.value / fleet.totalCost) * 100)}%)</span>
                    </div>
                    <div style={{ width: "100%", height: 8, borderRadius: 4, background: "var(--ac-border)", overflow: "hidden" }}>
                      <div style={{ width: `${(c.value / fleet.totalCost) * 100}%`, height: "100%", background: "var(--ac-accent)" }} />
                    </div>
                  </div>
                ))}
                <p className="ac-text-sm ac-text-muted" style={{ margin: "8px 0 0" }}>&ldquo;Other&rdquo; cost category (tooling/consumables/subcontracting): Insufficient source data.</p>
              </>
            )}
          </div>
        </section>
      </div>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Section 4 — Cost by Work Order</h2>
        <div className="ac-card" style={{ padding: 0 }}>
          <table className="ac-table">
            <thead><tr><th>Work Order</th><th>Aircraft</th><th>Labor</th><th>Parts</th><th>Vendor</th><th>Total Cost</th><th>Customer Charge</th><th>Margin</th><th>Status</th></tr></thead>
            <tbody>
              {allWoIds.map((id) => {
                const s = getWorkOrderCostSummary(id)!;
                if (s.coverage === "INSUFFICIENT_DATA") return null;
                return (
                  <tr key={id}>
                    <td><Link href={`/finance/${id}`} className="ac-mono">{s.workOrderNumber}</Link></td>
                    <td className="ac-mono">{s.registration}</td>
                    <td>{money(s.laborCost, "")}</td>
                    <td>{money(s.partsCost, "")}</td>
                    <td>{money(s.vendorCost, "")}</td>
                    <td style={{ fontWeight: 600 }}>{money(s.totalCost, "USD")}</td>
                    <td>{money(s.customerCharge, "USD")}</td>
                    <td>{s.marginPercent !== null ? `${s.marginPercent}%` : "Insufficient source data."}</td>
                    <td><StatusBadge {...coverageBadge(s.coverage)} /></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="ac-text-sm ac-text-muted" style={{ padding: 12, margin: 0 }}>
            {allWoIds.length - woIdsWithData.length} of {allWoIds.length} work orders have no cost data recorded — not shown above rather than rendered as $0.
          </p>
        </div>
      </section>

      <div className="ac-grid-2 ac-section">
        <section>
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Section 5 — Estimated vs Actual</h2>
          <div className="ac-card">
            <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
              Insufficient source data. No estimated-cost field exists anywhere in the current work order domain model, so cost variance cannot be determined for any work order. This is a real data-model gap, not a calculation the system chose not to show.
            </p>
          </div>
        </section>

        <section>
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Section 6 — Vendor Expenditure</h2>
          <div className="ac-card" style={{ padding: 0 }}>
            {vendorRollup.length === 0 ? (
              <p className="ac-text-sm ac-text-muted" style={{ padding: 12 }}>Vendor expenditure data not yet available.</p>
            ) : (
              <table className="ac-table">
                <thead><tr><th>Vendor</th><th>Spend</th><th>Orders</th><th>Lead Time</th><th>Rating</th></tr></thead>
                <tbody>
                  {vendorRollup.map((v) => (
                    <tr key={v.name}>
                      <td>{v.name}</td>
                      <td>{money(v.spend, "USD")}</td>
                      <td>{v.orders}</td>
                      <td className="ac-text-sm ac-text-muted">Insufficient source data.</td>
                      <td className="ac-text-sm ac-text-muted">Insufficient source data.</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>
      </div>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Section 7 — Margin Intelligence</h2>
        <div className="ac-card">
          <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
            <li>Highest-cost work order: {mostExpensiveWo ? <Link href={`/finance/${mostExpensiveWo.workOrderId}`} className="ac-mono">{mostExpensiveWo.workOrderNumber}</Link> : "Insufficient source data."} {mostExpensiveWo && `(${money(mostExpensiveWo.totalCost, "USD")})`}</li>
            <li>Best-margin work order: {bestMarginWo ? <Link href={`/finance/${bestMarginWo.workOrderId}`} className="ac-mono">{bestMarginWo.workOrderNumber}</Link> : "Insufficient source data."} {bestMarginWo && `(${bestMarginWo.marginPercent}%)`}</li>
            <li>Highest-cost part: {topPart ? `${topPart.partId} — ${money(topPart.amount, "USD")}` : "Insufficient source data."}</li>
            <li>Highest vendor spend: {topVendor ? `${topVendor.vendorName} — ${money(topVendor.amount, "USD")}` : "Insufficient source data."}</li>
            <li>Largest overrun: Insufficient source data — no estimated cost exists to compare against.</li>
          </ul>
        </div>
      </section>

      <section className="ac-section">
        <div className="ac-card" style={{ borderStyle: "dashed" }}>
          <p className="ac-eyebrow" style={{ marginBottom: 6 }}>Traceability</p>
          <p className="ac-text-sm ac-text-secondary" style={{ margin: 0 }}>
            Aircraft → Work Order → Labor / Parts / Vendor → Cost → Customer Charge → Margin. Every figure above traces to a labeled DEMO_SEED record in lib/mock/finance.ts on a real, existing work order — nothing is invented. Ask{" "}
            <Link href="/ai" className="ac-mono">AeroComply AI</Link> a financial question, or generate the{" "}
            <Link href="/reports/financial-intelligence" className="ac-mono">Financial Intelligence report</Link>.
          </p>
        </div>
      </section>
    </div>
  );
}

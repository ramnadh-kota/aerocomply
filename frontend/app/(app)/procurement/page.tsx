"use client";

import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { PLATFORM_AI_NAME, PLATFORM_NAME } from "@/lib/brand";
import { getPartsAtRisk } from "@/lib/mock/ai/analytics";
import { vendors, partRequests, vendorPartAvailability, partsWithoutVendorAvailability } from "@/lib/mock/procurement";
import { vendorCosts } from "@/lib/mock/finance";
import { parts } from "@/lib/mock/parts";
import { getAircraftById, currentRegistration } from "@/lib/mock/aircraft";

// M11.9 (lightweight) — Procurement Control Tower. Links out to Vendor
// Intelligence and reuses M10's parts-at-risk/vendor-spend rather than
// re-deriving them. The full cart/approval/PO workflow (M11.3-M11.8) is a
// separate milestone — this page is the entry point + risk overview only.

export default function ProcurementControlTowerPage() {
  const partsAtRisk = getPartsAtRisk();
  const aogRequests = partRequests.filter((r) => r.priority === "AOG");
  const pending = partRequests.filter((r) => r.status === "SUBMITTED" || r.status === "UNDER_REVIEW");
  const noVendorParts = partsWithoutVendorAvailability(parts.map((p) => p.id));

  const vendorSpendMap = new Map<string, number>();
  for (const v of vendorCosts) vendorSpendMap.set(v.vendorName, (vendorSpendMap.get(v.vendorName) ?? 0) + v.amount);
  const openVendorSpend = Array.from(vendorSpendMap.values()).reduce((s, n) => s + n, 0);

  const certGaps = vendorPartAvailability.filter((a) => a.certificationStatus !== "VERIFIED");
  const vendorRiskCount = vendors.filter((v) => v.approvalStatus === "UNKNOWN" || v.approvalStatus === "PENDING" || v.approvalStatus === "SUSPENDED").length;

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Procurement Control Center" }]} />
      <div className="ac-section-header">
        <div>
          <p className="ac-eyebrow" style={{ marginBottom: 4 }}>{PLATFORM_NAME}</p>
          <h1 className="ac-h1">Procurement Control Center</h1>
          <p className="ac-subtitle">Part requests, vendor risk, and open procurement exposure — every figure traces to a real request, vendor, or cost record.</p>
        </div>
        <div className="ac-flex ac-gap-2">
          <Link href="/procurement/parts" className="ac-btn">Find Parts</Link>
          <Link href="/procurement/cart" className="ac-btn">Procurement Cart</Link>
          <Link href="/procurement/approvals" className="ac-btn">Submitted Requests</Link>
          <Link href="/procurement/purchase-orders" className="ac-btn">Purchase Orders</Link>
          <Link href="/procurement/vendors" className="ac-btn">Vendor Intelligence →</Link>
        </div>
      </div>

      <section className="ac-section">
        <div className="ac-kpi-grid">
          <div className="ac-kpi-card"><p className="ac-kpi-label">AOG Parts</p><p className="ac-kpi-value">{aogRequests.length}</p></div>
          <div className="ac-kpi-card"><p className="ac-kpi-label">Pending Approvals</p><p className="ac-kpi-value">{pending.length}</p></div>
          <div className="ac-kpi-card"><p className="ac-kpi-label">Open Requests</p><p className="ac-kpi-value">{partRequests.filter((r) => !["RECEIVED", "CLOSED", "REJECTED"].includes(r.status)).length}</p></div>
          <div className="ac-kpi-card"><p className="ac-kpi-label">Recorded Vendor Spend</p><p className="ac-kpi-value">{openVendorSpend > 0 ? `USD ${openVendorSpend.toLocaleString()}` : "Insufficient source data."}</p></div>
          <div className="ac-kpi-card"><p className="ac-kpi-label">Parts at Risk</p><p className="ac-kpi-value">{partsAtRisk.length}</p></div>
          <div className="ac-kpi-card"><p className="ac-kpi-label">Vendor Risk (Unapproved/Pending)</p><p className="ac-kpi-value">{vendorRiskCount} / {vendors.length}</p></div>
          <div className="ac-kpi-card"><p className="ac-kpi-label">Certification Gaps</p><p className="ac-kpi-value">{certGaps.length} of {vendorPartAvailability.length} line(s)</p></div>
          <div className="ac-kpi-card"><p className="ac-kpi-label">Parts w/o Vendor Data</p><p className="ac-kpi-value">{noVendorParts.length} of {parts.length}</p></div>
        </div>
      </section>

      <div className="ac-grid-2 ac-section">
        <section>
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Parts at Risk</h2>
          <div className="ac-card" style={{ padding: 0 }}>
            {partsAtRisk.length === 0 ? <p className="ac-text-sm ac-text-muted" style={{ padding: 12 }}>Insufficient source data.</p> : (
              <table className="ac-table">
                <thead><tr><th>Part</th><th>Status</th></tr></thead>
                <tbody>
                  {partsAtRisk.map((p) => (
                    <tr key={p.partNumber}><td><Link href="/maintenance/parts" className="ac-mono">{p.partNumber}</Link></td><td>{p.status.replace(/_/g, " ")}</td></tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>
        <section>
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Vendor Spend</h2>
          <div className="ac-card" style={{ padding: 0 }}>
            {vendorSpendMap.size === 0 ? <p className="ac-text-sm ac-text-muted" style={{ padding: 12 }}>Insufficient source data.</p> : (
              <table className="ac-table">
                <thead><tr><th>Vendor</th><th>Spend</th></tr></thead>
                <tbody>
                  {Array.from(vendorSpendMap.entries()).sort((a, b) => b[1] - a[1]).map(([name, amount]) => {
                    const v = vendors.find((vv) => vv.name === name);
                    return <tr key={name}><td>{v ? <Link href={`/procurement/vendors/${v.id}`} className="ac-mono">{name}</Link> : name}</td><td>USD {amount.toLocaleString()}</td></tr>;
                  })}
                </tbody>
              </table>
            )}
          </div>
        </section>
      </div>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Open Requests</h2>
        <div className="ac-card" style={{ padding: 0 }}>
          <table className="ac-table">
            <thead><tr><th>Request</th><th>Aircraft</th><th>Part</th><th>Priority</th><th>Vendor</th><th>Status</th></tr></thead>
            <tbody>
              {partRequests.map((r) => {
                const ac = getAircraftById(r.aircraftId);
                const vendor = r.preferredVendorId ? vendors.find((v) => v.id === r.preferredVendorId) : undefined;
                return (
                  <tr key={r.id}>
                    <td className="ac-mono">{r.id}</td>
                    <td>{ac ? <Link href={`/aircraft/${ac.id}`}>{currentRegistration(ac)}</Link> : "Insufficient source data."}</td>
                    <td className="ac-mono">{r.partNumber}</td>
                    <td><StatusBadge status={r.priority === "AOG" ? "NON_COMPLIANT" : r.priority === "HIGH" ? "REVIEW_REQUIRED" : "COMPLIANT"} label={r.priority} /></td>
                    <td>{vendor ? <Link href={`/procurement/vendors/${vendor.id}`}>{vendor.name}</Link> : "Insufficient source data."}</td>
                    <td>{r.status.replace(/_/g, " ")}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section className="ac-section">
        <div className="ac-card" style={{ borderStyle: "dashed" }}>
          <p className="ac-eyebrow" style={{ marginBottom: 6 }}>Recommended Actions</p>
          <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
            {aogRequests.length > 0 && <li>Prioritize {aogRequests.length} AOG-priority request(s) for immediate vendor selection.</li>}
            {noVendorParts.length > 0 && <li>{noVendorParts.length} part(s) have no vendor availability data at all — source vendor coverage before the next AOG event.</li>}
            {vendorRiskCount > 0 && <li>{vendorRiskCount} vendor(s) are Pending/Unknown approval status — review before selecting them for a live order.</li>}
            {aogRequests.length === 0 && noVendorParts.length === 0 && vendorRiskCount === 0 && <li>No procurement actions indicated by current source data.</li>}
          </ul>
        </div>
      </section>

      <section className="ac-section">
        <p className="ac-text-sm ac-text-muted">
          Ask <Link href="/ai" className="ac-mono">{PLATFORM_AI_NAME}</Link> a procurement question, generate the{" "}
          <Link href="/reports/procurement-intelligence" className="ac-mono">Procurement Intelligence report</Link>, or start the full workflow:{" "}
          <Link href="/procurement/parts" className="ac-mono">Search a part</Link> →{" "}
          <Link href="/procurement/cart" className="ac-mono">review your cart</Link> →{" "}
          <Link href="/procurement/approvals" className="ac-mono">management approval</Link> →{" "}
          <Link href="/procurement/purchase-orders" className="ac-mono">purchase order</Link>.
        </p>
      </section>
    </div>
  );
}

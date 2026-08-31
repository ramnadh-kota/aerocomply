"use client";

import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { PLATFORM_NAME } from "@/lib/brand";
import { getPartsAtRisk } from "@/lib/mock/ai/analytics";
import { getWorkOrderById } from "@/lib/mock/workOrders";
import { parts } from "@/lib/mock/parts";

// M12.3 (catch-up, built as part of M12.4) — Material Readiness. This is
// NOT a new material-calculation engine: it renders getPartsAtRisk() (the
// same function the Control Tower's "Material Shortages" KPI and the
// Planning table's "Material Blocked" rows use) and adds the missing
// traceability link back to the affected work order and forward to
// Procurement — closing the Aircraft → Work Order → Material →
// Procurement chain the milestone asked for, without a second calculation.

export default function MaterialReadinessPage() {
  const atRisk = getPartsAtRisk();
  const totalParts = parts.length;
  const readyParts = totalParts - atRisk.length;

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Maintenance", href: "/maintenance/planning" }, { label: "Material Readiness" }]} />
      <div className="ac-section-header">
        <div>
          <p className="ac-eyebrow" style={{ marginBottom: 4 }}>{PLATFORM_NAME}</p>
          <h1 className="ac-h1">Material Readiness</h1>
          <p className="ac-subtitle">
            Every part not currently IN_STOCK, and the work order it is blocking. Reuses the same part-availability data as the
            Control Tower and Work Order Planning Center — one calculation, shown in three places.
          </p>
        </div>
        <Link href="/maintenance/planning" className="ac-btn">Open Planning Center</Link>
      </div>

      <section className="ac-section">
        <div className="ac-kpi-grid">
          <div className="ac-kpi-card"><p className="ac-kpi-label">Total Parts Tracked</p><p className="ac-kpi-value">{totalParts}</p></div>
          <div className="ac-kpi-card"><p className="ac-kpi-label">Available (In Stock)</p><p className="ac-kpi-value">{readyParts}</p></div>
          <div className="ac-kpi-card"><p className="ac-kpi-label">Shortages</p><p className="ac-kpi-value">{atRisk.length}</p></div>
          <div className="ac-kpi-card"><p className="ac-kpi-label">Procurement Actions Required</p><p className="ac-kpi-value">{atRisk.filter((p) => p.workOrderId).length}</p></div>
        </div>
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Material Shortages</h2>
        <div className="ac-card" style={{ padding: 0 }}>
          {atRisk.length === 0 ? (
            <p className="ac-text-sm ac-text-muted" style={{ padding: 12 }}>No parts currently at risk.</p>
          ) : (
            <table className="ac-table">
              <thead><tr><th>Part</th><th>Description</th><th>Status</th><th>Affected Work Order</th><th>Actions</th></tr></thead>
              <tbody>
                {atRisk.map((p) => {
                  const wo = p.workOrderId ? getWorkOrderById(p.workOrderId) : undefined;
                  return (
                    <tr key={p.partNumber}>
                      <td className="ac-mono">{p.partNumber}</td>
                      <td className="ac-text-sm">{p.description}</td>
                      <td>{p.status.replace(/_/g, " ")}</td>
                      <td>{wo ? <Link href={`/maintenance/planning/${wo.id}`} className="ac-mono">{wo.workOrderNumber}</Link> : "Insufficient source data."}</td>
                      <td className="ac-flex ac-gap-2">
                        {wo && <Link href={`/maintenance/planning/${wo.id}`} className="ac-btn" style={{ padding: "2px 8px" }}>View Work Order</Link>}
                        <Link href={`/procurement/parts?part=${encodeURIComponent(p.partNumber)}`} className="ac-btn ac-btn-primary" style={{ padding: "2px 8px" }}>
                          Create Procurement Request
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </section>
    </div>
  );
}

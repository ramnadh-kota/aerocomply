"use client";

import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { purchaseOrders } from "@/lib/mock/procurement";
import { procurementRepository } from "@/lib/domain/repositories";

// M11.8 — Purchase Order list. Server Component; a PO can ONLY be created
// from an approved request (see /procurement/approvals/[id]) — no direct
// creation UI exists here, per Rule 4 (technicians cannot issue POs, and
// this page has no "New PO" button at all).

function poStatusBadge(status: string): { status: Parameters<typeof StatusBadge>[0]["status"]; label: string } {
  switch (status) {
    case "RECEIVED": return { status: "COMPLIANT", label: "Received" };
    case "PARTIALLY_RECEIVED": return { status: "REVIEW_REQUIRED", label: "Partially Received" };
    case "CANCELLED": return { status: "NON_COMPLIANT", label: "Cancelled" };
    case "SENT": case "ACKNOWLEDGED": return { status: "PENDING", label: status.replace(/_/g, " ") };
    default: return { status: "INSUFFICIENT_DATA", label: status.replace(/_/g, " ") };
  }
}

export default function PurchaseOrdersPage() {
  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Procurement", href: "/procurement" }, { label: "Purchase Orders" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Purchase Orders</h1>
          <p className="ac-subtitle">Generated only from approved procurement requests. {purchaseOrders.length} PO(s) exist this session.</p>
        </div>
      </div>

      <div className="ac-card" style={{ padding: 0 }}>
        {purchaseOrders.length === 0 ? (
          <p className="ac-text-sm ac-text-muted" style={{ padding: 12 }}>Insufficient source data. No purchase order has been generated yet — approve a procurement request first.</p>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="ac-table">
              <thead><tr><th>PO Number</th><th>Vendor</th><th>Total</th><th>Required By</th><th>Status</th></tr></thead>
              <tbody>
                {purchaseOrders.map((po) => {
                  const vendor = procurementRepository.getVendorById(po.vendorId);
                  return (
                    <tr key={po.id}>
                      <td><Link href={`/procurement/purchase-orders/${po.id}`} className="ac-mono">{po.poNumber}</Link></td>
                      <td>{vendor?.name ?? "Insufficient source data."}</td>
                      <td>{po.currency} {po.total.toLocaleString()}</td>
                      <td>{po.requiredBy ?? "Insufficient source data."}</td>
                      <td><StatusBadge {...poStatusBadge(po.status)} /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

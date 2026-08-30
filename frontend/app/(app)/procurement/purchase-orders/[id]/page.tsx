"use client";

import { useState } from "react";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { procurementRepository } from "@/lib/domain/repositories";
import { getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
import { getWorkOrderById } from "@/lib/mock/workOrders";
import { getCurrentUser } from "@/lib/domain/currentUser";
import { useMroState } from "@/lib/mro-state/MroStateContext";
import { getUserById } from "@/lib/mock/roles";
import { PLATFORM_NAME } from "@/lib/brand";

// M11.8 — Purchase Order detail: a professional aviation procurement
// document, plus the "Send Purchase Order" demo email preview and a
// receiving action. No real email is ever sent — clearly labeled as a
// demo outbound communication, per the brief. No fake certificate is
// created on receipt; receiving only transitions status.

function poStatusBadge(status: string): { status: Parameters<typeof StatusBadge>[0]["status"]; label: string } {
  switch (status) {
    case "RECEIVED": return { status: "COMPLIANT", label: "Received" };
    case "PARTIALLY_RECEIVED": return { status: "REVIEW_REQUIRED", label: "Partially Received" };
    case "CANCELLED": return { status: "NON_COMPLIANT", label: "Cancelled" };
    case "SENT": case "ACKNOWLEDGED": return { status: "PENDING", label: status.replace(/_/g, " ") };
    default: return { status: "INSUFFICIENT_DATA", label: status.replace(/_/g, " ") };
  }
}

export default function PurchaseOrderDetailPage({ params }: { params: { id: string } }) {
  const [version, setVersion] = useState(0);
  const [showEmailPreview, setShowEmailPreview] = useState(false);
  const { addAuditEvent } = useMroState();
  const current = getCurrentUser();
  void version;

  const po = procurementRepository.getPurchaseOrderById(params.id);
  if (!po) notFound();

  const vendor = procurementRepository.getVendorById(po.vendorId);
  const aircraft = po.aircraftId ? getAircraftById(po.aircraftId) : undefined;
  const wo = po.workOrderIds[0] ? getWorkOrderById(po.workOrderIds[0]) : undefined;
  const line = po.items[0] ? procurementRepository.availabilityForPart(po.items[0].requestId ? (procurementRepository.getPartRequestById(po.items[0].requestId)?.partId ?? "") : "").find((l) => l.vendorId === po.vendorId) : undefined;

  function send() {
    if (!current) return;
    procurementRepository.sendPurchaseOrder(po!.id);
    addAuditEvent({ actor: current.user.name, actorRole: current.role?.name ?? "Procurement", action: "procurement.po_sent", objectType: "PurchaseOrder", objectLabel: po!.poNumber, previousState: "DRAFT", newState: "SENT" });
    setShowEmailPreview(false);
    setVersion((v) => v + 1);
  }

  function receive() {
    if (!current) return;
    procurementRepository.receivePurchaseOrder(po!.id);
    addAuditEvent({ actor: current.user.name, actorRole: current.role?.name ?? "Receiving", action: "procurement.po_received", objectType: "PurchaseOrder", objectLabel: po!.poNumber, previousState: po!.status, newState: "RECEIVED" });
    setVersion((v) => v + 1);
  }

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Procurement", href: "/procurement" }, { label: "Purchase Orders", href: "/procurement/purchase-orders" }, { label: po.poNumber }]} />

      <div className="ac-card ac-section">
        <div className="ac-flex ac-justify-between ac-items-center" style={{ marginBottom: 16, flexWrap: "wrap" }}>
          <div>
            <p className="ac-eyebrow" style={{ marginBottom: 4 }}>{PLATFORM_NAME}</p>
            <h1 className="ac-h1" style={{ margin: 0 }}>PURCHASE ORDER</h1>
          </div>
          <StatusBadge {...poStatusBadge(po.status)} />
        </div>
        <div className="ac-grid-3" style={{ marginBottom: 16 }}>
          <div><p className="ac-kpi-label">PO Number</p><p style={{ fontWeight: 600, marginTop: 4 }} className="ac-mono">{po.poNumber}</p></div>
          <div><p className="ac-kpi-label">Vendor</p><p style={{ fontWeight: 600, marginTop: 4 }}>{vendor?.name ?? "Insufficient source data."}</p></div>
          <div><p className="ac-kpi-label">Issue Date</p><p style={{ fontWeight: 600, marginTop: 4 }}>{po.createdAt}</p></div>
        </div>

        <h2 className="ac-h2" style={{ marginBottom: 8 }}>Supplier Information</h2>
        <p className="ac-text-sm ac-text-muted" style={{ marginBottom: 16 }}>
          {vendor?.legalName ?? vendor?.name ?? "Insufficient source data."} · {vendor?.city ?? "Insufficient source data."}{vendor?.city && vendor?.country ? ", " : ""}{vendor?.country ?? ""} · {vendor?.contactName ?? "Insufficient source data."} · {vendor?.email ?? "Vendor email unavailable — insufficient source data."}
        </p>

        <h2 className="ac-h2" style={{ marginBottom: 8 }}>Order Items</h2>
        <div style={{ overflowX: "auto", marginBottom: 16 }}>
          <table className="ac-table">
            <thead><tr><th>Part Number</th><th>Description</th><th>Manufacturer</th><th>Qty</th><th>Unit Price</th><th>Total</th></tr></thead>
            <tbody>
              {po.items.map((item, i) => (
                <tr key={i}>
                  <td className="ac-mono">{item.partNumber}</td>
                  <td>{item.description}</td>
                  <td>{item.manufacturer ?? "Insufficient source data."}</td>
                  <td>{item.quantity}</td>
                  <td>{item.unitPrice !== null ? `${item.currency} ${item.unitPrice}` : "Insufficient source data."}</td>
                  <td>{item.unitPrice !== null ? `${item.currency} ${(item.unitPrice * item.quantity).toLocaleString()}` : "Insufficient source data."}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="ac-grid-2" style={{ marginBottom: 16 }}>
          <section>
            <h2 className="ac-h2" style={{ marginBottom: 8 }}>Delivery Information</h2>
            <p className="ac-text-sm" style={{ margin: "0 0 4px" }}>Aircraft: {aircraft ? <Link href={`/aircraft/${aircraft.id}`}>{currentRegistration(aircraft)}</Link> : "Insufficient source data."}</p>
            <p className="ac-text-sm" style={{ margin: "0 0 4px" }}>Work Order: {wo ? <Link href={`/maintenance/work-orders/${wo.id}`} className="ac-mono">{wo.workOrderNumber}</Link> : "Insufficient source data."}</p>
            <p className="ac-text-sm" style={{ margin: "0 0 4px" }}>Required By: {po.requiredBy ?? "Insufficient source data."}</p>
            <p className="ac-text-sm" style={{ margin: 0 }}>Expected Delivery: {po.expectedDelivery ?? "Insufficient source data."}</p>
          </section>
          <section>
            <h2 className="ac-h2" style={{ marginBottom: 8 }}>Compliance Information</h2>
            <p className="ac-text-sm" style={{ margin: "0 0 4px" }}>Certificate Requirement: {line?.certificationStatus === "VERIFIED" ? "On file (verified)" : "Certificate to be confirmed at receiving"}</p>
            <p className="ac-text-sm" style={{ margin: "0 0 4px" }}>Traceability Requirement: Full part traceability required per {PLATFORM_NAME} procurement policy (demo).</p>
            <p className="ac-text-sm" style={{ margin: 0 }}>Documentation: {vendor?.certifications?.join(", ") ?? "Insufficient source data."}</p>
          </section>
        </div>

        <h2 className="ac-h2" style={{ marginBottom: 8 }}>Financial Summary</h2>
        <div className="ac-kpi-grid" style={{ marginBottom: 8 }}>
          <div className="ac-kpi-card"><p className="ac-kpi-label">Subtotal</p><p className="ac-kpi-value" style={{ fontSize: 18 }}>{po.currency} {po.subtotal.toLocaleString()}</p></div>
          <div className="ac-kpi-card"><p className="ac-kpi-label">Tax</p><p className="ac-kpi-value" style={{ fontSize: 18 }}>{po.tax !== null ? `${po.currency} ${po.tax.toLocaleString()}` : "Insufficient source data."}</p></div>
          <div className="ac-kpi-card"><p className="ac-kpi-label">Shipping</p><p className="ac-kpi-value" style={{ fontSize: 18 }}>{po.shipping !== null ? `${po.currency} ${po.shipping.toLocaleString()}` : "Insufficient source data."}</p></div>
          <div className="ac-kpi-card"><p className="ac-kpi-label">Total</p><p className="ac-kpi-value" style={{ fontSize: 18 }}>{po.currency} {po.total.toLocaleString()}</p></div>
        </div>
        <p className="ac-text-sm ac-text-muted">Created by {getUserById(po.createdBy)?.name ?? po.createdBy} · Approved by {po.approvedBy ? (getUserById(po.approvedBy)?.name ?? po.approvedBy) : "Insufficient source data."}</p>
      </div>

      <section className="ac-section">
        <div className="ac-flex ac-gap-2">
          {po.status === "DRAFT" && <button className="ac-btn ac-btn-primary" onClick={() => setShowEmailPreview(true)}>Send Purchase Order</button>}
          {(po.status === "SENT" || po.status === "ACKNOWLEDGED") && <button className="ac-btn ac-btn-primary" onClick={receive}>Mark Received</button>}
        </div>
      </section>

      {showEmailPreview && (
        <section className="ac-section">
          <div className="ac-card" style={{ borderStyle: "dashed" }}>
            <p className="ac-eyebrow" style={{ marginBottom: 8, color: "var(--ac-status-review)" }}>Demo — Email Not Actually Sent</p>
            <p className="ac-text-sm" style={{ margin: "0 0 4px" }}><strong>To:</strong> {vendor?.email ?? "Vendor email unavailable — insufficient source data."}</p>
            <p className="ac-text-sm" style={{ margin: "0 0 4px" }}><strong>Subject:</strong> Purchase Order {po.poNumber} — {PLATFORM_NAME}</p>
            <div className="ac-card" style={{ background: "var(--ac-bg-surface-hover)", marginTop: 8 }}>
              <p className="ac-text-sm" style={{ margin: "0 0 8px" }}>Dear {vendor?.name ?? "Vendor"},</p>
              <p className="ac-text-sm" style={{ margin: "0 0 8px" }}>Please find Purchase Order {po.poNumber} for the following item(s):</p>
              <ul style={{ margin: "0 0 8px", paddingLeft: 18, fontSize: 13 }}>
                {po.items.map((item, i) => <li key={i}>{item.quantity} × {item.partNumber} — {item.description}</li>)}
              </ul>
              <p className="ac-text-sm" style={{ margin: "0 0 8px" }}>Requested delivery: {po.requiredBy ?? "Insufficient source data"}. Reference: {wo?.workOrderNumber ?? "Insufficient source data"}{aircraft ? ` / ${currentRegistration(aircraft)}` : ""}.</p>
              <p className="ac-text-sm" style={{ margin: "0 0 8px" }}>Please confirm availability, lead time, price, certification (FAA 8130-3 / EASA Form 1 or equivalent), and traceability documentation.</p>
              <p className="ac-text-sm" style={{ margin: 0 }}>Regards,<br />{PLATFORM_NAME} Procurement</p>
            </div>
            <div className="ac-flex ac-gap-2" style={{ marginTop: 10 }}>
              <button className="ac-btn ac-btn-primary" onClick={send}>Confirm — Queue Demo Email</button>
              <button className="ac-btn" onClick={() => setShowEmailPreview(false)}>Cancel</button>
            </div>
            {!vendor?.email && <p className="ac-text-sm ac-text-muted" style={{ marginTop: 6 }}>No vendor contact email is on file — this records the outbound PO action, but no address exists to actually deliver to. Insufficient source data.</p>}
          </div>
        </section>
      )}

      {po.status === "SENT" && !showEmailPreview && (
        <section className="ac-section">
          <div className="ac-card"><p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Demo outbound communication sent {po.sentAt}. No real email integration exists in this prototype.</p></div>
        </section>
      )}
    </div>
  );
}

"use client";

import { useState } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { procurementRepository } from "@/lib/domain/repositories";
import { getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
import { getWorkOrderById } from "@/lib/mock/workOrders";
import { getCurrentUser } from "@/lib/domain/currentUser";
import { useMroState } from "@/lib/mro-state/MroStateContext";

// M11.4 — Technician Procurement Cart. Reads/mutates the single in-memory
// cart in lib/mock/procurement.ts through procurementRepository only —
// never touches the mock array directly. A "version" counter forces
// re-render after each in-place mutation, the same pattern used by the
// M8.9 role editor.

export default function ProcurementCartPage() {
  const [version, setVersion] = useState(0);
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  const [submittedIds, setSubmittedIds] = useState<string[]>([]);
  const { addAuditEvent } = useMroState();
  void version;

  const cart = procurementRepository.getCart();
  const current = getCurrentUser();
  const summary = procurementRepository.cartSummary();

  function estimatedTotal(item: (typeof cart)[number]): number | null {
    return procurementRepository.cartItemLineTotal(item);
  }

  function remove(id: string) {
    procurementRepository.removeCartItem(id);
    addAuditEvent({ actor: current?.user.name ?? "Unknown User", actorRole: "Technician", action: "procurement.cart_item_removed", objectType: "ProcurementCartItem", objectLabel: id, previousState: "IN_CART", newState: null });
    setVersion((v) => v + 1);
  }

  function setQty(id: string, qty: number, previousQty: number) {
    const next = Math.max(1, qty);
    if (next === previousQty) return;
    procurementRepository.updateCartItemQuantity(id, next);
    addAuditEvent({ actor: current?.user.name ?? "Unknown User", actorRole: "Technician", action: "procurement.cart_updated", objectType: "ProcurementCartItem", objectLabel: id, previousState: `qty ${previousQty}`, newState: `qty ${next}` });
    setVersion((v) => v + 1);
  }

  function confirmSubmit(item: (typeof cart)[number]) {
    const total = estimatedTotal(item);
    const request = procurementRepository.submitPartRequest(item, total);
    procurementRepository.removeCartItem(item.id);
    addAuditEvent({
      actor: current?.user.name ?? "Unknown User",
      actorRole: "Technician",
      action: "procurement.request_submitted",
      objectType: "PartRequest",
      objectLabel: request.id,
      previousState: null,
      newState: "SUBMITTED",
      reason: request.reason,
    });
    setConfirmingId(null);
    setSubmittedIds((prev) => [...prev, request.id]);
    setVersion((v) => v + 1);
  }

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Procurement", href: "/procurement" }, { label: "My Cart" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">My Procurement Cart</h1>
          <p className="ac-subtitle">Review, adjust, and submit part requests for management approval.</p>
        </div>
        <Link href="/procurement/parts" className="ac-btn">+ Search Parts</Link>
      </div>

      {submittedIds.length > 0 && (
        <div className="ac-section">
          <div className="ac-card" style={{ borderColor: "var(--ac-status-compliant)" }}>
            <p className="ac-text-sm" style={{ margin: 0, fontWeight: 600, color: "var(--ac-status-compliant)" }}>
              Request{submittedIds.length > 1 ? "s" : ""} submitted: {submittedIds.join(", ")}. Status: SUBMITTED. Track it in{" "}
              <Link href="/procurement" className="ac-mono">Procurement Control Center</Link>.
            </p>
          </div>
        </div>
      )}

      {cart.length === 0 ? (
        <div className="ac-card"><p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Your cart is empty. <Link href="/procurement/parts">Search for a part</Link> to get started.</p></div>
      ) : (
        <>
          <div className="ac-card ac-section" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
            <div>
              <p className="ac-kpi-label">Estimated Procurement Total</p>
              <p className="ac-kpi-value">
                {summary.fullyCalculable ? `${summary.currency ?? ""} ${summary.knownTotal.toLocaleString()}` : summary.itemsWithKnownPrice > 0 ? "Partially calculable" : "Insufficient source data."}
              </p>
            </div>
            <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
              {summary.itemsWithKnownPrice} of {summary.itemCount} item{summary.itemCount === 1 ? "" : "s"} have known pricing.
              {!summary.fullyCalculable && summary.itemsWithKnownPrice > 0 && summary.currency === null && summary.knownTotal > 0 && " (mixed or unrecorded currency on some lines)"}
            </p>
          </div>
          <div className="ac-flex ac-flex-col ac-gap-3">
          {cart.map((item) => {
            const vendor = item.preferredVendorId ? procurementRepository.getVendorById(item.preferredVendorId) : undefined;
            const line = item.preferredVendorId ? procurementRepository.availabilityForPart(item.partId ?? "").find((l) => l.vendorId === item.preferredVendorId) : undefined;
            const aircraft = getAircraftById(item.aircraftId);
            const wo = item.workOrderId ? getWorkOrderById(item.workOrderId) : undefined;
            const total = estimatedTotal(item);
            return (
              <div key={item.id} className="ac-card">
                <div className="ac-flex ac-justify-between" style={{ flexWrap: "wrap", gap: 10 }}>
                  <div>
                    <p className="ac-mono" style={{ fontWeight: 700, margin: 0 }}>{item.partNumber} — {item.description}</p>
                    <p className="ac-text-sm ac-text-muted" style={{ margin: "4px 0 0" }}>
                      Vendor: {vendor?.name ?? "Insufficient source data."} · Aircraft: {aircraft ? currentRegistration(aircraft) : "Insufficient source data."} · Work Order: {wo?.workOrderNumber ?? "Insufficient source data."}
                    </p>
                    <p className="ac-text-sm ac-text-muted" style={{ margin: "4px 0 0" }}>Justification: {item.justification}</p>
                    <p className="ac-text-sm ac-text-muted" style={{ margin: "4px 0 0" }}>
                      Certification: {line ? line.certificationStatus.replace(/_/g, " ") : "Insufficient source data."} · Availability: {line ? line.availabilityStatus.replace(/_/g, " ") : "Insufficient source data."}
                    </p>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <StatusBadge status={item.priority === "AOG" ? "NON_COMPLIANT" : item.priority === "HIGH" ? "REVIEW_REQUIRED" : "COMPLIANT"} label={item.priority} />
                    <div className="ac-flex ac-items-center ac-gap-2" style={{ margin: "6px 0 4px", justifyContent: "flex-end" }}>
                      <span className="ac-text-sm ac-text-muted">Qty:</span>
                      <button className="ac-btn" style={{ padding: "2px 8px" }} aria-label={`Decrease quantity for ${item.partNumber}`} onClick={() => setQty(item.id, item.quantity - 1, item.quantity)} disabled={item.quantity <= 1}>−</button>
                      <span className="ac-mono" style={{ minWidth: 24, textAlign: "center", display: "inline-block" }}>{item.quantity}</span>
                      <button className="ac-btn" style={{ padding: "2px 8px" }} aria-label={`Increase quantity for ${item.partNumber}`} onClick={() => setQty(item.id, item.quantity + 1, item.quantity)}>+</button>
                    </div>
                    <p className="ac-text-sm" style={{ margin: "0 0 8px", fontWeight: 600 }}>Est. Total: {total !== null ? `${line?.currency ?? ""} ${total.toLocaleString()}` : "Insufficient source data."}</p>
                    <div className="ac-flex ac-gap-2" style={{ justifyContent: "flex-end" }}>
                      <button className="ac-btn" onClick={() => remove(item.id)}>Remove</button>
                      <button className="ac-btn ac-btn-primary" onClick={() => setConfirmingId(item.id)}>Submit Request</button>
                    </div>
                  </div>
                </div>

                {confirmingId === item.id && (
                  <div className="ac-card" style={{ marginTop: 12, background: "var(--ac-bg-surface-hover)" }}>
                    <p className="ac-eyebrow" style={{ marginBottom: 6 }}>Request Summary</p>
                    <ul style={{ margin: "0 0 10px", paddingLeft: 18, fontSize: 13 }}>
                      <li>Part: {item.partNumber} — {item.description}</li>
                      <li>Quantity: {item.quantity}</li>
                      <li>Vendor: {vendor?.name ?? "Insufficient source data."}</li>
                      <li>Aircraft: {aircraft ? currentRegistration(aircraft) : "Insufficient source data."}</li>
                      <li>Work Order: {wo?.workOrderNumber ?? "Insufficient source data."}</li>
                      <li>Estimated Cost: {total !== null ? `${line?.currency ?? ""} ${total.toLocaleString()}` : "Insufficient source data."}</li>
                      <li>Priority: {item.priority}</li>
                      <li>Justification: {item.justification}</li>
                    </ul>
                    <div className="ac-flex ac-gap-2">
                      <button className="ac-btn ac-btn-primary" onClick={() => confirmSubmit(item)}>Confirm &amp; Submit</button>
                      <button className="ac-btn" onClick={() => setConfirmingId(null)}>Cancel</button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
          </div>
        </>
      )}
    </div>
  );
}

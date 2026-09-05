"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { PLATFORM_NAME, PLATFORM_AI_NAME } from "@/lib/brand";
import {
  getMaterialReadinessRows,
  getMaterialReadinessSummary,
  getAircraftMaterialReadiness,
  type MaterialReadinessRow,
  type MaterialReadinessStatus,
} from "@/lib/mock/ai/analytics";
import { getControlTowerFleet } from "@/lib/mock/ai/analytics";
import { procurementRepository } from "@/lib/domain/repositories";
import { getCurrentUser } from "@/lib/domain/currentUser";
import { useMroState } from "@/lib/mro-state/MroStateContext";
import type { PartRequestPriority, Priority } from "@/lib/mock/types";

// M12.3 — Material Readiness & Procurement Planning. Every number here comes
// from getMaterialReadinessRows()/getMaterialReadinessSummary()
// (lib/mock/ai/analytics.ts), which in turn reuse the existing part status,
// vendor scoring (scoreVendorOptionsForPart — the same function the
// procurement/parts comparison page uses), and PartRequest/cart/PurchaseOrder
// records. "Add to Cart" calls procurementRepository.addCartItem — the same
// mutation the procurement/parts page uses. No second cart, no invented
// price/lead-time/quantity.

const STATUS_BADGE: Record<MaterialReadinessStatus, { status: Parameters<typeof StatusBadge>[0]["status"]; label: string }> = {
  READY: { status: "COMPLIANT", label: "Ready" },
  PARTIAL: { status: "REVIEW_REQUIRED", label: "Partial" },
  SHORTAGE: { status: "NON_COMPLIANT", label: "Shortage" },
  UNKNOWN: { status: "INSUFFICIENT_DATA", label: "Insufficient source data" },
};

/** WorkOrder.priority (LOW/MEDIUM/HIGH/CRITICAL) has no exact equivalent in
 * PartRequestPriority (ROUTINE/HIGH/AOG) — this is a stated, honest mapping,
 * not a fabricated priority. */
function toCartPriority(p: Priority): PartRequestPriority {
  if (p === "CRITICAL") return "AOG";
  if (p === "HIGH") return "HIGH";
  return "ROUTINE";
}

function AddToCartRow({ row, onAdded }: { row: MaterialReadinessRow; onAdded: () => void }) {
  const [open, setOpen] = useState(false);
  const [quantity, setQuantity] = useState(1);
  const [added, setAdded] = useState(false);
  const current = getCurrentUser();
  const { addAuditEvent } = useMroState();

  if (added) return <span className="ac-text-sm" style={{ color: "var(--ac-status-compliant)" }}>Added ✓</span>;

  if (!row.bestVendor) {
    return (
      <div>
        <p className="ac-text-sm" style={{ margin: 0, color: "var(--ac-status-non-compliant)" }}>Procurement data incomplete</p>
        <p className="ac-text-sm ac-text-muted" style={{ margin: "2px 0 0" }}>
          {row.hasVendorAvailability ? "No vendor currently shows a scoreable price/availability for this part." : "No vendor has a recorded availability line for this part."}
        </p>
      </div>
    );
  }

  if (!open) {
    return <button className="ac-btn ac-btn-primary" style={{ padding: "2px 8px" }} onClick={() => setOpen(true)}>Add to Procurement Cart</button>;
  }

  const justification = `Required to resolve open maintenance work order ${row.workOrderNumber}.`;

  return (
    <div className="ac-card" style={{ background: "var(--ac-bg-surface-hover)", padding: 10 }}>
      <p className="ac-text-sm" style={{ margin: "0 0 4px" }}>Aircraft: {row.aircraftRegistration}</p>
      <p className="ac-text-sm" style={{ margin: "0 0 4px" }}>Work Order: {row.workOrderNumber}</p>
      <p className="ac-text-sm" style={{ margin: "0 0 4px" }}>Part: {row.partNumber}</p>
      <p className="ac-text-sm" style={{ margin: "0 0 4px" }}>Vendor: {row.bestVendor.vendorName}</p>
      <p className="ac-text-sm" style={{ margin: "0 0 4px" }}>Priority: {toCartPriority(row.priority)}</p>
      <p className="ac-text-sm" style={{ margin: "0 0 6px" }}>Justification: {justification}</p>
      <div className="ac-flex ac-items-center ac-gap-2" style={{ marginBottom: 8 }}>
        <span className="ac-text-sm ac-text-muted">Qty:</span>
        <button className="ac-btn" style={{ padding: "2px 8px" }} onClick={() => setQuantity((q) => Math.max(1, q - 1))} disabled={quantity <= 1}>−</button>
        <span className="ac-mono">{quantity}</span>
        <button className="ac-btn" style={{ padding: "2px 8px" }} onClick={() => setQuantity((q) => q + 1)}>+</button>
      </div>
      <div className="ac-flex ac-gap-2">
        <button
          className="ac-btn ac-btn-primary"
          onClick={() => {
            if (!row.partId) return;
            procurementRepository.addCartItem({
              partNumber: row.partNumber,
              partId: row.partId,
              description: row.description,
              quantity,
              aircraftId: row.aircraftId,
              workOrderId: row.workOrderId,
              priority: toCartPriority(row.priority),
              justification,
              requestedBy: current?.user.name ?? "Unknown User",
              preferredVendorId: row.bestVendor!.vendorId,
              notes: null,
            });
            addAuditEvent({
              actor: current?.user.name ?? "Unknown User",
              actorRole: "Maintenance",
              action: "maintenance.material_procurement_linked",
              objectType: "ProcurementCartItem",
              objectLabel: `${row.partNumber} (${row.workOrderNumber})`,
              previousState: null,
              newState: "IN_CART",
              reason: justification,
            });
            setAdded(true);
            onAdded();
          }}
        >
          Confirm — Add to Cart
        </button>
        <button className="ac-btn" onClick={() => setOpen(false)}>Cancel</button>
      </div>
    </div>
  );
}

export default function MaterialReadinessPage() {
  const [, setVersion] = useState(0);
  const [openAircraftId, setOpenAircraftId] = useState<string | null>(null);
  const { addAuditEvent } = useMroState();
  const current = getCurrentUser();

  const rows = useMemo(() => getMaterialReadinessRows(), []);
  const summary = useMemo(() => getMaterialReadinessSummary(), []);
  const fleet = useMemo(() => getControlTowerFleet(), []);
  const aircraftWithMaterialActivity = fleet.filter((f) => rows.some((r) => r.aircraftId === f.aircraftId));

  function toggleAircraft(aircraftId: string) {
    const opening = openAircraftId !== aircraftId;
    setOpenAircraftId(opening ? aircraftId : null);
    if (opening) {
      const row = fleet.find((f) => f.aircraftId === aircraftId);
      addAuditEvent({
        actor: current?.user.name ?? "Unknown User",
        actorRole: "Maintenance",
        action: "maintenance.material_readiness_reviewed",
        objectType: "Aircraft",
        objectLabel: row?.registration ?? aircraftId,
        previousState: null,
        newState: null,
      });
    }
  }

  const kpis = [
    { label: "Work Orders Requiring Material", value: summary.workOrdersRequiringMaterial },
    { label: "Material Ready", value: summary.materialReady },
    { label: "Partial Readiness", value: summary.partialReadiness },
    { label: "Material Shortages", value: summary.materialShortages },
    { label: "Procurement Requests", value: summary.procurementRequests },
    { label: "Parts With Vendor Availability", value: summary.partsWithVendorAvailability },
    { label: "Parts With Unknown Availability", value: summary.partsWithUnknownAvailability },
  ];

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Maintenance", href: "/maintenance/control-tower" }, { label: "Material Readiness" }]} />
      <div className="ac-section-header">
        <div>
          <p className="ac-eyebrow" style={{ marginBottom: 4 }}>{PLATFORM_NAME}</p>
          <h1 className="ac-h1">Material Readiness</h1>
          <p className="ac-subtitle">Maintenance Material Planning &amp; Procurement — every row traces to a real work order, part, and (where known) vendor record.</p>
        </div>
        <Link href="/maintenance/planning" className="ac-btn">Open Planning Center</Link>
      </div>

      <section className="ac-section">
        <div className="ac-kpi-grid">
          {kpis.map((k) => (
            <div key={k.label} className="ac-kpi-card">
              <p className="ac-kpi-label">{k.label}</p>
              <p className="ac-kpi-value">{k.value}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Material Readiness by Work Order</h2>
        <div className="ac-card" style={{ padding: 0, overflowX: "auto" }}>
          <table className="ac-table">
            <thead>
              <tr>
                <th>Aircraft</th>
                <th>Work Order</th>
                <th>Part Number</th>
                <th>Description</th>
                <th>Material Status</th>
                <th>Vendor Availability</th>
                <th>Known Price</th>
                <th>Lead Time</th>
                <th>Procurement Status</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const badge = STATUS_BADGE[r.materialStatus];
                return (
                  <tr key={`${r.workOrderId}-${r.partNumber}`}>
                    <td><Link href={`/aircraft/${r.aircraftId}`}>{r.aircraftRegistration}</Link></td>
                    <td><Link href={`/maintenance/planning/${r.workOrderId}`} className="ac-mono">{r.workOrderNumber}</Link></td>
                    <td className="ac-mono">{r.partNumber}</td>
                    <td className="ac-text-sm">{r.description}</td>
                    <td><StatusBadge status={badge.status} label={badge.label} /></td>
                    <td className="ac-text-sm">{r.bestVendor ? `${r.bestVendor.vendorName} — ${r.bestVendor.availabilityStatus.replace(/_/g, " ")}` : "Insufficient source data."}</td>
                    <td>{r.bestVendor?.unitPrice != null ? `${r.bestVendor.currency ?? ""} ${r.bestVendor.unitPrice}` : "Insufficient source data."}</td>
                    <td>{r.bestVendor?.leadTimeDays != null ? `${r.bestVendor.leadTimeDays} days` : "Insufficient source data."}</td>
                    <td className="ac-text-sm">{r.procurementStatus}</td>
                    <td>
                      {r.materialStatus === "READY" ? (
                        <span className="ac-text-sm ac-text-muted">No action required.</span>
                      ) : (
                        <AddToCartRow row={r} onAdded={() => setVersion((v) => v + 1)} />
                      )}
                    </td>
                  </tr>
                );
              })}
              {rows.length === 0 && (
                <tr><td colSpan={10} className="ac-text-sm ac-text-muted" style={{ padding: 12 }}>No open work order currently requires material.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Recommended Procurement Actions</h2>
        <div className="ac-flex ac-flex-col ac-gap-3">
          {rows.filter((r) => r.materialStatus !== "READY").map((r) => (
            <div key={`${r.workOrderId}-${r.partNumber}-rec`} className="ac-card">
              <p className="ac-eyebrow" style={{ marginBottom: 4 }}>{r.partNumber} — {r.workOrderNumber} ({r.aircraftRegistration})</p>
              {r.recommendation ? (
                <>
                  <p className="ac-text-sm" style={{ margin: "0 0 4px", fontWeight: 600 }}>Recommended Vendor: {r.recommendation.vendorName}</p>
                  <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
                    {r.recommendation.reasons.map((reason) => <li key={reason}>✓ {reason}</li>)}
                  </ul>
                </>
              ) : (
                <>
                  <p className="ac-text-sm" style={{ margin: "0 0 4px", fontWeight: 600 }}>NO RECOMMENDATION</p>
                  <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Insufficient source data to determine the best procurement option.</p>
                </>
              )}
            </div>
          ))}
          {rows.filter((r) => r.materialStatus !== "READY").length === 0 && (
            <p className="ac-text-sm ac-text-muted">No procurement action currently required.</p>
          )}
        </div>
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Aircraft Drill-Down</h2>
        <div className="ac-flex ac-flex-col ac-gap-3">
          {aircraftWithMaterialActivity.map((f) => {
            const isOpen = openAircraftId === f.aircraftId;
            const aircraftRows = getAircraftMaterialReadiness(f.aircraftId);
            const blocking = aircraftRows.filter((r) => r.materialStatus !== "READY");
            return (
              <div key={f.aircraftId} className="ac-card">
                <div className="ac-flex ac-justify-between" style={{ flexWrap: "wrap", gap: 10 }}>
                  <div>
                    <p className="ac-mono" style={{ fontWeight: 700, margin: 0 }}>{f.registration}</p>
                    <p className="ac-text-sm ac-text-muted" style={{ margin: "4px 0 0" }}>
                      {f.openWorkOrders} open work order(s) · {blocking.length} material issue(s)
                    </p>
                  </div>
                  <button className="ac-btn" onClick={() => toggleAircraft(f.aircraftId)}>{isOpen ? "Close" : "Investigate"}</button>
                </div>
                {isOpen && (
                  <div className="ac-card" style={{ marginTop: 12, background: "var(--ac-bg-surface-hover)" }}>
                    <p className="ac-eyebrow" style={{ marginBottom: 6 }}>Required Parts &amp; Material Readiness</p>
                    <table className="ac-table" style={{ marginBottom: 12 }}>
                      <thead><tr><th>Work Order</th><th>Part</th><th>Status</th><th>Known Vendor</th><th>Procurement Status</th></tr></thead>
                      <tbody>
                        {aircraftRows.map((r) => (
                          <tr key={`${r.workOrderId}-${r.partNumber}-drill`}>
                            <td><Link href={`/maintenance/planning/${r.workOrderId}`} className="ac-mono">{r.workOrderNumber}</Link></td>
                            <td className="ac-mono">{r.partNumber}</td>
                            <td><StatusBadge {...STATUS_BADGE[r.materialStatus]} /></td>
                            <td className="ac-text-sm">{r.bestVendor?.vendorName ?? "Insufficient source data."}</td>
                            <td className="ac-text-sm">{r.procurementStatus}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    <p className="ac-eyebrow" style={{ marginBottom: 6 }}>Blocking Materials</p>
                    {blocking.length === 0 ? (
                      <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>No material is currently blocking work on this aircraft.</p>
                    ) : (
                      <ul style={{ margin: "0 0 8px", paddingLeft: 18, fontSize: 13 }}>
                        {blocking.map((r) => <li key={`${r.workOrderId}-${r.partNumber}-block`}>{r.partNumber} for {r.workOrderNumber} — {STATUS_BADGE[r.materialStatus].label}</li>)}
                      </ul>
                    )}
                    <p className="ac-text-sm" style={{ margin: 0, fontWeight: 600 }}>
                      Recommended next action: {blocking.length === 0 ? "None — material is ready for all open work on this aircraft." : `Review procurement recommendations above for ${blocking.map((b) => b.partNumber).join(", ")}.`}
                    </p>
                  </div>
                )}
              </div>
            );
          })}
          {aircraftWithMaterialActivity.length === 0 && <p className="ac-text-sm ac-text-muted">No aircraft currently has an open work order requiring material.</p>}
        </div>
      </section>

      <section className="ac-section">
        <p className="ac-text-sm ac-text-muted">
          Ask <Link href="/ai" className="ac-mono">{PLATFORM_AI_NAME}</Link> which shortage procurement should handle first, or open the{" "}
          <Link href="/procurement/cart" className="ac-mono">Procurement Cart</Link> to review items added from this page.
        </p>
      </section>
    </div>
  );
}

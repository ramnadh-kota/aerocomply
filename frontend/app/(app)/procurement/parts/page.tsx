"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { parts } from "@/lib/mock/parts";
import { workOrders } from "@/lib/mock/workOrders";
import { aircraft, getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
import { procurementRepository } from "@/lib/domain/repositories";
import { getCurrentUser } from "@/lib/domain/currentUser";
import { useMroState } from "@/lib/mro-state/MroStateContext";
import type { Part, PartRequestPriority } from "@/lib/mock/types";
import type { VendorScoreResult } from "@/lib/mock/procurement";

// M11.3 — Part / Vendor procurement comparison workspace. This is not a
// duplicate parts list (see /maintenance/parts) — it exists to answer "who
// should we buy this from, and why" using the ONE deterministic scoring
// function (scoreVendorOptionsForPart, in lib/mock/procurement.ts), also
// used by the AI engine's vendor-recommendation answers, so the two can
// never disagree.

function certBadge(status: string): { status: Parameters<typeof StatusBadge>[0]["status"]; label: string } {
  switch (status) {
    case "VERIFIED": return { status: "COMPLIANT", label: "Verified" };
    case "NOT_VERIFIED": return { status: "REVIEW_REQUIRED", label: "Not Verified" };
    case "REFERENCE_UNKNOWN": return { status: "INSUFFICIENT_DATA", label: "Reference Unknown" };
    default: return { status: "INSUFFICIENT_DATA", label: "Unknown" };
  }
}

function workOrdersRequiringPart(partId: string) {
  return workOrders.filter((w) => w.requiredPartIds.includes(partId) && w.status !== "COMPLETED" && w.status !== "CANCELLED");
}

function AddToCartForm({ part, vendorId, onAdded }: { part: Part; vendorId: string; onAdded: () => void }) {
  const candidateWos = workOrdersRequiringPart(part.id);
  const [workOrderId, setWorkOrderId] = useState(candidateWos[0]?.id ?? "");
  const [quantity, setQuantity] = useState(1);
  const [priority, setPriority] = useState<PartRequestPriority>("ROUTINE");
  const [justification, setJustification] = useState("");
  const { addAuditEvent } = useMroState();

  if (candidateWos.length === 0) {
    return <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Insufficient source data — no open work order currently requires this part, so a request cannot be tied to real maintenance context.</p>;
  }

  const wo = candidateWos.find((w) => w.id === workOrderId);
  const canSubmit = justification.trim().length > 0 && wo;

  return (
    <div className="ac-flex ac-flex-col ac-gap-2" style={{ marginTop: 8 }}>
      <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
        <label className="ac-flex ac-flex-col ac-gap-2">
          <span className="ac-text-sm ac-text-muted">Work Order</span>
          <select className="ac-input" style={{ width: 200 }} value={workOrderId} onChange={(e) => setWorkOrderId(e.target.value)}>
            {candidateWos.map((w) => <option key={w.id} value={w.id}>{w.workOrderNumber} — {w.title}</option>)}
          </select>
        </label>
        <label className="ac-flex ac-flex-col ac-gap-2">
          <span className="ac-text-sm ac-text-muted">Quantity</span>
          <input className="ac-input" style={{ width: 90 }} type="number" min={1} value={quantity} onChange={(e) => setQuantity(Math.max(1, Number(e.target.value)))} />
        </label>
        <label className="ac-flex ac-flex-col ac-gap-2">
          <span className="ac-text-sm ac-text-muted">Priority</span>
          <select className="ac-input" style={{ width: 140 }} value={priority} onChange={(e) => setPriority(e.target.value as PartRequestPriority)}>
            <option value="ROUTINE">Routine</option>
            <option value="HIGH">High</option>
            <option value="AOG">AOG</option>
          </select>
        </label>
      </div>
      <label className="ac-flex ac-flex-col ac-gap-2">
        <span className="ac-text-sm ac-text-muted">Why is this part required?</span>
        <input className="ac-input" value={justification} onChange={(e) => setJustification(e.target.value)} placeholder="e.g. Required to close open finding on this work order" />
      </label>
      <div>
        <button
          className="ac-btn ac-btn-primary"
          disabled={!canSubmit}
          onClick={() => {
            if (!wo) return;
            const current = getCurrentUser();
            procurementRepository.addCartItem({
              partNumber: part.partNumber,
              partId: part.id,
              description: part.description,
              quantity,
              aircraftId: wo.aircraftId,
              workOrderId: wo.id,
              priority,
              justification: justification.trim(),
              requestedBy: current?.user.id ?? "unknown",
              preferredVendorId: vendorId,
              notes: null,
            });
            addAuditEvent({
              actor: current?.user.name ?? "Unknown User",
              actorRole: "Technician",
              action: "procurement.cart_item_added",
              objectType: "ProcurementCartItem",
              objectLabel: `${part.partNumber} x${quantity}`,
              previousState: null,
              newState: "IN_CART",
            });
            onAdded();
          }}
        >
          Add to Cart
        </button>
      </div>
    </div>
  );
}

function BestOptionSummary({ scores }: { scores: VendorScoreResult[] }) {
  const top = scores.find((s) => s.score !== null);
  if (!top) {
    return (
      <div className="ac-card" style={{ marginBottom: 10, borderStyle: "dashed" }}>
        <p className="ac-eyebrow" style={{ marginBottom: 4 }}>Best Available Option</p>
        <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Unable to determine a best option from available source data.</p>
      </div>
    );
  }
  const cheapestKnown = scores.filter((s) => s.line.unitPrice !== null).sort((a, b) => (a.line.unitPrice ?? 0) - (b.line.unitPrice ?? 0))[0];
  const reasons: string[] = [];
  if (top.line.availabilityStatus === "IN_STOCK") reasons.push("Known availability (in stock)");
  if (top.line.unitPrice !== null) reasons.push("Known price");
  if (top.line.certificationStatus === "VERIFIED") reasons.push("Verified traceability/certification");
  if (cheapestKnown?.vendorId === top.vendorId) reasons.push("Lowest known cost among compared vendors");
  return (
    <div className="ac-card" style={{ marginBottom: 10, borderColor: "var(--ac-accent)" }}>
      <p className="ac-eyebrow" style={{ marginBottom: 4 }}>Best Available Option</p>
      <p className="ac-text-sm" style={{ margin: "0 0 4px", fontWeight: 600 }}>Vendor: {top.vendorName}</p>
      {reasons.length > 0 ? (
        <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
          {reasons.map((r) => <li key={r}>✓ {r}</li>)}
        </ul>
      ) : (
        <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Highest relative score, but few factors are actually confirmed — {top.missingFactors.join("; ")}.</p>
      )}
    </div>
  );
}

function VendorComparisonRow({ score, part }: { score: VendorScoreResult; part: Part }) {
  const [adding, setAdding] = useState(false);
  const [added, setAdded] = useState(false);

  return (
    <div className="ac-card" style={{ marginBottom: 10 }}>
      <div className="ac-flex ac-justify-between ac-items-center" style={{ flexWrap: "wrap", gap: 8 }}>
        <div>
          <Link href={`/procurement/vendors/${score.vendorId}`} className="ac-mono" style={{ fontWeight: 600 }}>{score.vendorName}</Link>
          <p className="ac-text-sm ac-text-muted" style={{ margin: "2px 0 0" }}>
            Availability: {score.line.availabilityStatus.replace(/_/g, " ")} · Price: {score.line.unitPrice !== null ? `${score.line.currency} ${score.line.unitPrice}` : "Insufficient source data."} · Lead time: {score.line.leadTimeDays !== null ? `${score.line.leadTimeDays}d` : "Insufficient source data."}
          </p>
        </div>
        <div className="ac-flex ac-items-center ac-gap-2">
          <StatusBadge {...certBadge(score.line.certificationStatus)} />
          <span className="ac-badge ac-badge-unknown">Score: {score.score !== null ? score.score : "N/A"}</span>
          {!added ? (
            <button className="ac-btn" onClick={() => setAdding((v) => !v)}>{adding ? "Cancel" : "Add to Cart"}</button>
          ) : (
            <span className="ac-text-sm" style={{ color: "var(--ac-status-compliant)" }}>Added ✓</span>
          )}
        </div>
      </div>
      {score.missingFactors.length > 0 && (
        <p className="ac-text-sm ac-text-muted" style={{ margin: "6px 0 0" }}>Missing: {score.missingFactors.join("; ")}.</p>
      )}
      {adding && !added && <AddToCartForm part={part} vendorId={score.vendorId} onAdded={() => { setAdded(true); setAdding(false); }} />}
    </div>
  );
}

export default function ProcurementPartsPage() {
  const [query, setQuery] = useState("");
  const [aircraftFilter, setAircraftFilter] = useState("ALL");
  const [availabilityFilter, setAvailabilityFilter] = useState("ALL");
  const [certFilter, setCertFilter] = useState("ALL");

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    return parts.filter((p) => {
      if (q && !(p.partNumber.toLowerCase().includes(q) || p.description.toLowerCase().includes(q) || (p.manufacturer ?? "").toLowerCase().includes(q))) return false;
      if (aircraftFilter !== "ALL" && !workOrdersRequiringPart(p.id).some((w) => w.aircraftId === aircraftFilter)) return false;
      const lines = procurementRepository.availabilityForPart(p.id);
      if (availabilityFilter !== "ALL" && !lines.some((l) => l.availabilityStatus === availabilityFilter)) return false;
      if (certFilter !== "ALL" && !lines.some((l) => l.certificationStatus === certFilter)) return false;
      return true;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, aircraftFilter, availabilityFilter, certFilter]);

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Procurement", href: "/procurement" }, { label: "Part Search & Comparison" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Part Search &amp; Vendor Comparison</h1>
          <p className="ac-subtitle">Search a part, compare vendor options against real availability/price/lead-time/certification data, and add the best option to your cart.</p>
        </div>
        <Link href="/procurement/cart" className="ac-btn">View Cart →</Link>
      </div>

      <div className="ac-card ac-section" style={{ padding: "var(--ac-space-4)" }}>
        <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
          <input className="ac-input" style={{ flex: "1 1 260px" }} placeholder="Search part number, description, or manufacturer…" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search parts" />
          <select className="ac-input" style={{ width: 180 }} value={aircraftFilter} onChange={(e) => setAircraftFilter(e.target.value)} aria-label="Filter by aircraft">
            <option value="ALL">All Aircraft</option>
            {aircraft.map((a) => <option key={a.id} value={a.id}>{currentRegistration(a)}</option>)}
          </select>
          <select className="ac-input" style={{ width: 190 }} value={availabilityFilter} onChange={(e) => setAvailabilityFilter(e.target.value)} aria-label="Filter by availability">
            <option value="ALL">All Availability</option>
            <option value="IN_STOCK">In Stock</option>
            <option value="LIMITED">Limited</option>
            <option value="ON_ORDER">On Order</option>
            <option value="OUT_OF_STOCK">Out of Stock</option>
            <option value="UNKNOWN">Unknown</option>
          </select>
          <select className="ac-input" style={{ width: 200 }} value={certFilter} onChange={(e) => setCertFilter(e.target.value)} aria-label="Filter by certification status">
            <option value="ALL">All Certification Statuses</option>
            <option value="VERIFIED">Verified</option>
            <option value="NOT_VERIFIED">Not Verified</option>
            <option value="REFERENCE_UNKNOWN">Reference Unknown</option>
            <option value="UNKNOWN">Unknown</option>
          </select>
        </div>
      </div>

      {matches.length === 0 && <div className="ac-card"><p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>No parts match this search.</p></div>}

      <div className="ac-flex ac-flex-col ac-gap-3">
        {matches.map((part) => {
          const scores = procurementRepository.scoreVendorsForPart(part.id);
          const candidateWos = workOrdersRequiringPart(part.id);
          return (
            <section key={part.id} className="ac-card">
              <div className="ac-flex ac-justify-between ac-items-center" style={{ marginBottom: 8, flexWrap: "wrap" }}>
                <div>
                  <p className="ac-mono" style={{ fontWeight: 700, fontSize: 15, margin: 0 }}>{part.partNumber}</p>
                  <p className="ac-text-sm ac-text-muted" style={{ margin: "2px 0 0" }}>{part.description} · {part.manufacturer ?? "Manufacturer: Insufficient source data."}</p>
                </div>
                <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
                  Required by: {candidateWos.length > 0 ? candidateWos.map((w) => {
                    const a = getAircraftById(w.aircraftId);
                    return `${w.workOrderNumber} (${a ? currentRegistration(a) : w.aircraftId})`;
                  }).join(", ") : "No open work order currently requires this part."}
                </p>
              </div>
              {scores.length === 0 ? (
                <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Insufficient source data. No vendor has a recorded availability line for this part.</p>
              ) : (
                <>
                  <BestOptionSummary scores={scores} />
                  {scores.map((s) => <VendorComparisonRow key={s.vendorId} score={s} part={part} />)}
                </>
              )}
            </section>
          );
        })}
      </div>
    </div>
  );
}

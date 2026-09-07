"use client";

import { useState } from "react";
import Link from "next/link";
import { notFound, useRouter } from "next/navigation";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { procurementRepository } from "@/lib/domain/repositories";
import { getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
import { getWorkOrderById } from "@/lib/mock/workOrders";
import { getUserById } from "@/lib/mock/roles";
import { getTechnicianById } from "@/lib/mock/technicians";
import { getWorkOrderCostSummary } from "@/lib/mock/finance";
import { getCurrentUser } from "@/lib/domain/currentUser";
import { useMroState } from "@/lib/mro-state/MroStateContext";
import { auditEventsForObjectLabelContains } from "@/lib/mock/audit";

function requesterName(id: string): string {
  return getTechnicianById(id)?.name ?? getUserById(id)?.name ?? id;
}

// M11.5 — Procurement request detail + management decision. Client
// Component (needs mutation buttons) — no DataTable here, so no
// Server/Client boundary risk.
export default function ProcurementRequestDetailPage({ params }: { params: { id: string } }) {
  const [version, setVersion] = useState(0);
  const [rejectReason, setRejectReason] = useState("");
  const [clarificationNote, setClarificationNote] = useState("");
  const [mode, setMode] = useState<"idle" | "rejecting" | "clarifying">("idle");
  const { addAuditEvent, auditLog } = useMroState();
  const current = getCurrentUser();
  const router = useRouter();
  const [poError, setPoError] = useState<string | null>(null);
  void version;

  const request = procurementRepository.getPartRequestById(params.id);
  if (!request) notFound();

  const aircraft = getAircraftById(request.aircraftId);
  const wo = request.workOrderId ? getWorkOrderById(request.workOrderId) : undefined;
  const scores = request.partId ? procurementRepository.scoreVendorsForPart(request.partId) : [];
  const chosen = scores.find((s) => s.vendorId === (request.selectedVendorId ?? request.preferredVendorId));
  const costSummary = request.workOrderId ? getWorkOrderCostSummary(request.workOrderId) : null;
  // Merge the static seed audit log with this session's live events (the
  // request/approval/rejection events created above land in the live
  // MroStateContext auditLog, not the static lib/mock/audit.ts array).
  const auditTrail = [
    ...auditEventsForObjectLabelContains(request.id),
    ...auditLog.filter((e) => e.objectLabel === request.id),
  ].sort((a, b) => b.timestamp.localeCompare(a.timestamp));

  function decide(action: "approve" | "reject" | "clarify") {
    if (!current) return;
    if (action === "approve") {
      procurementRepository.approvePartRequest(request!.id, current.user.id, request!.preferredVendorId);
      addAuditEvent({ actor: current.user.name, actorRole: current.role?.name ?? "Management", action: "procurement.request_approved", objectType: "PartRequest", objectLabel: request!.id, previousState: "SUBMITTED", newState: "APPROVED" });
    } else if (action === "reject") {
      if (!rejectReason.trim()) return;
      procurementRepository.rejectPartRequest(request!.id, current.user.id, rejectReason.trim());
      addAuditEvent({ actor: current.user.name, actorRole: current.role?.name ?? "Management", action: "procurement.request_rejected", objectType: "PartRequest", objectLabel: request!.id, previousState: "SUBMITTED", newState: "REJECTED", reason: rejectReason.trim() });
    } else {
      if (!clarificationNote.trim()) return;
      procurementRepository.returnPartRequest(request!.id, clarificationNote.trim());
      addAuditEvent({ actor: current.user.name, actorRole: current.role?.name ?? "Management", action: "procurement.clarification_requested", objectType: "PartRequest", objectLabel: request!.id, previousState: "SUBMITTED", newState: "CLARIFICATION_REQUIRED", reason: clarificationNote.trim() });
    }
    setMode("idle");
    setVersion((v) => v + 1);
  }

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Procurement", href: "/procurement" }, { label: "Approvals", href: "/procurement/approvals" }, { label: request.id }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">{request.id} — {request.partNumber}</h1>
          <p className="ac-subtitle">{request.description}</p>
        </div>
        <StatusBadge status={request.priority === "AOG" ? "NON_COMPLIANT" : request.priority === "HIGH" ? "REVIEW_REQUIRED" : "COMPLIANT"} label={`${request.priority} · ${request.status.replace(/_/g, " ")}`} />
      </div>

      <div className="ac-grid-2 ac-section">
        <section>
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>1–4. Request Summary</h2>
          <div className="ac-card">
            <p className="ac-text-sm" style={{ margin: "0 0 4px" }}>Aircraft: {aircraft ? <Link href={`/aircraft/${aircraft.id}`}>{currentRegistration(aircraft)}</Link> : "Insufficient source data."}</p>
            <p className="ac-text-sm" style={{ margin: "0 0 4px" }}>Work Order: {wo ? <Link href={`/maintenance/work-orders/${wo.id}`} className="ac-mono">{wo.workOrderNumber}</Link> : "Insufficient source data."}</p>
            <p className="ac-text-sm" style={{ margin: "0 0 4px" }}>Quantity: {request.quantity}</p>
            <p className="ac-text-sm" style={{ margin: 0 }}>Requested by: {requesterName(request.requestedBy)} on {request.requestedAt}</p>
          </div>
        </section>
        <section>
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>9. Technician Justification</h2>
          <div className="ac-card"><p className="ac-text-sm" style={{ margin: 0 }}>{request.reason}</p></div>
        </section>
      </div>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>5–8, 12. Vendor &amp; Cost</h2>
        <div className="ac-card" style={{ padding: 0 }}>
          {scores.length === 0 ? (
            <p className="ac-text-sm ac-text-muted" style={{ padding: 12 }}>Insufficient source data. No vendor availability recorded for this part.</p>
          ) : (
            <table className="ac-table">
              <thead><tr><th>Vendor</th><th>Score</th><th>Availability</th><th>Price</th><th>Lead Time</th><th>Certification</th></tr></thead>
              <tbody>
                {scores.map((s) => (
                  <tr key={s.vendorId} style={s.vendorId === chosen?.vendorId ? { fontWeight: 600 } : undefined}>
                    <td><Link href={`/procurement/vendors/${s.vendorId}`} className="ac-mono">{s.vendorName}</Link>{s.vendorId === chosen?.vendorId && " (selected)"}</td>
                    <td>{s.score ?? "N/A"}</td>
                    <td>{s.line.availabilityStatus.replace(/_/g, " ")}</td>
                    <td>{s.line.unitPrice !== null ? `${s.line.currency} ${s.line.unitPrice}` : "Insufficient source data."}</td>
                    <td>{s.line.leadTimeDays !== null ? `${s.line.leadTimeDays}d` : "Insufficient source data."}</td>
                    <td>{s.line.certificationStatus.replace(/_/g, " ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>11. Financial Impact</h2>
        <div className="ac-card">
          <p className="ac-text-sm" style={{ margin: "0 0 4px" }}>Estimated procurement cost: {request.estimatedCost !== null ? `USD ${request.estimatedCost.toLocaleString()}` : "Procurement cost unavailable."}</p>
          <p className="ac-text-sm" style={{ margin: "0 0 4px" }}>Current known customer charge: {costSummary?.customerCharge !== null && costSummary?.customerCharge !== undefined ? `USD ${costSummary.customerCharge.toLocaleString()}` : "Customer charge unavailable."}</p>
          <p className="ac-text-sm" style={{ margin: 0 }}>Estimated margin impact: {costSummary?.marginPercent !== null && costSummary?.marginPercent !== undefined ? `${costSummary.marginPercent}%` : "Margin cannot be determined."}</p>
        </div>
      </section>

      {(request.status === "SUBMITTED" || request.status === "UNDER_REVIEW") && (
        <section className="ac-section">
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Management Decision</h2>
          <div className="ac-card">
            {mode === "idle" && (
              <div className="ac-flex ac-gap-2">
                <button className="ac-btn ac-btn-primary" onClick={() => decide("approve")}>Approve</button>
                <button className="ac-btn" onClick={() => setMode("rejecting")}>Reject</button>
                <button className="ac-btn" onClick={() => setMode("clarifying")}>Return for Clarification</button>
              </div>
            )}
            {mode === "rejecting" && (
              <div className="ac-flex ac-flex-col ac-gap-2">
                <label className="ac-flex ac-flex-col ac-gap-2">
                  <span className="ac-text-sm ac-text-muted">Rejection reason (required)</span>
                  <input className="ac-input" value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} />
                </label>
                <div className="ac-flex ac-gap-2">
                  <button className="ac-btn ac-btn-primary" disabled={!rejectReason.trim()} onClick={() => decide("reject")}>Confirm Reject</button>
                  <button className="ac-btn" onClick={() => setMode("idle")}>Cancel</button>
                </div>
              </div>
            )}
            {mode === "clarifying" && (
              <div className="ac-flex ac-flex-col ac-gap-2">
                <label className="ac-flex ac-flex-col ac-gap-2">
                  <span className="ac-text-sm ac-text-muted">Clarification requested (required)</span>
                  <input className="ac-input" value={clarificationNote} onChange={(e) => setClarificationNote(e.target.value)} />
                </label>
                <div className="ac-flex ac-gap-2">
                  <button className="ac-btn ac-btn-primary" disabled={!clarificationNote.trim()} onClick={() => decide("clarify")}>Confirm Return</button>
                  <button className="ac-btn" onClick={() => setMode("idle")}>Cancel</button>
                </div>
              </div>
            )}
          </div>
        </section>
      )}

      {request.status === "APPROVED" && (
        <section className="ac-section">
          <div className="ac-card" style={{ borderColor: "var(--ac-status-compliant)" }}>
            <p className="ac-text-sm" style={{ margin: "0 0 8px" }}>Approved by {getUserById(request.approvedBy ?? "")?.name ?? request.approvedBy} on {request.approvedAt}.</p>
            <button
              className="ac-btn ac-btn-primary"
              onClick={() => {
                if (!current) return;
                const result = procurementRepository.createPurchaseOrder(request.id, current.user.id);
                if ("error" in result) { setPoError(result.error); return; }
                addAuditEvent({ actor: current.user.name, actorRole: current.role?.name ?? "Procurement", action: "procurement.po_generated", objectType: "PurchaseOrder", objectLabel: result.poNumber, previousState: null, newState: "DRAFT" });
                router.push(`/procurement/purchase-orders/${result.id}`);
              }}
            >
              Generate Purchase Order →
            </button>
            {poError && <p className="ac-text-sm" style={{ color: "var(--ac-status-non-compliant)", marginTop: 8 }}>{poError}</p>}
          </div>
        </section>
      )}
      {request.status === "REJECTED" && (
        <section className="ac-section"><div className="ac-card"><p className="ac-text-sm" style={{ margin: 0 }}>Rejected: {request.rejectionReason}</p></div></section>
      )}
      {request.status === "CLARIFICATION_REQUIRED" && (
        <section className="ac-section"><div className="ac-card"><p className="ac-text-sm" style={{ margin: 0 }}>Clarification requested: {request.clarificationNote}</p></div></section>
      )}

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>13. Audit Timeline</h2>
        <div className="ac-card">
          {auditTrail.length === 0 ? <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>No audit events reference this request yet.</p> : (
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
              {auditTrail.map((e) => <li key={e.id}>{e.timestamp}: {e.action.replace(/_/g, " ")} — {e.actor}</li>)}
            </ul>
          )}
        </div>
      </section>
    </div>
  );
}

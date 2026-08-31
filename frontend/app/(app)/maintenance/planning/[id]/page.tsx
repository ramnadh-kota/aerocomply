"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge, priorityBadge, workOrderStatusBadge, riskLevelBadge } from "@/components/status/StatusBadge";
import { PLATFORM_AI_NAME } from "@/lib/brand";
import { getWorkOrderPlanningRow, getTechnicianAssignmentRecommendation, requirementLabel } from "@/lib/mock/ai/analytics";
import { defectsForAircraft } from "@/lib/mock/defects";
import { technicians } from "@/lib/mock/technicians";
import { workOrderRepository } from "@/lib/domain/repositories";
import { getWorkOrderById } from "@/lib/mock/workOrders";
import { useMroState } from "@/lib/mro-state/MroStateContext";
import { getCurrentUser } from "@/lib/domain/currentUser";

// M12.4 — Work Order execution/planning view. Deliberately a separate route
// from the existing /maintenance/work-orders/[id] (checklist/inspection
// detail, untouched) — this page is planning-focused: material readiness,
// technician assignment, and the READY/BLOCKED derivation from
// getWorkOrderPlanningRow(), the same function the Planning table uses.

export default function WorkOrderPlanningDetailPage() {
  const params = useParams<{ id: string }>();
  const workOrderId = params.id;
  const [version, setVersion] = useState(0);
  const { addAuditEvent } = useMroState();
  const current = getCurrentUser();
  void version;

  const row = getWorkOrderPlanningRow(workOrderId);
  const wo = getWorkOrderById(workOrderId);
  const recommendation = getTechnicianAssignmentRecommendation(workOrderId);

  if (!row || !wo) {
    return (
      <div>
        <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Planning", href: "/maintenance/planning" }, { label: "Not Found" }]} />
        <div className="ac-card"><p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Work order not found.</p></div>
      </div>
    );
  }

  const defects = defectsForAircraft(wo.aircraftId).filter((d) => d.status === "OPEN");
  const priority = priorityBadge(row.priority);
  const statusBadge = workOrderStatusBadge(row.status);
  const risk = riskLevelBadge(row.risk);

  const assign = (technicianId: string) => {
    const updated = workOrderRepository.assignTechnician(workOrderId, technicianId);
    if (!updated) return;
    const tech = technicians.find((t) => t.id === technicianId);
    addAuditEvent({
      actor: current?.user.name ?? "Unknown User",
      actorRole: "Maintenance",
      action: "maintenance.technician_assigned",
      objectType: "WorkOrder",
      objectLabel: wo.workOrderNumber,
      previousState: row.assignedTechnicianName,
      newState: tech?.name ?? technicianId,
    });
    setVersion((v) => v + 1);
  };

  const start = () => {
    const updated = workOrderRepository.startWorkOrder(workOrderId);
    if (!updated) return;
    addAuditEvent({
      actor: current?.user.name ?? "Unknown User",
      actorRole: "Maintenance",
      action: "maintenance.work_started",
      objectType: "WorkOrder",
      objectLabel: wo.workOrderNumber,
      previousState: row.status,
      newState: "IN_PROGRESS",
    });
    setVersion((v) => v + 1);
  };

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Planning", href: "/maintenance/planning" }, { label: row.workOrderNumber }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">{row.workOrderNumber} — {row.title}</h1>
          <p className="ac-subtitle">
            Aircraft <Link href={`/aircraft/${row.aircraftId}`}>{row.aircraftRegistration}</Link> · Due {row.dueDate}
            {row.daysOverdue !== null && <span style={{ color: "var(--ac-status-non_compliant)" }}> · {row.daysOverdue}d overdue</span>}
          </p>
        </div>
        <div className="ac-flex ac-gap-2">
          <StatusBadge status={priority.status} label={priority.label} />
          <StatusBadge status={statusBadge.status} label={statusBadge.label} />
        </div>
      </div>

      <section className="ac-section">
        <div className="ac-card" style={{ borderColor: risk.status === "NON_COMPLIANT" ? "var(--ac-status-non_compliant)" : undefined }}>
          <p className="ac-eyebrow" style={{ marginBottom: 6 }}>Planning Status: {row.planningStatus.replace(/_/g, " ")} · Risk: {row.risk}</p>
          <ul style={{ margin: "0 0 10px", paddingLeft: 18, fontSize: 13 }}>
            {row.riskReasons.map((r) => <li key={r}>→ {r}</li>)}
          </ul>
          <p className="ac-text-sm" style={{ margin: 0, fontWeight: 600 }}>{row.recommendedAction}</p>
        </div>
      </section>

      <div className="ac-grid-2 ac-section">
        <section>
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Maintenance Impact</h2>
          <div className="ac-card">
            <p className="ac-text-sm" style={{ margin: "0 0 6px" }}>Aircraft AOG: {row.aogAircraft ? "Yes (open HIGH/CRITICAL defect)" : "No"}</p>
            <p className="ac-text-sm" style={{ margin: "0 0 6px" }}>Open defects on this aircraft: {defects.length}</p>
            {defects.length > 0 && (
              <ul style={{ margin: "0 0 6px", paddingLeft: 18, fontSize: 13 }}>
                {defects.map((d) => <li key={d.id}>{d.description} ({d.severity})</li>)}
              </ul>
            )}
            <p className="ac-text-sm" style={{ margin: "0 0 6px" }}>Material shortages: {row.shortParts.length > 0 ? row.shortParts.map((p) => p.partNumber).join(", ") : "None"}</p>
            <p className="ac-text-sm" style={{ margin: 0 }}>
              Compliance: {wo.relatedRequirementId ? requirementLabel(wo.relatedRequirementId) : "No linked regulatory requirement."}
            </p>
          </div>
        </section>

        <section>
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Materials</h2>
          <div className="ac-card" style={{ padding: 0 }}>
            {row.shortParts.length === 0 ? (
              <p className="ac-text-sm ac-text-muted" style={{ padding: 12 }}>No material shortage recorded for this work order.</p>
            ) : (
              <table className="ac-table">
                <thead><tr><th>Part</th><th>Description</th><th>Status</th><th>Quantity</th></tr></thead>
                <tbody>
                  {row.shortParts.map((p) => (
                    <tr key={p.partNumber}>
                      <td className="ac-mono">{p.partNumber}</td>
                      <td className="ac-text-sm">{p.description}</td>
                      <td>{p.status.replace(/_/g, " ")}</td>
                      <td>{p.quantity}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {row.shortParts.length > 0 && (
              <div className="ac-flex ac-gap-2" style={{ padding: 12, borderTop: "1px solid var(--ac-border)" }}>
                <Link href="/maintenance/material-readiness" className="ac-btn">View Material Impact</Link>
                <Link href={`/procurement/parts?part=${encodeURIComponent(row.shortParts[0].partNumber)}`} className="ac-btn ac-btn-primary">
                  Create Procurement Request
                </Link>
              </div>
            )}
          </div>
        </section>
      </div>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Technician</h2>
        <div className="ac-card">
          <p className="ac-text-sm" style={{ margin: "0 0 6px" }}>
            Assigned: {row.assignedTechnicianName ?? <span className="ac-text-muted">Unassigned</span>}
          </p>
          {!row.assignedTechnicianId && (
            <>
              {recommendation ? (
                <div style={{ marginTop: 8 }}>
                  <p className="ac-eyebrow" style={{ marginBottom: 6 }}>{PLATFORM_AI_NAME}&apos;s Recommendation: {recommendation.name}</p>
                  <ul style={{ margin: "0 0 10px", paddingLeft: 18, fontSize: 13 }}>
                    {recommendation.reasons.map((r) => <li key={r}>✓ {r}</li>)}
                  </ul>
                  <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 10px" }}>
                    Certification matching is based on keyword overlap between technician certifications and the work order title — this
                    dataset does not record an explicit required-certification field, so this is not verified skill certification.
                  </p>
                  <button className="ac-btn ac-btn-primary" onClick={() => assign(recommendation.technicianId)}>
                    Assign {recommendation.name}
                  </button>
                </div>
              ) : (
                <p className="ac-text-sm ac-text-muted" style={{ margin: "8px 0" }}>Insufficient source data to recommend a technician.</p>
              )}
              <div className="ac-flex ac-gap-2" style={{ marginTop: 10, flexWrap: "wrap" }}>
                {technicians.map((t) => (
                  <button key={t.id} className="ac-btn" style={{ padding: "4px 10px" }} onClick={() => assign(t.id)}>
                    Assign {t.name}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      </section>

      <section className="ac-section">
        <div className="ac-flex ac-gap-2">
          {row.planningStatus === "READY" && (
            <button className="ac-btn ac-btn-primary" onClick={start}>Start Work</button>
          )}
          <Link href={`/maintenance/work-orders/${wo.id}`} className="ac-btn">View Full Work Order</Link>
          <Link href={`/aircraft/${wo.aircraftId}`} className="ac-btn">View Aircraft</Link>
        </div>
      </section>
    </div>
  );
}

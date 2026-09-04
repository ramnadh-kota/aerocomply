"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge, priorityBadge, workOrderStatusBadge, riskLevelBadge } from "@/components/status/StatusBadge";
import { PLATFORM_AI_NAME } from "@/lib/brand";
import { getWorkOrderPlanningRow, getTechnicianAssignmentRecommendation, getTechnicianEligibilityForWorkOrder, requirementLabel, getExecutionState, getSafetyGatesForWorkOrder, getMaintenanceTaskChain, getMaintenanceTaskExecutionView, explainExecutionState, getReleaseReadinessForWorkOrder, getExecutionEvidenceStatus, getTechnicianAuthorizationMatrix } from "@/lib/mock/ai/analytics";
import { defectsForAircraft } from "@/lib/mock/defects";
import { technicians } from "@/lib/mock/technicians";
import { workOrderRepository } from "@/lib/domain/repositories";
import { getWorkOrderById } from "@/lib/mock/workOrders";
import { combinedAuditHistory } from "@/lib/mock/audit";
import { ActionHistory } from "@/components/audit/ActionHistory";
import { useMroState } from "@/lib/mro-state/MroStateContext";
import { getCurrentUser } from "@/lib/domain/currentUser";
import { evidenceRecordsForWorkOrder, addEvidenceRecord, removeEvidenceRecord, reviewEvidenceRecord } from "@/lib/mock/evidenceRecords";
import type { EvidenceRecordType } from "@/lib/mock/types";

const EVIDENCE_TYPES: EvidenceRecordType[] = ["BEFORE", "DAMAGE", "INSPECTION", "REMOVAL", "INSTALLATION", "AFTER", "COMPLETION", "OTHER"];
// M28 — the representative technician identity, same convention already
// used by /workspace (no real per-user login in this prototype).
const REPRESENTATIVE_TECHNICIAN_ID = "tech-1";

// M12.4 — Work Order execution/planning view. Deliberately a separate route
// from the existing /maintenance/work-orders/[id] (checklist/inspection
// detail, untouched) — this page is planning-focused: material readiness,
// technician assignment, and the READY/BLOCKED derivation from
// getWorkOrderPlanningRow(), the same function the Planning table uses.

export default function WorkOrderPlanningDetailPage() {
  const params = useParams<{ id: string }>();
  const workOrderId = params.id;
  const [version, setVersion] = useState(0);
  const { addAuditEvent, auditLog } = useMroState();
  const current = getCurrentUser();
  void version;

  const row = getWorkOrderPlanningRow(workOrderId);
  const wo = getWorkOrderById(workOrderId);
  const recommendation = getTechnicianAssignmentRecommendation(workOrderId);
  const eligibility = getTechnicianEligibilityForWorkOrder(workOrderId);
  const [showReassign, setShowReassign] = useState(false);

  // M28 — evidence capture form state.
  const [evidenceType, setEvidenceType] = useState<EvidenceRecordType>("BEFORE");
  const [evidenceNote, setEvidenceNote] = useState("");
  const [evidenceFile, setEvidenceFile] = useState<File | null>(null);
  const [evidencePreviewUrl, setEvidencePreviewUrl] = useState<string | null>(null);
  const [evidenceError, setEvidenceError] = useState<string | null>(null);
  // M28-Phase1 — reviewer state: which record's reject-reason box is open,
  // and its draft text. The representative reviewer identity mirrors the
  // same no-real-login convention as REPRESENTATIVE_TECHNICIAN_ID.
  const [rejectingId, setRejectingId] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const REPRESENTATIVE_REVIEWER_ID = "tech-3";

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
  const executionState = getExecutionState(wo);
  const safetyGates = getSafetyGatesForWorkOrder(workOrderId);
  const taskChain = getMaintenanceTaskChain(workOrderId);
  const taskExecution = getMaintenanceTaskExecutionView(workOrderId);
  const releaseReadiness = getReleaseReadinessForWorkOrder(workOrderId);
  const evidenceRecords = evidenceRecordsForWorkOrder(workOrderId);
  const evidenceStatus = getExecutionEvidenceStatus(workOrderId);
  const evidenceBlocksCompletion = evidenceStatus?.state === "FAIL";
  const authorizationMatrix = getTechnicianAuthorizationMatrix(workOrderId);

  const onEvidenceFileChange = (file: File | null) => {
    setEvidenceError(null);
    if (evidencePreviewUrl) URL.revokeObjectURL(evidencePreviewUrl);
    if (!file) {
      setEvidenceFile(null);
      setEvidencePreviewUrl(null);
      return;
    }
    if (!file.type.startsWith("image/")) {
      setEvidenceError("Only image files are accepted.");
      setEvidenceFile(null);
      setEvidencePreviewUrl(null);
      return;
    }
    if (file.size > 15 * 1024 * 1024) {
      setEvidenceError("Image is larger than 15 MB — choose a smaller file.");
      setEvidenceFile(null);
      setEvidencePreviewUrl(null);
      return;
    }
    setEvidenceFile(file);
    setEvidencePreviewUrl(URL.createObjectURL(file));
  };

  const cancelEvidence = () => {
    if (evidencePreviewUrl) URL.revokeObjectURL(evidencePreviewUrl);
    setEvidenceFile(null);
    setEvidencePreviewUrl(null);
    setEvidenceNote("");
    setEvidenceError(null);
  };

  const submitEvidence = () => {
    if (!evidenceFile || !evidencePreviewUrl) {
      setEvidenceError("Choose an image before submitting.");
      return;
    }
    const record = addEvidenceRecord({
      workOrderId,
      maintenanceTaskId: wo.maintenanceTaskId ?? null,
      aircraftId: wo.aircraftId,
      uploadedByTechnicianId: REPRESENTATIVE_TECHNICIAN_ID,
      evidenceType,
      fileRef: evidencePreviewUrl,
      fileName: evidenceFile.name,
      technicianNote: evidenceNote.trim() || null,
    });
    addAuditEvent({
      actor: current?.user.name ?? "Unknown User",
      actorRole: "Technician",
      action: "maintenance.evidence_uploaded",
      objectType: "EvidenceRecord",
      // Matches wo.workOrderNumber exactly (not a compound label) so this
      // event surfaces in the same combinedAuditHistory(row.workOrderNumber, ...)
      // lookup every other WO-scoped audit event on this page already uses.
      objectLabel: wo.workOrderNumber,
      previousState: null,
      newState: evidenceType,
      reason: `Evidence ${record.id} (${evidenceType}) uploaded${evidenceNote.trim() ? `: ${evidenceNote.trim()}` : "."}`,
    });
    setEvidenceFile(null);
    setEvidencePreviewUrl(null);
    setEvidenceNote("");
    setEvidenceType("BEFORE");
    setVersion((v) => v + 1);
  };

  const removeEvidence = (id: string) => {
    const removed = removeEvidenceRecord(id);
    if (!removed) return;
    addAuditEvent({
      actor: current?.user.name ?? "Unknown User",
      actorRole: "Technician",
      action: "maintenance.evidence_removed",
      objectType: "EvidenceRecord",
      objectLabel: wo.workOrderNumber,
      previousState: "SUBMITTED",
      newState: null,
      reason: `Evidence ${id} removed by uploader before review.`,
    });
    setVersion((v) => v + 1);
  };

  // M28-Phase1 — reviewer accept/reject. Uses the existing reviewEvidenceRecord
  // mutation (M28), which itself refuses a REJECTED status with no reason —
  // this UI enforces the same rule so a reviewer can't bypass it by leaving
  // the box empty.
  const acceptEvidence = (id: string) => {
    const reviewer = technicians.find((t) => t.id === REPRESENTATIVE_REVIEWER_ID);
    const updated = reviewEvidenceRecord(id, REPRESENTATIVE_REVIEWER_ID, "ACCEPTED", null);
    if (!updated) return;
    addAuditEvent({
      actor: reviewer?.name ?? "Unknown Reviewer",
      actorRole: "Inspector",
      action: "maintenance.evidence_reviewed",
      objectType: "EvidenceRecord",
      objectLabel: wo.workOrderNumber,
      previousState: "SUBMITTED",
      newState: "ACCEPTED",
      reason: `Evidence ${id} accepted.`,
    });
    setVersion((v) => v + 1);
  };

  const submitRejection = (id: string) => {
    if (!rejectReason.trim()) return;
    const reviewer = technicians.find((t) => t.id === REPRESENTATIVE_REVIEWER_ID);
    const updated = reviewEvidenceRecord(id, REPRESENTATIVE_REVIEWER_ID, "REJECTED", rejectReason.trim());
    if (!updated) return;
    addAuditEvent({
      actor: reviewer?.name ?? "Unknown Reviewer",
      actorRole: "Inspector",
      action: "maintenance.evidence_rejected",
      objectType: "EvidenceRecord",
      objectLabel: wo.workOrderNumber,
      previousState: "SUBMITTED",
      newState: "REJECTED",
      reason: `Evidence ${id} rejected: ${rejectReason.trim()}`,
    });
    setRejectingId(null);
    setRejectReason("");
    setVersion((v) => v + 1);
  };

  const assign = (technicianId: string) => {
    const wasAssigned = row.assignedTechnicianId !== null;
    const updated = workOrderRepository.assignTechnician(workOrderId, technicianId);
    if (!updated) return;
    const tech = technicians.find((t) => t.id === technicianId);
    addAuditEvent({
      actor: current?.user.name ?? "Unknown User",
      actorRole: "Maintenance",
      action: wasAssigned ? "maintenance.technician_reassigned" : "maintenance.technician_assigned",
      objectType: "WorkOrder",
      objectLabel: wo.workOrderNumber,
      previousState: row.assignedTechnicianName,
      newState: tech?.name ?? technicianId,
    });
    setShowReassign(false);
    setVersion((v) => v + 1);
  };

  const unassign = () => {
    const updated = workOrderRepository.unassignTechnician(workOrderId);
    if (!updated) return;
    addAuditEvent({
      actor: current?.user.name ?? "Unknown User",
      actorRole: "Maintenance",
      action: "maintenance.technician_unassigned",
      objectType: "WorkOrder",
      objectLabel: wo.workOrderNumber,
      previousState: row.assignedTechnicianName,
      newState: null,
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

  const complete = () => {
    if (evidenceBlocksCompletion) return; // guarded — see the disabled-button message below
    const today = new Date().toISOString().slice(0, 10);
    const updated = workOrderRepository.completeWorkOrder(workOrderId, today);
    if (!updated) return;
    addAuditEvent({
      actor: current?.user.name ?? "Unknown User",
      actorRole: "Maintenance",
      action: "maintenance.work_order_completed",
      objectType: "WorkOrder",
      objectLabel: wo.workOrderNumber,
      previousState: row.status,
      newState: "COMPLETED",
    });
    setVersion((v) => v + 1);
  };

  const escalate = () => {
    const updated = workOrderRepository.escalateWorkOrder(workOrderId);
    if (!updated) return;
    addAuditEvent({
      actor: current?.user.name ?? "Unknown User",
      actorRole: "Maintenance",
      action: "maintenance.work_order_escalated",
      objectType: "WorkOrder",
      objectLabel: wo.workOrderNumber,
      previousState: row.priority,
      newState: "CRITICAL",
      reason: "Escalated by maintenance planner.",
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
        <div className="ac-card" style={{ display: "flex", flexWrap: "wrap", gap: 14, alignItems: "center" }}>
          <div>
            <p className="ac-eyebrow" style={{ marginBottom: 4 }}>Execution</p>
            <StatusBadge
              status={executionState === "READY_FOR_RELEASE" ? "COMPLIANT" : executionState === "BLOCKED" ? "NON_COMPLIANT" : "REVIEW_REQUIRED"}
              label={executionState.replace(/_/g, " ")}
            />
          </div>
          <div>
            <p className="ac-eyebrow" style={{ marginBottom: 4 }}>Evidence Gate</p>
            <StatusBadge
              status={evidenceStatus?.state === "PASS" ? "COMPLIANT" : evidenceStatus?.state === "FAIL" ? "NON_COMPLIANT" : evidenceStatus?.state === "UNKNOWN" ? "INSUFFICIENT_DATA" : "COMPLIANT"}
              label={evidenceStatus?.state ?? "NOT_REQUIRED"}
            />
          </div>
          <div>
            <p className="ac-eyebrow" style={{ marginBottom: 4 }}>Release Readiness</p>
            <StatusBadge
              status={releaseReadiness.status === "READY" ? "COMPLIANT" : releaseReadiness.status === "BLOCKED" ? "NON_COMPLIANT" : "INSUFFICIENT_DATA"}
              label={releaseReadiness.status}
            />
          </div>
        </div>
      </section>

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
          <div className="ac-flex ac-justify-between" style={{ flexWrap: "wrap", gap: 10, marginBottom: 6 }}>
            <p className="ac-text-sm" style={{ margin: 0 }}>
              Assigned: {row.assignedTechnicianName ?? <span className="ac-text-muted">Unassigned</span>}
            </p>
            {row.assignedTechnicianId && (
              <div className="ac-flex ac-gap-2">
                <button className="ac-btn" style={{ padding: "2px 8px" }} onClick={() => setShowReassign((s) => !s)}>
                  {showReassign ? "Cancel Reassign" : "Reassign"}
                </button>
                <button className="ac-btn" style={{ padding: "2px 8px" }} onClick={unassign}>Remove Assignment</button>
              </div>
            )}
          </div>

          {(!row.assignedTechnicianId || showReassign) && (
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

              <p className="ac-eyebrow" style={{ margin: "16px 0 6px" }}>Eligible Technicians</p>
              <div className="ac-card" style={{ padding: 0, overflowX: "auto" }}>
                <table className="ac-table">
                  <thead><tr><th>Technician</th><th>Certification Match</th><th>Availability</th><th>Workload</th><th>Reasons</th><th></th></tr></thead>
                  <tbody>
                    {eligibility.map((e) => (
                      <tr key={e.technicianId}>
                        <td>{e.name}</td>
                        <td className="ac-text-sm">{e.certificationMatch}</td>
                        <td className="ac-text-sm">{e.availability}</td>
                        <td className="ac-text-sm">{e.workload}</td>
                        <td className="ac-text-sm">{e.reasons.length > 0 ? e.reasons.join("; ") : "Insufficient source data."}</td>
                        <td><button className="ac-btn" style={{ padding: "2px 8px" }} onClick={() => assign(e.technicianId)}>Assign</button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 4 }}>Technician Authorization</h2>
        <p className="ac-text-sm ac-text-muted" style={{ marginBottom: 10 }}>
          A high certification match or availability ranking above is a recommendation, not authorization — this table is
          the formal authorization determination and always takes precedence. A hard authorization block is never
          overridden by a strong recommendation.
        </p>
        <div className="ac-card" style={{ padding: 0, overflowX: "auto" }}>
          <table className="ac-table">
            <thead><tr><th>Technician</th><th>Status</th><th>Reasons</th></tr></thead>
            <tbody>
              {authorizationMatrix.map((m) => (
                <tr key={m.technicianId}>
                  <td className="ac-text-sm">{m.name}</td>
                  <td>
                    <StatusBadge
                      status={m.status === "AUTHORIZED" ? "COMPLIANT" : m.status === "NOT_AUTHORIZED" ? "NON_COMPLIANT" : "INSUFFICIENT_DATA"}
                      label={m.status.replace(/_/g, " ")}
                    />
                  </td>
                  <td className="ac-text-sm ac-text-muted">{m.reasons.join(" ")}</td>
                </tr>
              ))}
              {authorizationMatrix.length === 0 && (
                <tr><td colSpan={3} className="ac-text-sm ac-text-muted" style={{ textAlign: "center", padding: 16 }}>No technician authorization data available for this work order.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="ac-section">
        <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
          {row.planningStatus === "READY" && (
            <button className="ac-btn ac-btn-primary" onClick={start}>Start Work</button>
          )}
          {row.status === "IN_PROGRESS" && (
            <button className="ac-btn ac-btn-primary" onClick={complete} disabled={evidenceBlocksCompletion} title={evidenceBlocksCompletion ? evidenceStatus?.reason : undefined}>
              Complete
            </button>
          )}
          {row.priority !== "CRITICAL" && row.status !== "COMPLETED" && row.status !== "CANCELLED" && (
            <button className="ac-btn" onClick={escalate}>Escalate</button>
          )}
          <Link href={`/maintenance/work-orders/${wo.id}`} className="ac-btn">View Full Work Order</Link>
          <Link href={`/aircraft/${wo.aircraftId}`} className="ac-btn">View Aircraft</Link>
        </div>
        {row.status === "IN_PROGRESS" && evidenceBlocksCompletion && (
          <div className="ac-card" style={{ borderColor: "var(--ac-status-non_compliant)", marginTop: 10 }}>
            <p className="ac-text-sm" style={{ color: "var(--ac-status-non_compliant)", margin: "0 0 8px", fontWeight: 600 }}>
              Cannot complete task — required execution evidence is not yet accepted.
            </p>
            <p className="ac-text-sm" style={{ margin: "0 0 10px" }}>{evidenceStatus?.reason}</p>
            <a href="#evidence-section" className="ac-btn ac-btn-primary">Go to Evidence — Submit/Review</a>
          </div>
        )}
      </section>

      <section className="ac-section" id="evidence-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Evidence</h2>
        <p className="ac-text-sm ac-text-muted" style={{ marginBottom: 10 }}>
          Prototype storage only — images are held as in-browser object references for this session and are not persisted to
          production object storage. Uploading a photo records that an artifact was captured; it is never treated as proof of
          airworthiness, compliance, or acceptable workmanship on its own.
        </p>
        <div className="ac-card" style={{ marginBottom: 12 }}>
          <StatusBadge
            status={evidenceStatus?.state === "PASS" ? "COMPLIANT" : evidenceStatus?.state === "FAIL" ? "NON_COMPLIANT" : evidenceStatus?.state === "UNKNOWN" ? "INSUFFICIENT_DATA" : "COMPLIANT"}
            label={evidenceStatus?.state ?? "NOT_REQUIRED"}
          />
          <p className="ac-text-sm" style={{ margin: "8px 0 0" }}>{evidenceStatus?.reason}</p>
        </div>

        {evidenceRecords.length > 0 ? (
          <div className="ac-card" style={{ padding: 0, marginBottom: 12, overflowX: "auto" }}>
            <table className="ac-table">
              <thead><tr><th>Type</th><th>Preview</th><th>Uploaded By</th><th>Captured</th><th>Note</th><th>Status</th><th></th></tr></thead>
              <tbody>
                {evidenceRecords.map((e) => {
                  const uploader = technicians.find((t) => t.id === e.uploadedByTechnicianId);
                  return (
                    <tr key={e.id}>
                      <td>{e.evidenceType}</td>
                      <td>
                        {e.fileRef !== "DEMO_SEED_PLACEHOLDER" ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img src={e.fileRef} alt={e.fileName} style={{ width: 48, height: 48, objectFit: "cover", borderRadius: 4 }} />
                        ) : (
                          <span className="ac-text-sm ac-text-muted">{e.fileName}</span>
                        )}
                      </td>
                      <td className="ac-text-sm">{uploader?.name ?? e.uploadedByTechnicianId}</td>
                      <td className="ac-text-sm">{new Date(e.capturedAt).toLocaleString()}</td>
                      <td className="ac-text-sm">{e.technicianNote ?? "—"}{e.status === "REJECTED" && e.reviewNote ? ` (Rejected: ${e.reviewNote})` : ""}</td>
                      <td>
                        <StatusBadge
                          status={e.status === "ACCEPTED" ? "COMPLIANT" : e.status === "REJECTED" ? "NON_COMPLIANT" : "PENDING"}
                          label={e.status}
                        />
                      </td>
                      <td>
                        {e.status === "SUBMITTED" && (
                          <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
                            <button className="ac-btn ac-btn-primary" style={{ padding: "2px 8px" }} onClick={() => acceptEvidence(e.id)}>Accept</button>
                            <button className="ac-btn" style={{ padding: "2px 8px" }} onClick={() => { setRejectingId(rejectingId === e.id ? null : e.id); setRejectReason(""); }}>
                              {rejectingId === e.id ? "Cancel" : "Reject"}
                            </button>
                            <button className="ac-btn" style={{ padding: "2px 8px" }} onClick={() => removeEvidence(e.id)}>Remove</button>
                          </div>
                        )}
                        {rejectingId === e.id && (
                          <div style={{ marginTop: 6 }}>
                            <textarea
                              className="ac-input"
                              style={{ width: 220, fontSize: 12 }}
                              placeholder="Reason for rejection (required)"
                              value={rejectReason}
                              onChange={(ev) => setRejectReason(ev.target.value)}
                            />
                            <button
                              className="ac-btn ac-btn-primary"
                              style={{ padding: "2px 8px", marginTop: 4, display: "block" }}
                              disabled={!rejectReason.trim()}
                              onClick={() => submitRejection(e.id)}
                            >
                              Submit Rejection
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="ac-text-sm ac-text-muted" style={{ marginBottom: 12 }}>No evidence submitted for this work order yet.</p>
        )}

        <div className="ac-card">
          <p className="ac-eyebrow" style={{ marginBottom: 8 }}>Add Evidence</p>
          <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap", marginBottom: 8 }}>
            <select className="ac-input" value={evidenceType} onChange={(e) => setEvidenceType(e.target.value as EvidenceRecordType)}>
              {EVIDENCE_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
            <input
              type="file"
              accept="image/*"
              capture="environment"
              onChange={(e) => onEvidenceFileChange(e.target.files?.[0] ?? null)}
            />
          </div>
          {evidenceError && <p className="ac-text-sm" style={{ color: "var(--ac-status-non_compliant)", marginBottom: 8 }}>{evidenceError}</p>}
          {evidencePreviewUrl && (
            <div style={{ marginBottom: 8 }}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={evidencePreviewUrl} alt="Evidence preview" style={{ maxWidth: 200, maxHeight: 200, borderRadius: 4 }} />
            </div>
          )}
          <textarea
            className="ac-input"
            style={{ width: "100%", marginBottom: 8 }}
            placeholder="Optional note"
            value={evidenceNote}
            onChange={(e) => setEvidenceNote(e.target.value)}
          />
          <div className="ac-flex ac-gap-2">
            <button className="ac-btn ac-btn-primary" onClick={submitEvidence} disabled={!evidenceFile}>Submit Evidence</button>
            {evidenceFile && <button className="ac-btn" onClick={cancelEvidence}>Cancel</button>}
          </div>
        </div>
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Maintenance Task &amp; Release</h2>
        <p className="ac-text-sm ac-text-muted" style={{ marginBottom: 10 }}>
          Technician completion is separate from release. &quot;{statusBadge.label}&quot; describes the work order status; the
          execution state below tracks whether this work order has actually cleared inspection and is ready for release.
        </p>
        <div className="ac-grid-2">
          <div className="ac-card">
            <p className="ac-eyebrow" style={{ marginBottom: 6 }}>Traceability Chain</p>
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
              {taskChain.map((step) => (
                <li key={step.label} style={{ marginBottom: 4 }}>
                  <strong>{step.label}:</strong>{" "}
                  {step.href ? <Link href={step.href}>{step.detail}</Link> : step.detail}
                </li>
              ))}
            </ul>
            {taskExecution && (
              <>
                <p className="ac-eyebrow" style={{ margin: "12px 0 6px" }}>Task Execution</p>
                <p className="ac-text-sm" style={{ margin: "0 0 2px" }}>Performed by: {taskExecution.performedBy}</p>
                <p className="ac-text-sm" style={{ margin: 0 }}>Inspected by: {taskExecution.inspectedBy}</p>
              </>
            )}
          </div>
          <div className="ac-card">
            <p className="ac-eyebrow" style={{ marginBottom: 6 }}>
              Execution State: {executionState.replace(/_/g, " ")}
            </p>
            <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 10px" }}>{explainExecutionState(executionState)}</p>
            <table className="ac-table">
              <thead><tr><th>Safety Gate</th><th>Status</th><th>Reason</th></tr></thead>
              <tbody>
                {safetyGates.map((g) => (
                  <tr key={g.type}>
                    <td className="ac-text-sm">{g.type.replace(/_/g, " ")}</td>
                    <td>
                      <StatusBadge
                        status={g.state === "PASS" ? "COMPLIANT" : g.state === "NOT_REQUIRED" ? "COMPLIANT" : g.state === "UNKNOWN" ? "INSUFFICIENT_DATA" : "NON_COMPLIANT"}
                        label={g.state.replace(/_/g, " ")}
                      />
                    </td>
                    <td className="ac-text-sm">{g.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Release Readiness</h2>
        <p className="ac-text-sm ac-text-muted" style={{ marginBottom: 10 }}>
          Whether this application&apos;s known operational gates are satisfied — not an airworthiness or dispatch determination.
        </p>
        <div className="ac-card" style={{ borderColor: releaseReadiness.status === "BLOCKED" ? "var(--ac-status-non_compliant)" : undefined }}>
          <StatusBadge
            status={releaseReadiness.status === "READY" ? "COMPLIANT" : releaseReadiness.status === "BLOCKED" ? "NON_COMPLIANT" : "INSUFFICIENT_DATA"}
            label={releaseReadiness.status}
          />
          {releaseReadiness.blockers.length > 0 && (
            <ul style={{ margin: "10px 0 0", paddingLeft: 18, fontSize: 13 }}>
              {releaseReadiness.blockers.map((b, i) => (
                <li key={i}><strong>[{b.category}]</strong> {b.explanation} — <em>{b.requiredAction}</em> (source: {b.source})</li>
              ))}
            </ul>
          )}
        </div>
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Work Order History</h2>
        <p className="ac-text-sm ac-text-muted" style={{ marginBottom: 10 }}>
          The recorded history for {row.workOrderNumber}, read directly from the audit trail. This is a session-only prototype — only
          actions taken in this session (or seeded at startup) appear here; no lifecycle step is shown unless it was actually recorded.
        </p>
        <ActionHistory
          events={combinedAuditHistory(row.workOrderNumber, auditLog)}
          emptyMessage="No recorded actions for this work order yet."
        />
      </section>
    </div>
  );
}

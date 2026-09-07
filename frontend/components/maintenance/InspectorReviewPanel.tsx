"use client";

import { useState } from "react";
import type { InspectorReviewStatus } from "@/lib/mock/types";
import { StatusBadge, inspectorReviewStatusBadge } from "@/components/status/StatusBadge";
import { getTechnicianById } from "@/lib/mock/technicians";
import { useChecklistRecord, useMroState } from "@/lib/mro-state/MroStateContext";

const DECISIONS: { value: InspectorReviewStatus; label: string }[] = [
  { value: "APPROVED", label: "Pass" },
  { value: "REJECTED", label: "Fail" },
  { value: "RETURNED_FOR_CORRECTION", label: "Return for Rework" },
];

interface InspectorReviewPanelProps {
  workOrderId: string;
  inspectorId: string;
  /** Reasons PASS is currently blocked (e.g. unresolved UNKNOWN checklist items,
   * open CRITICAL defects). Empty array = PASS is allowed. */
  blockPassReasons?: string[];
}

/**
 * Inspector Decision quality gate, after technician sign-off. Reads and
 * writes the SAME shared checklist record (via MroStateContext) the
 * technician submitted — the inspector reviews the actual submission, not an
 * independently-seeded copy. Still a prototype: nothing here is persisted to
 * a backend; a fresh page load resets the session's in-memory state.
 */
export function InspectorReviewPanel({ workOrderId, inspectorId, blockPassReasons = [] }: InspectorReviewPanelProps) {
  const record = useChecklistRecord(workOrderId);
  const { submitInspectorDecision } = useMroState();
  const inspector = getTechnicianById(inspectorId);

  const [decision, setDecision] = useState<InspectorReviewStatus | null>(null);
  const [comments, setComments] = useState("");

  if (!record) return null;

  const alreadyDecided = record.inspectorDecisionStatus !== "PENDING_INSPECTION";
  const passBlocked = blockPassReasons.length > 0;
  const sameActor = Boolean(record.technicianSignOff && record.technicianSignOff.technicianId === inspectorId);
  const requiresComment = decision === "REJECTED" || decision === "RETURNED_FOR_CORRECTION";
  const commentMissing = requiresComment && comments.trim().length === 0;
  const canSubmit = decision !== null && !commentMissing && !(decision === "APPROVED" && passBlocked);

  function handleSubmit() {
    if (!decision || !canSubmit) return;
    submitInspectorDecision(workOrderId, decision, comments);
  }

  return (
    <div className="ac-card">
      <div className="ac-flex ac-justify-between ac-items-center" style={{ marginBottom: 10 }}>
        <p className="ac-eyebrow" style={{ margin: 0 }}>Inspector Decision</p>
        <StatusBadge {...inspectorReviewStatusBadge(record.inspectorDecisionStatus)} />
      </div>

      <p className="ac-text-sm ac-text-secondary" style={{ marginBottom: 12 }}>
        Inspector: {inspector?.name ?? inspectorId} ({inspector?.role})
      </p>

      {alreadyDecided ? (
        <div>
          <p style={{ fontWeight: 600, margin: "0 0 4px" }}>
            {DECISIONS.find((d) => d.value === record.inspectorDecisionStatus)?.label ?? record.inspectorDecisionStatus.replace(/_/g, " ")}
          </p>
          {record.inspectorComments && <p className="ac-text-sm ac-text-secondary" style={{ margin: "0 0 4px" }}>&ldquo;{record.inspectorComments}&rdquo;</p>}
          <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
            {inspector?.name ?? inspectorId} · {record.inspectorReviewedAt ? new Date(record.inspectorReviewedAt).toLocaleString() : "—"}
          </p>
        </div>
      ) : (
        <div>
          <p className="ac-text-sm ac-text-secondary" style={{ marginBottom: 8 }}>
            The inspector reviews the technician&rsquo;s checklist, measurements, findings, and evidence — the
            technician cannot approve their own work.
          </p>

          {sameActor && (
            <div className="ac-card" style={{ marginBottom: 10, borderColor: "var(--ac-status-non-compliant)", background: "var(--ac-status-non-compliant-bg)" }}>
              <p className="ac-text-sm" style={{ margin: 0, color: "var(--ac-status-non-compliant)" }}>
                Separation-of-duties warning: the technician sign-off and the assigned inspector are the same person. Route this to a different inspector before recording a decision.
              </p>
            </div>
          )}

          {passBlocked && (
            <div className="ac-card" style={{ marginBottom: 10, borderColor: "var(--ac-status-non-compliant)", background: "var(--ac-status-non-compliant-bg)" }}>
              <p className="ac-text-sm" style={{ margin: 0, color: "var(--ac-status-non-compliant)" }}>
                Pass is blocked:
              </p>
              <ul style={{ margin: "4px 0 0", paddingLeft: 18, fontSize: 13 }}>
                {blockPassReasons.map((r, idx) => (
                  <li key={idx}>{r}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap", marginBottom: 10 }}>
            {DECISIONS.map((d) => {
              const disabled = d.value === "APPROVED" && passBlocked;
              return (
                <button
                  key={d.value}
                  className="ac-btn"
                  style={decision === d.value ? { borderColor: "var(--ac-accent)", color: "var(--ac-accent-hover)" } : undefined}
                  onClick={() => setDecision(d.value)}
                  disabled={disabled}
                  title={disabled ? "Pass is blocked — see reasons above" : undefined}
                >
                  {d.label}
                </button>
              );
            })}
          </div>

          <label className="ac-flex ac-flex-col ac-gap-2" style={{ marginBottom: 10 }}>
            <span className="ac-text-sm ac-text-secondary">
              {decision === "REJECTED" && <span style={{ color: "var(--ac-status-non-compliant)" }}>Justification (required for Fail)</span>}
              {decision === "RETURNED_FOR_CORRECTION" && <span style={{ color: "var(--ac-status-review)" }}>Reason (required for Return for Rework)</span>}
              {decision !== "REJECTED" && decision !== "RETURNED_FOR_CORRECTION" && "Comments"}
            </span>
            <textarea
              className="ac-input"
              rows={2}
              value={comments}
              onChange={(e) => setComments(e.target.value)}
              placeholder={requiresComment ? "Explain the reason for this decision…" : "Inspection comments (optional)…"}
            />
          </label>
          {commentMissing && (
            <p className="ac-text-sm" style={{ color: "var(--ac-status-non-compliant)", marginTop: -4, marginBottom: 10 }}>
              A written {decision === "REJECTED" ? "justification" : "reason"} is required before submitting.
            </p>
          )}

          <button className="ac-btn ac-btn-primary" onClick={handleSubmit} disabled={!canSubmit}>
            Submit Decision
          </button>
        </div>
      )}

      <p className="ac-text-sm ac-text-muted" style={{ marginTop: 12 }}>
        Prototype note: this decision is held in shared in-memory state for this session only and is not persisted to a backend.
      </p>
    </div>
  );
}

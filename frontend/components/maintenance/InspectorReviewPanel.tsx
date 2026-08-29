"use client";

import { useState } from "react";
import type { InspectorReview, InspectorReviewStatus } from "@/lib/mock/types";
import { StatusBadge, inspectorReviewStatusBadge } from "@/components/status/StatusBadge";
import { getTechnicianById } from "@/lib/mock/technicians";

const DECISIONS: { value: InspectorReviewStatus; label: string }[] = [
  { value: "APPROVED", label: "Pass" },
  { value: "REJECTED", label: "Fail" },
  { value: "RETURNED_FOR_CORRECTION", label: "Return for Correction" },
];

interface InspectorReviewPanelProps {
  review: InspectorReview;
  /** Reasons PASS is currently blocked (e.g. unresolved UNKNOWN checklist items,
   * open CRITICAL defects). Empty array = PASS is allowed. */
  blockPassReasons?: string[];
}

/**
 * Inspector Decision quality gate, after technician sign-off. Local
 * component state only — mirrors the same non-persisted, clearly-labeled
 * prototype pattern as ChecklistPanel and the compliance Human Review
 * screen. Nothing here is written to a backend.
 */
export function InspectorReviewPanel({ review, blockPassReasons = [] }: InspectorReviewPanelProps) {
  const inspector = getTechnicianById(review.inspectorId);
  const [decision, setDecision] = useState<InspectorReviewStatus | null>(review.status === "PENDING_INSPECTION" ? null : review.status);
  const [comments, setComments] = useState(review.comments);
  const [submitted, setSubmitted] = useState<{ status: InspectorReviewStatus; at: string; comments: string } | null>(
    review.status !== "PENDING_INSPECTION" ? { status: review.status, at: review.reviewedAt ?? "", comments: review.comments } : null
  );

  const passBlocked = blockPassReasons.length > 0;
  const requiresComment = decision === "REJECTED" || decision === "RETURNED_FOR_CORRECTION";
  const commentMissing = requiresComment && comments.trim().length === 0;
  const canSubmit = decision !== null && !commentMissing && !(decision === "APPROVED" && passBlocked);

  function handleSubmit() {
    if (!decision || !canSubmit) return;
    setSubmitted({ status: decision, at: new Date().toISOString(), comments });
  }

  return (
    <div className="ac-card">
      <div className="ac-flex ac-justify-between ac-items-center" style={{ marginBottom: 10 }}>
        <p className="ac-eyebrow" style={{ margin: 0 }}>Inspector Decision</p>
        <StatusBadge {...inspectorReviewStatusBadge(submitted?.status ?? "PENDING_INSPECTION")} />
      </div>

      <p className="ac-text-sm ac-text-secondary" style={{ marginBottom: 12 }}>
        Inspector: {inspector?.name ?? review.inspectorId} ({inspector?.role})
      </p>

      {submitted ? (
        <div>
          <p style={{ fontWeight: 600, margin: "0 0 4px" }}>
            {DECISIONS.find((d) => d.value === submitted.status)?.label ?? submitted.status.replace(/_/g, " ")}
          </p>
          {submitted.comments && <p className="ac-text-sm ac-text-secondary" style={{ margin: "0 0 4px" }}>&ldquo;{submitted.comments}&rdquo;</p>}
          <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
            {inspector?.name ?? review.inspectorId} · {submitted.at ? new Date(submitted.at).toLocaleString() : "—"}
          </p>
        </div>
      ) : (
        <div>
          <p className="ac-text-sm ac-text-secondary" style={{ marginBottom: 8 }}>
            The inspector reviews the technician&rsquo;s checklist, measurements, findings, and evidence — the
            technician cannot approve their own work.
          </p>

          {passBlocked && (
            <div className="ac-card" style={{ marginBottom: 10, borderColor: "var(--ac-status-non-compliant)", background: "rgba(229,72,77,0.06)" }}>
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
              {decision === "RETURNED_FOR_CORRECTION" && <span style={{ color: "var(--ac-status-review)" }}>Reason (required for Return for Correction)</span>}
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
        Prototype note: this decision is held in local component state only and is not persisted to a backend.
      </p>
    </div>
  );
}

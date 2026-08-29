"use client";

import { useState } from "react";
import type { InspectorReview, InspectorReviewStatus } from "@/lib/mock/types";
import { StatusBadge, inspectorReviewStatusBadge } from "@/components/status/StatusBadge";
import { getTechnicianById } from "@/lib/mock/technicians";

const DECISIONS: { value: InspectorReviewStatus; label: string }[] = [
  { value: "APPROVED", label: "Approve" },
  { value: "REJECTED", label: "Reject" },
  { value: "RETURNED_FOR_CORRECTION", label: "Return for Correction" },
];

/**
 * Inspector review step, after technician sign-off. Local component state
 * only — mirrors the same non-persisted, clearly-labeled prototype pattern
 * as ChecklistPanel and the compliance Human Review screen.
 */
export function InspectorReviewPanel({ review }: { review: InspectorReview }) {
  const inspector = getTechnicianById(review.inspectorId);
  const [decision, setDecision] = useState<InspectorReviewStatus | null>(review.status === "PENDING_INSPECTION" ? null : review.status);
  const [comments, setComments] = useState(review.comments);
  const [submitted, setSubmitted] = useState<{ status: InspectorReviewStatus; at: string } | null>(
    review.status !== "PENDING_INSPECTION" ? { status: review.status, at: review.reviewedAt ?? "" } : null
  );

  function handleSubmit() {
    if (!decision) return;
    setSubmitted({ status: decision, at: new Date().toISOString() });
  }

  return (
    <div className="ac-card">
      <div className="ac-flex ac-justify-between ac-items-center" style={{ marginBottom: 10 }}>
        <p className="ac-eyebrow" style={{ margin: 0 }}>Inspector Review</p>
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
          {comments && <p className="ac-text-sm ac-text-secondary" style={{ margin: "0 0 4px" }}>&ldquo;{comments}&rdquo;</p>}
          <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
            {submitted.at ? new Date(submitted.at).toLocaleString() : "—"}
          </p>
        </div>
      ) : (
        <div>
          <p className="ac-text-sm ac-text-secondary" style={{ marginBottom: 8 }}>
            The inspector reviews the technician&rsquo;s checklist, measurements, findings, and evidence — the
            technician cannot approve their own work.
          </p>
          <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap", marginBottom: 10 }}>
            {DECISIONS.map((d) => (
              <button
                key={d.value}
                className="ac-btn"
                style={decision === d.value ? { borderColor: "var(--ac-accent)", color: "var(--ac-accent-hover)" } : undefined}
                onClick={() => setDecision(d.value)}
              >
                {d.label}
              </button>
            ))}
          </div>
          <label className="ac-flex ac-flex-col ac-gap-2" style={{ marginBottom: 10 }}>
            <span className="ac-text-sm ac-text-secondary">Comments</span>
            <textarea className="ac-input" rows={2} value={comments} onChange={(e) => setComments(e.target.value)} placeholder="Inspection comments…" />
          </label>
          <button className="ac-btn ac-btn-primary" onClick={handleSubmit} disabled={!decision}>
            Submit Review
          </button>
        </div>
      )}

      <p className="ac-text-sm ac-text-muted" style={{ marginTop: 12 }}>
        Prototype note: this review is held in local component state only and is not persisted.
      </p>
    </div>
  );
}

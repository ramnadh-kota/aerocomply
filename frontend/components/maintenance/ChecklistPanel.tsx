"use client";

import type { Checklist, ChecklistItemResult } from "@/lib/mock/types";
import { StatusBadge, checklistResultBadge } from "@/components/status/StatusBadge";
import { useChecklistRecord, useMroState } from "@/lib/mro-state/MroStateContext";

const RESULT_OPTIONS: ChecklistItemResult[] = ["PASS", "FAIL", "NOT_APPLICABLE", "UNKNOWN"];
const DEMO_TECHNICIAN_ID = "tech-1"; // prototype: sign-off identity is not tied to real auth

/**
 * Interactive checklist for a work order task. Reads and writes the SAME
 * shared submission record (via MroStateContext) that the Inspector Decision
 * screen reviews — this is what makes the technician's submission the
 * submission the inspector sees, not a separate re-seeded copy. Still a
 * prototype: state is in-memory only, never persisted to a backend.
 *
 * UNKNOWN is a first-class result, never coerced to PASS or FAIL — if any
 * item is UNKNOWN, the overall outcome is REVIEW REQUIRED, never a silent
 * pass.
 */
export function ChecklistPanel({ checklist, workOrderId }: { checklist: Checklist; workOrderId: string }) {
  const record = useChecklistRecord(workOrderId);
  const { updateChecklistItem, technicianSignOff, submitForInspection } = useMroState();

  if (!record) return null;

  const submitted = record.submissionStatus === "SUBMITTED";
  const items = record.items;
  const resolvedCount = checklist.items.filter((i) => items[i.id]?.result !== null && items[i.id] !== undefined).length;
  const unknownCount = checklist.items.filter((i) => items[i.id]?.result === "UNKNOWN").length;
  const failCount = checklist.items.filter((i) => items[i.id]?.result === "FAIL").length;
  const progress = Math.round((resolvedCount / checklist.items.length) * 100);
  const allResolved = resolvedCount === checklist.items.length;

  const overallOutcome: ChecklistItemResult | "REVIEW_REQUIRED" = unknownCount > 0 ? "REVIEW_REQUIRED" : failCount > 0 ? "FAIL" : "PASS";

  function handleSignOff() {
    technicianSignOff(workOrderId, DEMO_TECHNICIAN_ID);
  }

  function handleSubmit() {
    if (!allResolved || !record?.technicianSignOff) return;
    submitForInspection(workOrderId);
  }

  return (
    <div className="ac-card">
      <div className="ac-flex ac-justify-between ac-items-center" style={{ marginBottom: 10 }}>
        <p className="ac-eyebrow" style={{ margin: 0 }}>
          {checklist.title}
        </p>
        <span className="ac-text-sm ac-text-muted">{progress}% complete</span>
      </div>

      <div style={{ height: 6, borderRadius: 4, background: "var(--ac-border)", overflow: "hidden", marginBottom: 10 }}>
        <div style={{ width: `${progress}%`, height: "100%", background: "var(--ac-accent)", transition: "width 0.2s ease" }} />
      </div>

      {allResolved && (
        <div className="ac-flex ac-items-center ac-gap-2" style={{ marginBottom: 14 }}>
          <span className="ac-text-sm ac-text-muted">Overall outcome:</span>
          <StatusBadge {...checklistResultBadge(overallOutcome === "REVIEW_REQUIRED" ? "UNKNOWN" : overallOutcome)} label={overallOutcome.replace(/_/g, " ")} />
          {overallOutcome === "REVIEW_REQUIRED" && (
            <span className="ac-text-sm" style={{ color: "var(--ac-status-insufficient)" }}>
              {unknownCount} item{unknownCount > 1 ? "s" : ""} unresolved — never treated as pass or fail.
            </span>
          )}
        </div>
      )}

      <div className="ac-text-sm ac-text-secondary" style={{ marginBottom: 14, display: "grid", gap: 4 }}>
        <div><span className="ac-text-muted">Required reference: </span>{checklist.requiredReference}</div>
        {checklist.requiredTools.length > 0 && <div><span className="ac-text-muted">Required tools: </span>{checklist.requiredTools.join(", ")}</div>}
        {checklist.requiredParts.length > 0 && <div><span className="ac-text-muted">Required parts: </span>{checklist.requiredParts.join(", ")}</div>}
        <div><span className="ac-text-muted">Required evidence: </span>{checklist.requiredEvidence}</div>
        <div><span className="ac-text-muted">Acceptance criteria: </span>{checklist.acceptanceCriteria}</div>
      </div>

      <fieldset style={{ border: "none", padding: 0, margin: 0 }} disabled={submitted}>
        <legend className="ac-text-sm ac-text-secondary" style={{ marginBottom: 8 }}>Checklist Items</legend>
        <div className="ac-flex ac-flex-col ac-gap-3">
          {checklist.items.map((item) => {
            const state = items[item.id] ?? { result: null, actualValue: "", note: "", evidenceAttached: false };
            const withinLimits =
              item.requiresMeasurement && state.actualValue !== "" && item.minLimit !== null && item.maxLimit !== null
                ? Number(state.actualValue) >= item.minLimit && Number(state.actualValue) <= item.maxLimit
                : null;
            return (
              <div key={item.id} className="ac-card" style={{ background: "var(--ac-bg)", padding: "var(--ac-space-3)" }}>
                <div className="ac-flex ac-justify-between ac-items-center" style={{ marginBottom: 4 }}>
                  <span style={{ fontWeight: 600, fontSize: 13 }}>
                    <span className="ac-mono ac-text-muted" style={{ marginRight: 6 }}>{item.id}</span>
                    {item.label}
                  </span>
                  {state.result && <StatusBadge {...checklistResultBadge(state.result)} />}
                </div>
                <p className="ac-text-sm ac-text-secondary" style={{ margin: "0 0 2px" }}>{item.instruction}</p>
                <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 4px" }}>Acceptance: {item.acceptanceCriteria}</p>
                {(item.findingRequiredOnFail || item.evidenceRequired || item.requiresMeasurement) && (
                  <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 8px" }}>
                    Prerequisites: {[
                      item.requiresMeasurement && "measurement recorded",
                      item.evidenceRequired && "evidence attached",
                      item.findingRequiredOnFail && "finding required if FAIL",
                    ].filter(Boolean).join(" · ")}
                  </p>
                )}

                {item.requiresMeasurement && (
                  <div className="ac-flex ac-items-center ac-gap-2" style={{ marginBottom: 8 }}>
                    <input
                      type="number"
                      className="ac-input"
                      style={{ maxWidth: 120 }}
                      value={state.actualValue}
                      onChange={(e) => updateChecklistItem(workOrderId, item.id, { actualValue: e.target.value })}
                      aria-label={`${item.label} measured value`}
                      placeholder="Value"
                    />
                    <span className="ac-text-sm ac-text-muted">
                      {item.unit} {item.minLimit !== null && item.maxLimit !== null && `(limit ${item.minLimit}–${item.maxLimit})`}
                    </span>
                    {withinLimits !== null && (
                      <span className="ac-text-sm" style={{ color: withinLimits ? "var(--ac-status-compliant)" : "var(--ac-status-non-compliant)" }}>
                        {withinLimits ? "Within limits" : "Out of limits"}
                      </span>
                    )}
                  </div>
                )}

                <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap", marginBottom: 8 }}>
                  {RESULT_OPTIONS.map((opt) => (
                    <button
                      key={opt}
                      type="button"
                      className="ac-btn"
                      style={state.result === opt ? { borderColor: "var(--ac-accent)", color: "var(--ac-accent-hover)" } : undefined}
                      onClick={() => updateChecklistItem(workOrderId, item.id, { result: opt })}
                      disabled={submitted}
                    >
                      {opt.replace(/_/g, " ")}
                    </button>
                  ))}
                </div>

                {state.result === "FAIL" && item.findingRequiredOnFail && (
                  <label className="ac-flex ac-flex-col ac-gap-2" style={{ marginBottom: 8 }}>
                    <span className="ac-text-sm" style={{ color: "var(--ac-status-non-compliant)" }}>Finding required (fail)</span>
                    <textarea className="ac-input" rows={2} value={state.note} onChange={(e) => updateChecklistItem(workOrderId, item.id, { note: e.target.value })} placeholder="Describe the finding…" disabled={submitted} />
                  </label>
                )}
                {state.result === "UNKNOWN" && (
                  <label className="ac-flex ac-flex-col ac-gap-2" style={{ marginBottom: 8 }}>
                    <span className="ac-text-sm" style={{ color: "var(--ac-status-insufficient)" }}>Why is this unknown? (required information missing — do not guess)</span>
                    <textarea className="ac-input" rows={2} value={state.note} onChange={(e) => updateChecklistItem(workOrderId, item.id, { note: e.target.value })} placeholder="e.g. tooling unavailable, data not accessible…" disabled={submitted} />
                  </label>
                )}
                {item.evidenceRequired && (
                  <label className="ac-flex ac-items-center ac-gap-2" style={{ fontSize: 13 }}>
                    <input type="checkbox" checked={state.evidenceAttached} onChange={(e) => updateChecklistItem(workOrderId, item.id, { evidenceAttached: e.target.checked })} disabled={submitted} />
                    Evidence attached for this item
                  </label>
                )}
              </div>
            );
          })}
        </div>
      </fieldset>

      <hr className="ac-divider" />

      {submitted ? (
        <p style={{ color: "var(--ac-status-compliant)", fontWeight: 600, margin: 0 }}>
          ✓ Submitted for inspection/review by {record.technicianSignOff?.technicianId} at{" "}
          {record.submittedAt ? new Date(record.submittedAt).toLocaleString() : ""}
        </p>
      ) : (
        <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
          <button className="ac-btn" onClick={handleSignOff} disabled={!allResolved || !!record.technicianSignOff}>
            {record.technicianSignOff ? `Signed off by ${record.technicianSignOff.technicianId}` : "Technician Sign-off"}
          </button>
          <button className="ac-btn ac-btn-primary" onClick={handleSubmit} disabled={!allResolved || !record.technicianSignOff}>
            Submit for Inspection/Review
          </button>
        </div>
      )}

      <p className="ac-text-sm ac-text-muted" style={{ marginTop: 12 }}>
        Prototype note: this submission is held in shared in-memory state for this session only —
        it is not persisted to a backend and resets on reload.
      </p>
    </div>
  );
}

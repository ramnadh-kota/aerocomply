"use client";

import { useState } from "react";
import type { Checklist, ChecklistItemResult } from "@/lib/mock/types";
import { StatusBadge, checklistResultBadge } from "@/components/status/StatusBadge";

const RESULT_OPTIONS: ChecklistItemResult[] = ["PASS", "FAIL", "NOT_APPLICABLE", "UNKNOWN"];

interface ItemState {
  result: ChecklistItemResult | null;
  actualValue: string;
  note: string;
  evidenceAttached: boolean;
}

/**
 * Interactive checklist for a work order task. All state is local React
 * state only — nothing here is persisted to a backend. This is a prototype
 * of the technician sign-off + inspector review workflow, clearly labeled.
 *
 * UNKNOWN is a first-class result, never coerced to PASS or FAIL — if any
 * item is UNKNOWN, the overall outcome is REVIEW REQUIRED, never a silent
 * pass.
 */
export function ChecklistPanel({ checklist }: { checklist: Checklist }) {
  const [items, setItems] = useState<Record<string, ItemState>>(
    Object.fromEntries(checklist.items.map((i) => [i.id, { result: null, actualValue: "", note: "", evidenceAttached: false }]))
  );
  const [signOff, setSignOff] = useState<{ by: string; at: string } | null>(null);
  const [submitted, setSubmitted] = useState(false);

  const resolvedCount = Object.values(items).filter((i) => i.result !== null).length;
  const unknownCount = Object.values(items).filter((i) => i.result === "UNKNOWN").length;
  const failCount = Object.values(items).filter((i) => i.result === "FAIL").length;
  const progress = Math.round((resolvedCount / checklist.items.length) * 100);
  const allResolved = resolvedCount === checklist.items.length;

  const overallOutcome: ChecklistItemResult | "REVIEW_REQUIRED" = unknownCount > 0 ? "REVIEW_REQUIRED" : failCount > 0 ? "FAIL" : "PASS";

  function setItemState(id: string, patch: Partial<ItemState>) {
    if (submitted) return;
    setItems((s) => ({ ...s, [id]: { ...s[id], ...patch } }));
  }

  function handleSignOff() {
    setSignOff({ by: "Rahul Menon", at: new Date().toISOString() });
  }

  function handleSubmit() {
    if (!allResolved || !signOff) return;
    setSubmitted(true);
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
            const state = items[item.id];
            const withinLimits =
              item.requiresMeasurement && state.actualValue !== "" && item.minLimit !== null && item.maxLimit !== null
                ? Number(state.actualValue) >= item.minLimit && Number(state.actualValue) <= item.maxLimit
                : null;
            return (
              <div key={item.id} className="ac-card" style={{ background: "var(--ac-bg)", padding: "var(--ac-space-3)" }}>
                <div className="ac-flex ac-justify-between ac-items-center" style={{ marginBottom: 4 }}>
                  <span style={{ fontWeight: 600, fontSize: 13 }}>{item.label}</span>
                  {state.result && <StatusBadge {...checklistResultBadge(state.result)} />}
                </div>
                <p className="ac-text-sm ac-text-secondary" style={{ margin: "0 0 2px" }}>{item.instruction}</p>
                <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 8px" }}>Acceptance: {item.acceptanceCriteria}</p>

                {item.requiresMeasurement && (
                  <div className="ac-flex ac-items-center ac-gap-2" style={{ marginBottom: 8 }}>
                    <input
                      type="number"
                      className="ac-input"
                      style={{ maxWidth: 120 }}
                      value={state.actualValue}
                      onChange={(e) => setItemState(item.id, { actualValue: e.target.value })}
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
                      onClick={() => setItemState(item.id, { result: opt })}
                      disabled={submitted}
                    >
                      {opt.replace(/_/g, " ")}
                    </button>
                  ))}
                </div>

                {state.result === "FAIL" && item.findingRequiredOnFail && (
                  <label className="ac-flex ac-flex-col ac-gap-2" style={{ marginBottom: 8 }}>
                    <span className="ac-text-sm" style={{ color: "var(--ac-status-non-compliant)" }}>Finding required (fail)</span>
                    <textarea className="ac-input" rows={2} value={state.note} onChange={(e) => setItemState(item.id, { note: e.target.value })} placeholder="Describe the finding…" />
                  </label>
                )}
                {state.result === "UNKNOWN" && (
                  <label className="ac-flex ac-flex-col ac-gap-2" style={{ marginBottom: 8 }}>
                    <span className="ac-text-sm" style={{ color: "var(--ac-status-insufficient)" }}>Why is this unknown? (required information missing — do not guess)</span>
                    <textarea className="ac-input" rows={2} value={state.note} onChange={(e) => setItemState(item.id, { note: e.target.value })} placeholder="e.g. tooling unavailable, data not accessible…" />
                  </label>
                )}
                {item.evidenceRequired && (
                  <label className="ac-flex ac-items-center ac-gap-2" style={{ fontSize: 13 }}>
                    <input type="checkbox" checked={state.evidenceAttached} onChange={(e) => setItemState(item.id, { evidenceAttached: e.target.checked })} />
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
          ✓ Submitted for inspection/review by {signOff?.by} at {signOff ? new Date(signOff.at).toLocaleString() : ""}
        </p>
      ) : (
        <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
          <button className="ac-btn" onClick={handleSignOff} disabled={!allResolved || !!signOff}>
            {signOff ? `Signed off by ${signOff.by}` : "Technician Sign-off"}
          </button>
          <button className="ac-btn ac-btn-primary" onClick={handleSubmit} disabled={!allResolved || !signOff}>
            Submit for Inspection/Review
          </button>
        </div>
      )}

      <p className="ac-text-sm ac-text-muted" style={{ marginTop: 12 }}>
        Prototype note: checklist state is held in local component state only and resets on reload —
        it is not persisted to a backend.
      </p>
    </div>
  );
}

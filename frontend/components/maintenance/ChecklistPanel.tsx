"use client";

import { useState } from "react";
import type { Checklist } from "@/lib/mock/types";

/**
 * Interactive checklist for a work order task. All state is local React
 * state only — nothing here is persisted to a backend. This is a prototype
 * of the technician sign-off workflow, clearly labeled as such.
 */
export function ChecklistPanel({ checklist }: { checklist: Checklist }) {
  const [checked, setChecked] = useState<Record<string, boolean>>({});
  const [measurements, setMeasurements] = useState("");
  const [findings, setFindings] = useState("");
  const [evidenceAttached, setEvidenceAttached] = useState(false);
  const [signOff, setSignOff] = useState<{ by: string; at: string } | null>(null);
  const [submitted, setSubmitted] = useState(false);

  const doneCount = Object.values(checked).filter(Boolean).length;
  const progress = Math.round((doneCount / checklist.items.length) * 100);
  const allChecked = doneCount === checklist.items.length;

  function toggle(id: string) {
    if (submitted) return;
    setChecked((c) => ({ ...c, [id]: !c[id] }));
  }

  function handleSignOff() {
    setSignOff({ by: "Rahul Menon", at: new Date().toISOString() });
  }

  function handleSubmit() {
    if (!allChecked || !signOff) return;
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

      <div style={{ height: 6, borderRadius: 4, background: "var(--ac-border)", overflow: "hidden", marginBottom: 14 }}>
        <div style={{ width: `${progress}%`, height: "100%", background: "var(--ac-accent)", transition: "width 0.2s ease" }} />
      </div>

      <div className="ac-text-sm ac-text-secondary" style={{ marginBottom: 14, display: "grid", gap: 4 }}>
        <div><span className="ac-text-muted">Required reference: </span>{checklist.requiredReference}</div>
        {checklist.requiredTools.length > 0 && <div><span className="ac-text-muted">Required tools: </span>{checklist.requiredTools.join(", ")}</div>}
        {checklist.requiredParts.length > 0 && <div><span className="ac-text-muted">Required parts: </span>{checklist.requiredParts.join(", ")}</div>}
        <div><span className="ac-text-muted">Required evidence: </span>{checklist.requiredEvidence}</div>
        <div><span className="ac-text-muted">Acceptance criteria: </span>{checklist.acceptanceCriteria}</div>
      </div>

      <fieldset style={{ border: "none", padding: 0, margin: 0 }} disabled={submitted}>
        <legend className="ac-text-sm ac-text-secondary" style={{ marginBottom: 8 }}>Checklist</legend>
        <div className="ac-flex ac-flex-col ac-gap-2">
          {checklist.items.map((item) => (
            <label key={item.id} className="ac-flex ac-items-center ac-gap-2" style={{ fontSize: 13 }}>
              <input type="checkbox" checked={Boolean(checked[item.id])} onChange={() => toggle(item.id)} aria-label={item.label} />
              <span style={{ textDecoration: checked[item.id] ? "line-through" : "none", opacity: checked[item.id] ? 0.7 : 1 }}>{item.label}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <hr className="ac-divider" />

      <div className="ac-grid-2" style={{ marginBottom: 12 }}>
        <label className="ac-flex ac-flex-col ac-gap-2">
          <span className="ac-text-sm ac-text-secondary">Measurements</span>
          <textarea className="ac-input" rows={2} value={measurements} onChange={(e) => setMeasurements(e.target.value)} disabled={submitted} placeholder="Record measurements…" />
        </label>
        <label className="ac-flex ac-flex-col ac-gap-2">
          <span className="ac-text-sm ac-text-secondary">Findings</span>
          <textarea className="ac-input" rows={2} value={findings} onChange={(e) => setFindings(e.target.value)} disabled={submitted} placeholder="Record findings…" />
        </label>
      </div>

      <label className="ac-flex ac-items-center ac-gap-2" style={{ fontSize: 13, marginBottom: 14 }}>
        <input type="checkbox" checked={evidenceAttached} onChange={(e) => setEvidenceAttached(e.target.checked)} disabled={submitted} />
        Evidence attached (photos / measurement log)
      </label>

      {submitted ? (
        <p style={{ color: "var(--ac-status-compliant)", fontWeight: 600, margin: 0 }}>
          ✓ Submitted for inspection/review by {signOff?.by} at {signOff ? new Date(signOff.at).toLocaleString() : ""}
        </p>
      ) : (
        <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
          <button className="ac-btn" onClick={handleSignOff} disabled={!allChecked || !!signOff}>
            {signOff ? `Signed off by ${signOff.by}` : "Technician Sign-off"}
          </button>
          <button className="ac-btn ac-btn-primary" onClick={handleSubmit} disabled={!allChecked || !signOff}>
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

/**
 * Deliberately subordinate AI placeholder. Per ADR-004, the rules engine
 * produces the compliance decision; AI only ever explains/assists, and that
 * boundary must be visually obvious even in a prototype where AI isn't built
 * yet at all.
 */
export function AIPlaceholder() {
  return (
    <div className="ac-card" style={{ borderStyle: "dashed", opacity: 0.85 }}>
      <p className="ac-eyebrow" style={{ marginBottom: 6 }}>
        AI Assistance — Coming in M4
      </p>
      <p className="ac-text-sm ac-text-secondary" style={{ margin: 0 }}>
        Planned: explain this regulation in plain language, summarize evidence, retrieve relevant
        regulatory passages, and answer grounded questions.
      </p>
      <p className="ac-text-sm" style={{ marginTop: 8, color: "var(--ac-text-muted)" }}>
        The rules engine produces the compliance decision. AI explains and assists — it never
        makes or overrides the decision (see ADR-004).
      </p>
    </div>
  );
}

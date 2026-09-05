const STEPS = ["Regulation", "Configuration", "Rule Evaluation", "Assessment", "Evidence", "Human Decision", "Audit"];

/**
 * AeroComply's signature visual pattern — the core intelligence loop. Used on
 * the dashboard and the requirement detail page.
 */
export function CoreLoopDiagram({ compact = false }: { compact?: boolean }) {
  return (
    <div
      className="ac-flex ac-items-center"
      style={{ gap: compact ? 4 : 8, flexWrap: "wrap" }}
      role="img"
      aria-label={`AeroComply core loop: ${STEPS.join(" leads to ")}`}
    >
      {STEPS.map((step, idx) => (
        <div key={step} className="ac-flex ac-items-center" style={{ gap: compact ? 4 : 8 }}>
          <div
            style={{
              padding: compact ? "6px 10px" : "10px 16px",
              borderRadius: "var(--ac-radius-md)",
              border: "1px solid var(--ac-border)",
              background: "var(--ac-bg-surface)",
              fontSize: compact ? 11 : 13,
              fontWeight: 600,
              whiteSpace: "nowrap",
            }}
          >
            {step}
          </div>
          {idx < STEPS.length - 1 && (
            <span aria-hidden="true" style={{ color: "var(--ac-text-muted)" }}>
              →
            </span>
          )}
        </div>
      ))}
    </div>
  );
}

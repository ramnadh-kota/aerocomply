import type { ConditionEvaluation } from "@/lib/mock/types";

const ICON: Record<ConditionEvaluation["result"], string> = {
  TRUE: "✓",
  FALSE: "✗",
  UNKNOWN: "⚠",
};

const COLOR_VAR: Record<ConditionEvaluation["result"], string> = {
  TRUE: "var(--ac-status-compliant)",
  FALSE: "var(--ac-status-non-compliant)",
  UNKNOWN: "var(--ac-status-insufficient)",
};

/**
 * AeroComply's signature "Show me why" pattern: every APPLICABLE / NOT_APPLICABLE
 * / UNKNOWN / INSUFFICIENT_DATA / REVIEW_REQUIRED result is explained condition
 * by condition, and UNKNOWN is always visually distinct from FALSE.
 */
export function WhyPanel({ evaluations }: { evaluations: ConditionEvaluation[] }) {
  const supported = evaluations.filter((e) => e.result === "TRUE" || e.result === "FALSE").length;

  return (
    <div>
      <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
        {evaluations.map((ev) => (
          <li key={ev.conditionId} className="ac-flex ac-gap-3" style={{ padding: "8px 0", borderBottom: "1px solid var(--ac-border-subtle)" }}>
            <span aria-hidden="true" style={{ color: COLOR_VAR[ev.result], fontWeight: 700, width: 16, flexShrink: 0 }}>
              {ICON[ev.result]}
            </span>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 13 }}>
                {ev.label}
                <span className="ac-text-sm ac-text-muted"> — expected {ev.expected}</span>
              </div>
              {ev.actual && <div className="ac-text-sm ac-text-secondary">Actual: {ev.actual}</div>}
              {ev.note && (
                <div className="ac-text-sm" style={{ color: "var(--ac-status-insufficient)", marginTop: 2 }}>
                  {ev.note}
                </div>
              )}
            </div>
          </li>
        ))}
      </ul>
      <p className="ac-text-sm ac-text-muted" style={{ marginTop: "var(--ac-space-3)" }}>
        {supported} / {evaluations.length} conditions resolved
        {evaluations.some((e) => e.result === "UNKNOWN") ? " — unresolved conditions are shown as UNKNOWN, never silently treated as false." : ""}
      </p>
    </div>
  );
}

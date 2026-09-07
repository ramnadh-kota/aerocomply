"use client";

import { useState } from "react";
import type { ApplicabilityCondition, ConditionResult } from "@/lib/mock/types";
import { StatusBadge } from "@/components/status/StatusBadge";

const TYPE_LABELS: Record<string, string> = {
  AND: "AND",
  OR: "OR",
  NOT: "NOT",
  AIRCRAFT_TYPE: "AIRCRAFT_TYPE",
  AIRCRAFT_VARIANT: "AIRCRAFT_VARIANT",
  MSN_RANGE: "MSN_RANGE",
  ENGINE_TYPE: "ENGINE_TYPE",
  COMPONENT_PART: "COMPONENT_PART",
  REGISTRATION: "REGISTRATION",
  MODIFICATION_EXCLUSION: "MODIFICATION_EXCLUSION",
};

const COMBINATORS = new Set(["AND", "OR", "NOT"]);

interface ConditionTreeProps {
  node: ApplicabilityCondition;
  /** Map of conditionId -> Kleene result, for the decision-visualizer use case. Omit for a purely structural view. */
  results?: Record<string, ConditionResult>;
  depth?: number;
}

export function ConditionTree({ node, results, depth = 0 }: ConditionTreeProps) {
  const [expanded, setExpanded] = useState(true);
  const isCombinator = COMBINATORS.has(node.conditionType);
  const hasChildren = (node.children?.length ?? 0) > 0;
  const result = results?.[node.id];

  return (
    <div style={{ marginLeft: depth === 0 ? 0 : 20, borderLeft: depth === 0 ? "none" : "1px solid var(--ac-border)", paddingLeft: depth === 0 ? 0 : 16 }}>
      <div className="ac-flex ac-items-center ac-gap-2" style={{ padding: "6px 0" }}>
        {hasChildren ? (
          <button
            aria-expanded={expanded}
            aria-label={expanded ? `Collapse ${node.label}` : `Expand ${node.label}`}
            onClick={() => setExpanded((v) => !v)}
            style={{ background: "none", border: "none", color: "var(--ac-text-muted)", padding: 0, width: 16 }}
          >
            {expanded ? "▾" : "▸"}
          </button>
        ) : (
          <span style={{ width: 16 }} aria-hidden="true" />
        )}

        <span
          className="ac-eyebrow"
          style={{
            padding: "2px 6px",
            borderRadius: 4,
            background: isCombinator ? "var(--ac-bg-surface-hover)" : "var(--ac-accent-muted)",
            color: isCombinator ? "var(--ac-text-secondary)" : "var(--ac-accent-hover)",
          }}
        >
          {TYPE_LABELS[node.conditionType] ?? node.conditionType}
        </span>

        <span style={{ fontSize: 13 }}>{node.label}</span>

        {result && <StatusBadge status={result} />}
      </div>

      {expanded && hasChildren && (
        <div>
          {node.children!.map((child) => (
            <ConditionTree key={child.id} node={child} results={results} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

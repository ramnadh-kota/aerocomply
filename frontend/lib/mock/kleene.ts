import type { ApplicabilityCondition, ConditionResult } from "./types";

// Three-valued (Kleene) logic for combining condition results — "unknown is
// not false" (docs/ontology/DOMAIN_INVARIANTS.md #23). UNKNOWN is not
// absorbed by TRUE in an AND, but IS absorbed by TRUE in an OR.

export function kleeneAnd(a: ConditionResult, b: ConditionResult): ConditionResult {
  if (a === "FALSE" || b === "FALSE") return "FALSE";
  if (a === "UNKNOWN" || b === "UNKNOWN") return "UNKNOWN";
  return "TRUE";
}

export function kleeneOr(a: ConditionResult, b: ConditionResult): ConditionResult {
  if (a === "TRUE" || b === "TRUE") return "TRUE";
  if (a === "UNKNOWN" || b === "UNKNOWN") return "UNKNOWN";
  return "FALSE";
}

export function kleeneNot(a: ConditionResult): ConditionResult {
  if (a === "UNKNOWN") return "UNKNOWN";
  return a === "TRUE" ? "FALSE" : "TRUE";
}

/**
 * Recursively evaluates a condition tree given a map of leaf condition id ->
 * result, returning the result for every node (leaves and combinators).
 */
export function evaluateTree(
  node: ApplicabilityCondition,
  leafResults: Record<string, ConditionResult>
): Record<string, ConditionResult> {
  const results: Record<string, ConditionResult> = {};

  function visit(n: ApplicabilityCondition): ConditionResult {
    let result: ConditionResult;
    if (n.conditionType === "AND") {
      result = (n.children ?? []).map(visit).reduce(kleeneAnd, "TRUE");
    } else if (n.conditionType === "OR") {
      result = (n.children ?? []).map(visit).reduce(kleeneOr, "FALSE");
    } else if (n.conditionType === "NOT") {
      const childResults = (n.children ?? []).map(visit);
      result = kleeneNot(childResults[0] ?? "UNKNOWN");
    } else {
      result = leafResults[n.id] ?? "UNKNOWN";
    }
    results[n.id] = result;
    return result;
  }

  visit(node);
  return results;
}

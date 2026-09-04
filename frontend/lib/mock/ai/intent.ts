// Lisa natural-language intent resolution — a thin, deterministic layer
// ahead of the existing answerQuestion() catch-all in engine.ts. This file
// contains ZERO business logic and ZERO domain calculations: it only
// classifies free text into one of a fixed set of intents with a
// confidence score, using term-group matching. Every intent handler in
// engine.ts that consumes this classification calls an EXISTING canonical
// analytics function (getFleetMaintenanceDue, getAogRecoveryAnalysis,
// getReleaseReadinessForWorkOrder, etc.) — this module never duplicates
// what those functions already compute.
//
// Why this exists: the ~150 exact/substring branches already in
// answerQuestion() cover the SUGGESTED questions well, but a real user
// typing "How do I handle the critical priority items smartly?" doesn't
// hit any of them and previously fell straight to a generic
// "I can't answer this" response — even though the intent (operational
// priority) is perfectly answerable from existing data. This resolver is
// consulted ONLY as a fallback, after every existing branch has already
// had a chance to match — so it can never change the answer to a phrase
// that already worked, only rescue phrasings that previously dead-ended.

export type LisaIntent =
  | "WORK_ORDER_PRIORITY"
  | "OVERDUE_MAINTENANCE"
  | "DUE_SOON_MAINTENANCE"
  | "AIRCRAFT_HEALTH"
  | "AOG_RECOVERY"
  | "RELEASE_READINESS"
  | "INSPECTION_RII"
  | "TECHNICIAN_AUTHORIZATION"
  | "DEFERRED_MEL"
  | "EVIDENCE"
  | "PARTS_MATERIAL"
  | "TRACEABILITY"
  | "UTILIZATION"
  | "MAINTENANCE_PROGRAM"
  | "COMPLIANCE"
  | "AUDIT"
  | "AUTOMATION"
  | "PROJECT"
  | "TAT_STATUS";

export interface IntentMatch {
  intent: LisaIntent;
  confidence: number; // 0-1, relative score among candidates, not a probability
  matchedTerms: string[];
}

interface IntentDefinition {
  intent: LisaIntent;
  // Multi-word phrases score higher than single terms — a phrase match is
  // strong evidence, a lone term is weak evidence on its own.
  phrases: string[];
  terms: string[];
  // Terms that argue AGAINST this intent when another intent's phrase/term
  // is also present — keeps "parts" from stealing "who can work on this
  // part" (technician) style overlaps down to a manageable few cases.
  negativeTerms?: string[];
}

const INTENT_DEFINITIONS: IntentDefinition[] = [
  {
    intent: "WORK_ORDER_PRIORITY",
    phrases: ["work order", "work orders", "need attention", "needs attention", "what should i", "what needs my attention", "do first", "focus on", "operational problem", "biggest problem"],
    terms: ["job", "jobs", "task", "tasks", "backlog", "priority", "critical", "urgent", "important", "immediate", "prioritize", "prioritise", "smartly", "smart", "handle", "deal with", "today"],
  },
  {
    intent: "OVERDUE_MAINTENANCE",
    phrases: ["past due", "behind on", "fell behind"],
    terms: ["overdue", "late", "missed", "expired", "behind"],
  },
  {
    intent: "DUE_SOON_MAINTENANCE",
    phrases: ["due soon", "coming due", "coming up", "next maintenance", "prepare for"],
    terms: ["upcoming", "approaching", "scheduled", "pending"],
  },
  {
    intent: "AIRCRAFT_HEALTH",
    phrases: ["aircraft health", "aircraft status", "fleet health", "operational status", "how is", "at risk", "why is", "what's wrong", "what is wrong", "anything wrong", "what's stopping", "what is stopping"],
    terms: ["condition", "risk", "flagged", "problem", "problems", "wrong"],
  },
  {
    intent: "AOG_RECOVERY",
    phrases: ["aircraft on ground", "return to service", "get back", "get aircraft back", "recovery plan", "recovery blocker"],
    terms: ["aog", "grounded", "recovery", "recover"],
  },
  {
    intent: "RELEASE_READINESS",
    phrases: ["release ready", "ready for release", "why can't we release", "why cant we release", "blocking release", "return to service", "what's blocking", "what is blocking"],
    terms: ["release", "rts", "blocking", "blocked"],
    negativeTerms: ["release the part", "vendor"],
  },
  {
    intent: "INSPECTION_RII",
    phrases: ["independent inspection", "who needs to inspect", "inspection status", "inspection required"],
    terms: ["inspection", "inspect", "rii", "inspector"],
  },
  {
    intent: "TECHNICIAN_AUTHORIZATION",
    phrases: ["who can work", "who can perform", "who is qualified", "who is authorized", "authorized technician", "certified technician"],
    terms: ["technician", "mechanic", "qualified", "authorized", "certified"],
  },
  {
    intent: "DEFERRED_MEL",
    phrases: ["deferred item", "deferred items", "what is deferred", "blocking closure"],
    terms: ["deferred", "deferral", "mel", "limitation", "closure"],
  },
  {
    intent: "EVIDENCE",
    phrases: ["missing evidence", "rejected evidence", "pending evidence", "upload evidence", "task evidence"],
    terms: ["evidence", "photo", "proof"],
  },
  {
    intent: "PARTS_MATERIAL",
    phrases: ["holding this up", "holding it up", "what parts", "missing part"],
    terms: ["part", "parts", "material", "materials", "shortage", "stock", "unavailable", "component", "spare", "procurement", "purchase", "supplier"],
  },
  {
    intent: "TRACEABILITY",
    phrases: ["serial number", "part number", "component history", "part history"],
    terms: ["traceability", "installed", "removed", "quarantine", "quarantined"],
  },
  {
    intent: "UTILIZATION",
    phrases: ["flight hours", "flight cycles", "flying hours", "cycles flown"],
    terms: ["utilization", "utilisation", "usage"],
  },
  {
    intent: "MAINTENANCE_PROGRAM",
    phrases: ["maintenance program", "maintenance requirement", "calendar interval", "maintenance interval", "maintenance status"],
    terms: ["interval"],
  },
  {
    intent: "COMPLIANCE",
    phrases: ["overdue regulatory", "non-compliant", "non compliant"],
    terms: ["compliance", "regulatory", "regulation", "applicability", "assessment"],
  },
  {
    intent: "AUDIT",
    phrases: ["who changed", "who uploaded", "who reviewed", "audit trail"],
    terms: ["audit", "ledger"],
  },
  {
    intent: "AUTOMATION",
    phrases: ["automation queue", "what can be automated", "approval queue"],
    terms: ["automation", "automated"],
  },
  {
    intent: "PROJECT",
    phrases: ["remaining work", "resource utilization", "project status", "project risk"],
    terms: ["project", "progress"],
  },
  {
    intent: "TAT_STATUS",
    phrases: ["turnaround time", "tat risk", "tat status", "miss tat", "missing tat", "what's delaying", "what is delaying", "taking so long", "taking this long", "at risk of missing"],
    terms: ["tat", "turnaround", "delaying"],
  },
];

export function normalizeQuestion(question: string): string {
  return question.toLowerCase().trim().replace(/\s+/g, " ");
}

export function resolveLisaIntent(question: string): IntentMatch[] {
  const q = normalizeQuestion(question);
  const scored: IntentMatch[] = [];

  for (const def of INTENT_DEFINITIONS) {
    let score = 0;
    const matched: string[] = [];
    for (const phrase of def.phrases) {
      if (q.includes(phrase)) {
        score += 3;
        matched.push(phrase);
      }
    }
    for (const term of def.terms) {
      if (q.includes(term)) {
        score += 1;
        matched.push(term);
      }
    }
    if (def.negativeTerms) {
      for (const neg of def.negativeTerms) {
        if (q.includes(neg)) score -= 2;
      }
    }
    if (score > 0) scored.push({ intent: def.intent, confidence: score, matchedTerms: matched });
  }

  // Normalize confidence to 0-1 relative to the top score so callers can
  // reason about "is this a clear winner or ambiguous" without knowing the
  // raw scoring scale.
  const max = Math.max(...scored.map((s) => s.confidence), 1);
  return scored.map((s) => ({ ...s, confidence: s.confidence / max })).sort((a, b) => b.confidence - a.confidence);
}

/** Human-readable domain label for the "Lisa Understood" transparency
 * panel — never exposes function names or internal identifiers. */
export const INTENT_LABEL: Record<LisaIntent, string> = {
  WORK_ORDER_PRIORITY: "Operational Priority",
  OVERDUE_MAINTENANCE: "Overdue Maintenance",
  DUE_SOON_MAINTENANCE: "Upcoming Maintenance",
  AIRCRAFT_HEALTH: "Aircraft Health",
  AOG_RECOVERY: "AOG Recovery",
  RELEASE_READINESS: "Release Readiness",
  INSPECTION_RII: "Inspection / Independent Inspection",
  TECHNICIAN_AUTHORIZATION: "Technician Authorization",
  DEFERRED_MEL: "Deferred Item / MEL",
  EVIDENCE: "Execution Evidence",
  PARTS_MATERIAL: "Parts / Material",
  TRACEABILITY: "Part Traceability",
  UTILIZATION: "Aircraft Utilization",
  MAINTENANCE_PROGRAM: "Maintenance Program",
  COMPLIANCE: "Regulatory Compliance",
  AUDIT: "Audit History",
  AUTOMATION: "Automation Queue",
  PROJECT: "Project Status",
  TAT_STATUS: "Turnaround Time (TAT)",
};

export const INTENT_DATA_AREAS: Record<LisaIntent, string> = {
  WORK_ORDER_PRIORITY: "Work Order Planning · Release Readiness · AOG",
  OVERDUE_MAINTENANCE: "Maintenance Due Engine",
  DUE_SOON_MAINTENANCE: "Maintenance Due Engine",
  AIRCRAFT_HEALTH: "Control Tower · Defects · Work Orders",
  AOG_RECOVERY: "AOG Recovery Orchestration",
  RELEASE_READINESS: "Release Readiness Engine",
  INSPECTION_RII: "Inspection / RII Engine",
  TECHNICIAN_AUTHORIZATION: "Technician Authorization Matrix",
  DEFERRED_MEL: "Deferred / MEL Operations",
  EVIDENCE: "Execution Evidence Records",
  PARTS_MATERIAL: "Material Readiness · Procurement",
  TRACEABILITY: "Part Traceability Engine",
  UTILIZATION: "Aircraft Utilization Intelligence",
  MAINTENANCE_PROGRAM: "Maintenance Program / Due Engine",
  COMPLIANCE: "Applicability / Compliance Assessments",
  AUDIT: "Audit Trail",
  AUTOMATION: "Automation Queue",
  PROJECT: "Project Analytics",
  TAT_STATUS: "Work Order Due Dates · Release Readiness",
};

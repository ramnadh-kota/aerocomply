// Mock AI orchestration layer. NOT a real LLM and NOT a backend call — this
// matches keywords in the question against existing mock data and the
// analytics builders in ./analytics.ts, then returns a structured response
// for AIResponseView to render. The matching logic here is intentionally the
// only thing that would be swapped out for a real AI/LLM service later; the
// analytics functions and response shape would not need to change.
//
// Trust model (see docs/adr ADR-004 and this phase's Part 10): the assistant
// only explains, summarizes, compares, ranks, and highlights risk. It never
// approves/rejects a compliance decision, never turns UNKNOWN into FALSE, and
// reports INSUFFICIENT_DATA rather than guessing when the mock data can't
// answer the question.

import { maintenanceProjects, getProjectById } from "../maintenanceProjects";
import { aircraft, getAircraftByRegistration, getAircraftById, currentRegistration } from "../aircraft";
import { workOrders, isOverdue, workOrdersForAircraft } from "../workOrders";
import { findings, findingsForWorkOrder } from "../findings";
import { defects, defectsForAircraft, defectsForWorkOrder } from "../defects";
import { getInspectorReviewForWorkOrder } from "../inspectorReviews";
import { getChecklistByWorkOrderId } from "../checklists";
import { evidenceForAssessment } from "../evidence";
import { overdueMaintenanceEvents, maintenanceEventsForAircraft, upcomingMaintenanceEvents } from "../maintenance";
import { assessments } from "../assessments";
import { getTechnicianById } from "../technicians";
import { partsForWorkOrder, parts } from "../parts";
import { certificatesForPart, traceabilityStatusForPart, partLifecycleStage, partTraceabilityAnswers } from "../partTraceability";
import { getWorkOrderCostSummary, getAircraftCostSummary, getFleetFinancialSummary, workOrderIdsWithCostData, highestCostPartCost, highestVendorSpend, vendorCosts } from "../finance";
import { vendors, partRequests, purchaseOrders, partsWithoutVendorAvailability, scoreVendorOptionsForPart, cartItems, cartSummary, cartItemLineTotal, getVendorById } from "../procurement";
import { auditEvents, combinedAuditHistory } from "../audit";
import type { AuditEvent } from "../types";
import { AI_DEMO_DATA_FOOTER } from "../../brand";
import {
  getProjectAnalytics,
  getAircraftAnalytics,
  getMaintenanceAnalytics,
  getComplianceAnalytics,
  getInspectionAnalytics,
  getFleetAnalytics,
  getTechnicianWorkload,
  getPartsAtRisk,
  assessmentDiffSummary,
  assessmentUnknownReasons,
  requirementLabel,
  getControlTowerFleet,
  getControlTowerSummary,
  getAircraftOperationalRisk,
  getDiscrepancyGroups,
  getDiscrepancyGroupAnalysis,
  getWorkOrderPlanning,
  getWorkOrderPlanningSummary,
  getWorkOrderPlanningRow,
  getMaterialBlockedWorkOrders,
  getReadyToStartWorkOrders,
  getTechnicianAssignmentRecommendation,
  getNextMaintenanceActions,
  getMaterialReadinessRows,
  getMaterialReadinessSummary,
  getAircraftMaterialReadiness,
  getWorkOrderMaterialReadiness,
  getMaterialShortages,
  getProcurementActionsForShortages,
  getMaintenanceControlCenter,
  getMaintenanceControlCenterSummary,
  getTechnicianEligibilityForWorkOrder,
  getExecutionQueue,
  getWorkOrdersAwaitingAssignment,
  getExecutionState,
  getSafetyGatesForWorkOrder,
  getEligibleInspectorsForWorkOrder,
  getQuarantinedParts,
  getDeferredItemsForAircraft,
  getCannibalizationCandidatesForAircraft,
  getAogRecoveryAnalysis,
  getMaintenanceForecastForAircraft,
  type KpiCard,
  type RiskItem,
} from "./analytics";

/** Context carried from the calling page (e.g. Project Intelligence) so a
 * question that doesn't name a project/aircraft explicitly still resolves to
 * the one the user is looking at — no new state, just an optional parameter
 * on the existing engine entry point. */
export interface AiQuestionContext {
  projectId?: string;
  aircraftId?: string;
  /** M12.7 — this session's live audit events (useMroState().auditLog), so
   * Lisa's traceability answers see the same mutations the UI does. When
   * omitted (e.g. server-rendered callers), falls back to the static seed
   * log only — never a second audit calculation. */
  auditLog?: AuditEvent[];
}

export interface AiButton {
  label: string;
  href: string;
}

export interface AiResponse {
  id: string;
  question: string;
  headline: string;
  narrative: string[];
  insufficientData?: boolean;
  missing?: string[];
  kpis?: KpiCard[];
  bars?: { title: string; items: { label: string; percent: number }[] };
  distribution?: { title: string; items: { label: string; count: number }[] };
  risks?: RiskItem[];
  complianceChain?: string[];
  recommendedActions?: string[];
  table?: { title: string; columns: string[]; rows: (string | number)[][] };
  buttons?: AiButton[];
  suggestGenerateReport?: { reportId: string; title: string; scope: string };
}

export interface QuestionCategory {
  category: string;
  questions: string[];
}

export const CATEGORIZED_QUESTIONS: QuestionCategory[] = [
  {
    category: "Project",
    questions: [
      "Analyze C-Check Project P-001",
      "What is putting this project at risk?",
      "Show project progress and remaining work.",
      "Show resource utilization for this project.",
    ],
  },
  {
    category: "Aircraft",
    questions: [
      "Give me a health analysis of VT-ABC.",
      "What maintenance actions are due for VT-ABC?",
      "What defects does VT-ABC have?",
      "What is the inspection status for VT-ABC?",
    ],
  },
  {
    category: "Maintenance",
    questions: [
      "Which work orders need attention?",
      "Show the work order backlog.",
      "Which parts are at risk?",
      "Show technician workload.",
      "Show me overdue maintenance activities.",
      "What findings have been recorded?",
    ],
  },
  {
    category: "Compliance",
    questions: [
      "Which aircraft have compliance risk?",
      "Show overdue regulatory actions.",
      "Why is this assessment UNKNOWN?",
      "What regulatory deadlines are coming up?",
      "What is our compliance health?",
      "Which assessments are non-compliant?",
      "Which assessments have evidence gaps?",
    ],
  },
  {
    category: "Inspection",
    questions: [
      "Prioritize the inspection queue.",
      "Which inspections are blocked?",
      "Show inspection aging.",
      "Which checklist items have failed?",
    ],
  },
  {
    category: "Fleet",
    questions: ["What is the health of the fleet?", "Show the aircraft risk ranking."],
  },
  {
    category: "Prescriptive",
    questions: [
      "What is the TAT risk for this work order?",
      "Which parts are at risk?",
      "Which assessments have evidence gaps?",
      "What AMM reference applies here?",
      "What should happen next for this work order?",
    ],
  },
  {
    category: "Finance",
    questions: [
      "Which aircraft is most expensive to maintain?",
      "How much did VT-ABC cost us?",
      "What is our margin?",
      "Which vendors cost us the most?",
      "Which work orders are losing money?",
      "Generate a financial report.",
    ],
  },
  {
    category: "Procurement",
    questions: [
      "Which vendor should we use for HP-442?",
      "Which parts have insufficient supplier data?",
      "Which AOG parts need immediate attention?",
      "Which vendor has the best delivery performance?",
      "What should procurement do next?",
      "What is in my procurement cart?",
    ],
  },
  {
    category: "Maintenance Control Tower",
    questions: [
      "Which aircraft is most at risk?",
      "Which aircraft are currently AOG?",
      "What discrepancies are recurring?",
      "Which discrepancy is the most common?",
      "Which aircraft has the most open discrepancies?",
      "What should maintenance do next?",
      "Give me today's maintenance operational report.",
    ],
  },
  {
    category: "Maintenance Planning",
    questions: [
      "Which work orders should maintenance do first?",
      "Which work orders are blocked?",
      "Which work orders are ready to start?",
      "Which work orders are blocked by materials?",
      "Which work orders need technician assignment?",
      "What should maintenance work on next?",
      "Why is WO-1042 blocked?",
      "Which aircraft has the highest maintenance priority?",
      "Which work order is most urgent?",
      "Show me today's maintenance priorities.",
      "Recommend a technician for WO-1042.",
    ],
  },
  {
    category: "Material Readiness",
    questions: [
      "What materials are blocking maintenance?",
      "Which work orders are waiting for parts?",
      "Which aircraft have material shortages?",
      "What parts do I need to procure?",
      "Which shortage should procurement handle first?",
      "Can I procure the part for WO-1042?",
      "What is the material readiness of N412MX?",
      "Which parts have known vendor availability?",
      "What should maintenance do about material shortages?",
    ],
  },
  {
    category: "Maintenance Control Center",
    questions: [
      "What needs attention right now?",
      "Which aircraft need immediate attention?",
      "What are the biggest maintenance blockers?",
      "Which work orders are blocked?",
      "What is preventing maintenance from progressing?",
      "Which aircraft have material issues?",
      "Which discrepancies need attention?",
      "What should maintenance prioritize?",
      "Give me the maintenance control report.",
      "Why is N412MX high risk?",
    ],
  },
  {
    category: "Maintenance Execution",
    questions: [
      "Who should handle WO-1051?",
      "Which technician is best suited for this work order?",
      "Why was this technician recommended?",
      "Which work orders are waiting for technician assignment?",
      "Which work orders are blocked by materials?",
      "What can maintenance complete today?",
      "What needs escalation?",
      "What should the planner do next?",
      "Show technician workload.",
      "Which aircraft have work orders that need action?",
    ],
  },
  {
    category: "Maintenance Traceability",
    questions: [
      "What happened to WO-1051?",
      "Who assigned the technician?",
      "When was WO-1046 escalated?",
      "Why was this work order escalated?",
      "Who reassigned this technician?",
      "Show the history of WO-1051.",
      "What maintenance actions happened recently?",
      "What changed on this work order?",
      "Who made the latest maintenance decision?",
      "Show me the audit trail for this aircraft.",
    ],
  },
  {
    category: "AOG Recovery",
    questions: [
      "How can we recover N412MX?",
      "What is blocking the AOG recovery for N412MX?",
    ],
  },
  {
    category: "Safety & Release",
    questions: [
      "What is the release status of WO-1054?",
      "What safety gates are open on WO-1055?",
      "Who can independently inspect WO-1042?",
      "Which parts are quarantined?",
      "What is the deferred status of VT-ABC?",
      "Is there a cannibalization candidate for N412MX?",
      "Is this aircraft airworthy?",
    ],
  },
];

export const SUGGESTED_QUESTIONS = CATEGORIZED_QUESTIONS.flatMap((c) => c.questions);

let counter = 0;
function nextId(): string {
  counter += 1;
  return `ai-resp-${counter}`;
}

function findProjectFromText(text: string) {
  const byNumber = maintenanceProjects.find((p) => text.toUpperCase().includes(p.projectNumber.toUpperCase()));
  if (byNumber) return byNumber;
  const byId = maintenanceProjects.find((p) => text.toLowerCase().includes(p.id));
  if (byId) return byId;
  return undefined;
}

function findAircraftFromText(text: string) {
  // Matches both hyphenated (e.g. "VT-ABC") and non-hyphenated (e.g.
  // "N412ML") registration marks. The previous pattern (`[A-Z0-9]{4,7}`)
  // could never match a hyphenated mark — the hyphen splits it into two
  // sub-4-character tokens — which meant every hyphenated aircraft in the
  // fleet (VT-ABC, VT-XYZ, VT-DEF, VT-GHI, VT-JKL — including both hero
  // aircraft named in the suggested questions) silently failed to resolve
  // and fell through to INSUFFICIENT_DATA on every question naming them.
  const tokens = text.toUpperCase().match(/[A-Z0-9]{2,4}-[A-Z0-9]{2,4}|[A-Z0-9]{4,7}/g) ?? [];
  for (const t of tokens) {
    const a = getAircraftByRegistration(t);
    if (a) return a;
  }
  return undefined;
}

function findWorkOrderFromText(text: string) {
  const match = text.toUpperCase().match(/WO-?(\d{3,4})/);
  if (!match) return undefined;
  const num = `WO-${match[1]}`;
  return workOrders.find((w) => w.workOrderNumber.toUpperCase() === num);
}

function findAssessmentIdsFromText(text: string): string[] {
  const matches = text.toLowerCase().match(/asmt-[a-z0-9-]+/g);
  return matches ?? [];
}

/** Prefer a project explicitly named in the question; otherwise fall back to
 * the caller's context (e.g. Project Intelligence page); otherwise the demo
 * default. Keeps the existing "always answer something" behavior. */
function resolveProject(text: string, context?: AiQuestionContext) {
  return findProjectFromText(text) ?? (context?.projectId ? getProjectById(context.projectId) : undefined) ?? maintenanceProjects[0];
}

function resolveAircraft(text: string, context?: AiQuestionContext) {
  return findAircraftFromText(text) ?? (context?.aircraftId ? getAircraftById(context.aircraftId) : undefined);
}

const TRUST_FOOTER = AI_DEMO_DATA_FOOTER;

function insufficient(question: string, missing: string[]): AiResponse {
  return {
    id: nextId(),
    question,
    headline: "INSUFFICIENT_DATA",
    narrative: [
      "I can't answer this from the current demo dataset.",
      `Missing: ${missing.join("; ")}.`,
      TRUST_FOOTER,
    ],
    insufficientData: true,
    missing,
  };
}

// M12.9 — Lisa must never make a final airworthiness/legal/regulatory
// determination itself; those decisions belong to authorized maintenance
// personnel. This guard sits ahead of every other branch so no keyword match
// below it can accidentally produce an authoritative-sounding answer to one
// of these questions.
const AIRWORTHINESS_GUARD_PATTERNS = [
  /\bairworth/i,
  /\bsafe to dispatch\b/i,
  /\bsafe to fly\b/i,
  /\bapproved substitute\b/i,
  /\blegally (complete|compliant|authorized)\b/i,
  /\bcertificate of release\b/i,
  /\bcrs\b/i,
  /\brelease( it| the aircraft)? to service\b/i,
];

function answerAirworthinessGuard(question: string): AiResponse | null {
  if (!AIRWORTHINESS_GUARD_PATTERNS.some((p) => p.test(question))) return null;
  return {
    id: nextId(),
    question,
    headline: "SAFETY_REFUSAL — this requires authorized maintenance personnel",
    narrative: [
      "SAFETY_REFUSAL: I cannot determine airworthiness, legal compliance, or certification of release — those are determinations for authorized maintenance personnel using applicable approved data and procedures, not this system.",
      "The system can summarize recorded facts: aircraft/work order status, open safety gates, and open discrepancies.",
      "Ask about a specific aircraft or work order's recorded execution state, safety gates, or open discrepancies, and I can summarize what the current data shows.",
      TRUST_FOOTER,
    ],
  };
}

export function answerQuestion(question: string, context?: AiQuestionContext): AiResponse {
  const guard = answerAirworthinessGuard(question);
  if (guard) return guard;
  const q = question.toLowerCase();

  // "What is the execution/release status of WO-XXXX?" / "Is WO-XXXX released?"
  // / "What safety gates are open on WO-XXXX?" — M12.9. Explicit FACT /
  // INFERENCE / RECOMMENDATION structure, reusing getExecutionState and
  // getSafetyGatesForWorkOrder (lib/mock/ai/analytics.ts) so this can never
  // disagree with the Planning detail page rendering the same functions.
  if ((q.includes("release") || q.includes("safety gate") || q.includes("execution status")) && findWorkOrderFromText(question)) {
    const wo = findWorkOrderFromText(question)!;
    const execState = getExecutionState(wo);
    const gates = getSafetyGatesForWorkOrder(wo.id);
    const openGates = gates.filter((g) => g.open);
    const narrative: string[] = [
      `FACT: ${wo.workOrderNumber} status is ${wo.status.replace(/_/g, " ")}; derived execution state is ${execState.replace(/_/g, " ")}.`,
    ];
    if (openGates.length > 0) {
      const unknownGates = openGates.filter((g) => g.state === "UNKNOWN");
      narrative.push(`FACT: ${openGates.length} safety gate(s) currently open: ${openGates.map((g) => `${g.type.replace(/_/g, " ")} (${g.state})`).join(", ")}.`);
      if (unknownGates.length > 0) narrative.push(`UNKNOWN: ${unknownGates.map((g) => g.type.replace(/_/g, " ")).join(", ")} cannot be evaluated from current source data — UNKNOWN is never treated as PASS.`);
      narrative.push(`INFERENCE: this work order is not yet ready for release while these gates remain open.`);
      narrative.push(`RECOMMENDATION: resolve ${openGates[0].type.replace(/_/g, " ").toLowerCase()} first — ${openGates[0].reason}`);
    } else {
      narrative.push("FACT: no safety gate is currently open for this work order.");
    }
    narrative.push("SAFETY_REFUSAL: final release/airworthiness determination requires authorized maintenance personnel — this is a summary of recorded system data, not a certification.");
    narrative.push(TRUST_FOOTER);
    return {
      id: nextId(),
      question,
      headline: `${wo.workOrderNumber} — execution state: ${execState.replace(/_/g, " ")}`,
      narrative,
      table: { title: "Safety Gates", columns: ["Gate", "State", "Reason"], rows: gates.map((g) => [g.type.replace(/_/g, " "), g.state, g.reason]) },
      buttons: [{ label: "Open Planning View", href: `/maintenance/planning/${wo.id}` }],
    };
  }

  // "How can we recover N412MX?" / "What is blocking the AOG recovery?" —
  // M14.1. Reuses getAogRecoveryAnalysis (lib/mock/ai/analytics.ts), the
  // ONE AOG recovery calculation, also rendered by the recovery detail page
  // — this can never disagree with what a human sees there.
  if ((q.includes("recover") || (q.includes("aog") && (q.includes("block") || q.includes("next")))) && resolveAircraft(question, context)) {
    const a = resolveAircraft(question, context)!;
    const analysis = getAogRecoveryAnalysis(a.id);
    if (!analysis) return insufficient(question, ["aircraft data"]);
    if (!analysis.isAog) {
      return {
        id: nextId(),
        question,
        headline: `${analysis.registration} — not currently AOG`,
        narrative: [`FACT: ${analysis.registration} is not currently derived as AOG (no open HIGH/CRITICAL defect on file).`, TRUST_FOOTER],
        buttons: [{ label: "View Aircraft", href: `/aircraft/${a.id}` }],
      };
    }
    const narrative: string[] = [
      `FACT: ${analysis.registration} is AOG — ${analysis.aogReason ?? "Insufficient source data."}`,
      `FACT: ${analysis.criticalWorkOrders.length} critical/high-priority open work order(s): ${analysis.criticalWorkOrders.map((w) => w.workOrderNumber).join(", ") || "none"}.`,
    ];
    if (analysis.primaryBlocker) {
      narrative.push(`FACT: primary blocker is ${analysis.primaryBlocker.type} — ${analysis.primaryBlocker.description} (source: ${analysis.primaryBlocker.source}).`);
      narrative.push(`INFERENCE: recovery cannot proceed past this blocker until it is resolved.`);
      narrative.push(`RECOMMENDATION: ${analysis.recoveryOptions[0]?.action ?? "escalate to maintenance manager"}.`);
    } else {
      narrative.push("UNKNOWN: no specific safety-gate or deferred-item blocker is identified from current source data, despite AOG status — investigate manually.");
    }
    if (analysis.dataCompleteness !== "COMPLETE") narrative.push(`UNKNOWN: recovery data completeness is ${analysis.dataCompleteness} — some blockers may not be identifiable from current records.`);
    narrative.push("SAFETY_REFUSAL: this system does not authorize or execute recovery actions — every option requires human approval through the existing workflow.");
    narrative.push(TRUST_FOOTER);
    return {
      id: nextId(),
      question,
      headline: `${analysis.registration} — AOG recovery analysis`,
      narrative,
      table: { title: "Recovery Options", columns: ["Action", "Responsible Role"], rows: analysis.recoveryOptions.map((o) => [o.action, o.responsibleRole]) },
      buttons: [{ label: "Open Recovery View", href: `/maintenance/aog-recovery/${a.id}` }, { label: "Open Control Tower", href: "/maintenance/control-tower" }],
    };
  }

  // "What maintenance is coming due for VT-ABC?" — M14.4 utilization
  // forecasting foundation. Honest by construction: this dataset has no
  // seeded FH/FC threshold on any task, so this always reports UNKNOWN
  // today rather than fabricating a due date.
  if (q.includes("coming due") || (q.includes("due") && q.includes("maintenance") && resolveAircraft(question, context))) {
    const a = resolveAircraft(question, context);
    if (!a) return insufficient(question, ["a recognizable aircraft registration, e.g. VT-ABC"]);
    const forecast = getMaintenanceForecastForAircraft(a.id);
    return {
      id: nextId(),
      question,
      headline: `${currentRegistration(a)} — maintenance forecast`,
      narrative: [
        forecast.length > 0 ? `FACT: ${forecast.length} maintenance task(s) linked to open work on this aircraft.` : "FACT: no maintenance task is currently linked to open work on this aircraft.",
        "UNKNOWN: no maintenance-interval threshold (FH/FC/calendar) exists in this dataset for any task, so due status cannot be calculated — this is a forecasting foundation, not a working forecast yet.",
        TRUST_FOOTER,
      ],
      table: { title: "Maintenance Forecast", columns: ["Task", "Due Status", "Reason"], rows: forecast.map((f) => [f.taskDescription, f.dueStatus, f.reason]) },
      buttons: [{ label: "View Aircraft", href: `/aircraft/${a.id}` }],
    };
  }

  // "Who can independently inspect WO-XXXX?" — M13 RII enforcement: the
  // assigned technician is never eligible to inspect their own work.
  if ((q.includes("independently inspect") || q.includes("who can inspect")) && findWorkOrderFromText(question)) {
    const wo = findWorkOrderFromText(question)!;
    const eligible = getEligibleInspectorsForWorkOrder(wo.id);
    const assignedTech = wo.assignedTechnicianId ? getTechnicianById(wo.assignedTechnicianId) : undefined;
    return {
      id: nextId(),
      question,
      headline: eligible.length > 0 ? `${wo.workOrderNumber} — ${eligible.length} eligible independent inspector(s)` : `${wo.workOrderNumber} — no eligible independent inspector identified`,
      narrative: [
        assignedTech ? `FACT: ${assignedTech.name} performed/is assigned this work and cannot independently inspect it.` : "FACT: no technician is currently assigned to this work order.",
        eligible.length > 0
          ? `FACT: eligible inspector(s): ${eligible.map((e) => `${e.name} (${e.availability})`).join(", ")}.`
          : "UNKNOWN: no technician other than the one assigned is currently marked as an inspector in this dataset.",
        TRUST_FOOTER,
      ],
      buttons: [{ label: "Open Planning View", href: `/maintenance/planning/${wo.id}` }],
    };
  }

  // "Trace part FCU-220" / "where did this part come from" — M14.6.
  // Reuses the existing M7.1/M8.7 traceability functions (never a second
  // traceability calculation) — origin, certificate, installation, removal,
  // and lifecycle stage, all "Insufficient source data." where no record
  // exists rather than guessed.
  if ((q.includes("trace") || q.includes("where did") || q.includes("origin of")) && parts.find((p) => q.includes(p.partNumber.toLowerCase()))) {
    const part = parts.find((p) => q.includes(p.partNumber.toLowerCase()))!;
    const answers = partTraceabilityAnswers(part.id);
    const stage = partLifecycleStage(part.id);
    const narrative = [
      `FACT: Origin — ${answers.origin}`,
      `FACT: Certificate — ${answers.supportingCertificate}`,
      `FACT: Installed aircraft — ${answers.installedAircraft}`,
      `FACT: Removal — ${answers.removalInfo}`,
    ];
    // M14.7 — rotable lifecycle foundation. A ROTABLE part's full
    // REMOVED→QUARANTINE→SHOP→REPAIR→INSPECTION→SERVICEABLE lifecycle is
    // NOT tracked in this dataset (no shop/repair-order records exist) —
    // partLifecycleStage only covers the receiving/install/remove portion.
    if (part.aviationClassification === "ROTABLE") {
      narrative.push(`FACT: classification is ROTABLE — current lifecycle stage: ${stage.replace(/_/g, " ")}.`);
      narrative.push("UNKNOWN: shop/repair-cycle stages (quarantine → shop → repair → inspection → serviceable) are not tracked in this dataset — only receiving, installation, and removal are.");
    }
    narrative.push(TRUST_FOOTER);
    return {
      id: nextId(),
      question,
      headline: `${part.partNumber} — traceability (lifecycle stage: ${stage.replace(/_/g, " ")})`,
      narrative,
      buttons: [{ label: "View Parts", href: "/maintenance/parts" }],
    };
  }

  // "Which parts are quarantined?" — M13 receiving/quarantine foundation.
  if (q.includes("quarantin")) {
    const quarantined = getQuarantinedParts();
    return {
      id: nextId(),
      question,
      headline: `${quarantined.length} part(s) currently quarantined`,
      narrative: [quarantined.length > 0 ? "FACT: these parts are physically received but not serviceable pending disposition." : "FACT: no part is currently recorded as quarantined.", TRUST_FOOTER],
      table: { title: "Quarantined Parts", columns: ["Part", "Description", "Reason"], rows: quarantined.map((p) => [p.partNumber, p.description, p.reason]) },
      buttons: [{ label: "Open Parts", href: "/maintenance/parts" }],
    };
  }

  // "What is the MEL/deferred status of VT-ABC?" — M13 MEL foundation.
  // Deliberately never invents a countdown/deadline.
  if ((q.includes("mel") || q.includes("deferred")) && resolveAircraft(question, context)) {
    const a = resolveAircraft(question, context)!;
    const items = getDeferredItemsForAircraft(a.id);
    return {
      id: nextId(),
      question,
      headline: `${currentRegistration(a)} — ${items.length} deferred item(s)`,
      narrative: [
        items.length > 0
          ? `FACT: ${items.length} deferred item(s) recorded.`
          : "FACT: no deferred item is currently recorded for this aircraft.",
        ...items.filter((i) => i.dueAt === null).map(() => "UNKNOWN: no authoritative MEL reference or due date exists in this dataset for at least one deferred item — never presented as an invented deadline."),
        TRUST_FOOTER,
      ],
      table: { title: "Deferred Items", columns: ["Category", "MEL Reference", "Due", "Status"], rows: items.map((i) => [i.category, i.melReference ?? "Insufficient source data.", i.dueAt ?? "UNKNOWN", i.status]) },
      buttons: [{ label: "View Aircraft", href: `/aircraft/${a.id}` }],
    };
  }

  // "Is there a cannibalization candidate for N412MX?" — M13 foundation.
  // Never authorizes anything; always routes to human review.
  if (q.includes("cannibaliz") && resolveAircraft(question, context)) {
    const a = resolveAircraft(question, context)!;
    const candidates = getCannibalizationCandidatesForAircraft(a.id);
    if (candidates.length === 0) return insufficient(question, [`a recorded cannibalization candidate for ${currentRegistration(a)}`]);
    const c = candidates[0];
    return {
      id: nextId(),
      question,
      headline: `${currentRegistration(a)} — cannibalization candidate identified (pending human review)`,
      narrative: [
        `FACT: ${c.reason}`,
        `FACT: traceability status is ${c.traceabilityStatus} — ${c.traceabilityStatus === "UNKNOWN" ? "the source part is not confirmed installed on the donor aircraft in current records." : "the source part record is confirmed."}`,
        "SAFETY_REFUSAL: this system does not authorize cannibalization — authorization status stays PENDING_HUMAN_REVIEW until an authorized person acts.",
        TRUST_FOOTER,
      ],
      buttons: [{ label: "View Aircraft", href: `/aircraft/${a.id}` }],
    };
  }

  // --- Contextual (project-scoped) shortcuts — only apply when the caller
  // has an active project context (e.g. asked from Project Intelligence).
  // These sit ahead of the generic branches below so phrasing that doesn't
  // name the project explicitly ("which technicians are overloaded?") still
  // resolves to the project being viewed, not the fleet-wide default.
  if (context?.projectId) {
    const ctxProject = getProjectById(context.projectId);
    const ctxAnalytics = ctxProject ? getProjectAnalytics(ctxProject.id) : null;
    if (ctxProject && ctxAnalytics) {
      const projectWos = workOrders.filter((w) => w.projectId === ctxProject.id);

      if (q.includes("technician") && (q.includes("overload") || q.includes("workload"))) {
        const byTech = new Map<string, number>();
        for (const w of projectWos) {
          if (!w.assignedTechnicianId) continue;
          byTech.set(w.assignedTechnicianId, (byTech.get(w.assignedTechnicianId) ?? 0) + 1);
        }
        const rows = Array.from(byTech.entries()).map(([id, count]) => [getTechnicianById(id)?.name ?? id, count]);
        const overloaded = rows.filter(([, count]) => (count as number) > 1);
        return {
          id: nextId(),
          question,
          headline: `${ctxProject.projectNumber} — technician workload`,
          narrative: [
            overloaded.length > 0 ? `${overloaded.length} technician(s) are assigned to more than one work order on this project.` : "No technician on this project currently has more than one assigned work order.",
            TRUST_FOOTER,
          ],
          table: { title: "Technician Assignments", columns: ["Technician", "Work Orders"], rows },
          buttons: [{ label: "View Project", href: `/maintenance/projects/${ctxProject.id}` }, { label: "View Technicians", href: "/maintenance/technicians" }],
        };
      }

      if (q.includes("parts") && q.includes("risk")) {
        const woIds = new Set(projectWos.map((w) => w.id));
        const atRisk = getPartsAtRisk().filter((p) => p.workOrderId && woIds.has(p.workOrderId));
        return {
          id: nextId(),
          question,
          headline: `${ctxProject.projectNumber} — parts putting this project at risk`,
          narrative: [atRisk.length > 0 ? "These parts on this project are not currently in stock." : "No parts on this project are currently at risk.", TRUST_FOOTER],
          table: {
            title: "Parts At Risk",
            columns: ["Part", "Status", "Work Order"],
            rows: atRisk.map((p) => [p.partNumber, p.status.replace(/_/g, " "), projectWos.find((w) => w.id === p.workOrderId)?.workOrderNumber ?? "—"]),
          },
          buttons: [{ label: "View Project", href: `/maintenance/projects/${ctxProject.id}` }, { label: "View Parts", href: "/maintenance/parts" }],
        };
      }

      if ((q.includes("work order") || q.includes("work orders")) && (q.includes("caus") || q.includes("risk"))) {
        return {
          id: nextId(),
          question,
          headline: `${ctxProject.projectNumber} — work orders driving risk`,
          narrative: [ctxAnalytics.risks.length > 0 ? `${ctxAnalytics.risks.length} risk item(s) are tied to specific work orders on this project.` : "No work order on this project is currently driving risk.", TRUST_FOOTER],
          risks: ctxAnalytics.risks,
          buttons: [{ label: "View Project", href: `/maintenance/projects/${ctxProject.id}` }, { label: "View Work Orders", href: "/maintenance/work-orders" }],
        };
      }

      if (q.includes("compliance") && (q.includes("attention") || q.includes("need"))) {
        const linked = projectWos.filter((w) => w.relatedRequirementId);
        return {
          id: nextId(),
          question,
          headline: `${ctxProject.projectNumber} — compliance items needing attention`,
          narrative: [linked.length > 0 ? `${linked.length} work order(s) on this project are linked to a regulatory requirement.` : "No regulatory requirements are linked to this project's work orders.", TRUST_FOOTER],
          table: { title: "Linked Requirements", columns: ["Work Order", "Requirement"], rows: linked.map((w) => [w.workOrderNumber, requirementLabel(w.relatedRequirementId)]) },
          buttons: [{ label: "View Project", href: `/maintenance/projects/${ctxProject.id}` }, { label: "View Regulations", href: "/regulations" }],
        };
      }

      if ((q.includes("prioritize") || q.includes("priorities")) && !q.includes("inspection")) {
        return {
          id: nextId(),
          question,
          headline: `${ctxProject.projectNumber} — recommended priorities`,
          narrative: [ctxAnalytics.recommendedActions.length > 0 ? "Based on current risk factors for this project." : "No urgent action required on this project right now.", TRUST_FOOTER],
          recommendedActions: ctxAnalytics.recommendedActions,
          risks: ctxAnalytics.risks,
          buttons: [{ label: "View Project", href: `/maintenance/projects/${ctxProject.id}` }],
        };
      }

      if (q.includes("generate") && q.includes("report")) {
        return {
          id: nextId(),
          question,
          headline: `${ctxProject.projectNumber} — generate report`,
          narrative: ["The report uses the same analytics shown on this page.", TRUST_FOOTER],
          buttons: [{ label: "Generate Report", href: `/reports/project-${ctxProject.id}` }],
          suggestGenerateReport: { reportId: `project-${ctxProject.id}`, title: `${ctxProject.projectNumber} Operations Report`, scope: ctxAnalytics.title },
        };
      }
    }
  }

  // --- Contextual (aircraft-scoped) shortcuts — mirrors the project-scoped
  // block above, for pages that carry only an aircraft context (e.g. Aircraft
  // Health Intelligence) and only when no project context is also present.
  if (context?.aircraftId && !context?.projectId) {
    const ctxAircraft = getAircraftById(context.aircraftId);
    const ctxAircraftAnalytics = ctxAircraft ? getAircraftAnalytics(ctxAircraft.id) : null;
    if (ctxAircraft && ctxAircraftAnalytics) {
      if ((q.includes("prioritize") || q.includes("priorities") || q.includes("next action") || q.includes("what should")) && !q.includes("inspection")) {
        return {
          id: nextId(),
          question,
          headline: `${ctxAircraftAnalytics.registration} — recommended priorities`,
          narrative: [...ctxAircraftAnalytics.reasons, TRUST_FOOTER],
          kpis: ctxAircraftAnalytics.kpis,
          buttons: [{ label: "View Aircraft", href: `/aircraft/${ctxAircraft.id}` }, { label: "Aircraft Health Intelligence", href: `/fleet/aircraft/${ctxAircraft.id}/health` }],
        };
      }

      if (q.includes("why") && !findWorkOrderFromText(question)) {
        return {
          id: nextId(),
          question,
          headline: `${ctxAircraftAnalytics.registration} — explanation`,
          narrative: [...ctxAircraftAnalytics.reasons, TRUST_FOOTER],
          kpis: ctxAircraftAnalytics.kpis,
          buttons: [{ label: "View Aircraft", href: `/aircraft/${ctxAircraft.id}` }],
        };
      }

      if (q.includes("generate") && q.includes("report")) {
        return {
          id: nextId(),
          question,
          headline: `${ctxAircraftAnalytics.registration} — generate report`,
          narrative: ["The report uses the same analytics shown on this page.", TRUST_FOOTER],
          buttons: [{ label: "Generate Report", href: `/reports/aircraft-${ctxAircraft.id}` }],
          suggestGenerateReport: { reportId: `aircraft-${ctxAircraft.id}`, title: `${ctxAircraftAnalytics.registration} Compliance Exposure Report`, scope: ctxAircraftAnalytics.registration },
        };
      }
    }
  }

  // "What changed between assessment X and Y"
  if (q.includes("changed between") || (q.includes("assessment") && q.includes("vs"))) {
    const ids = findAssessmentIdsFromText(question);
    if (ids.length >= 2) {
      const diff = assessmentDiffSummary(ids[0], ids[1]);
      if (!diff.found) return insufficient(question, [`assessment ids "${ids[0]}" / "${ids[1]}" not found in mock data`]);
      return {
        id: nextId(),
        question,
        headline: `Comparing ${ids[0]} → ${ids[1]}`,
        narrative: diff.summary,
        buttons: [{ label: "View Assessment", href: `/assessments/${ids[1]}` }],
      };
    }
    return insufficient(question, ["two assessment IDs to compare (e.g. asmt-1 and asmt-2)"]);
  }

  // "Why is this assessment UNKNOWN?"
  if (q.includes("unknown") && q.includes("assessment")) {
    const ids = findAssessmentIdsFromText(question);
    const target = ids[0] ? ids[0] : assessments.find((a) => a.systemResult === "INSUFFICIENT_DATA")?.id;
    if (!target) return insufficient(question, ["an assessment ID, or an assessment currently marked INSUFFICIENT_DATA in the demo data"]);
    const reasons = assessmentUnknownReasons(target);
    return {
      id: nextId(),
      question,
      headline: `${target} — why conditions are UNKNOWN`,
      narrative: [...reasons, "UNKNOWN is never silently treated as TRUE or FALSE — it requires human review or new evidence.", TRUST_FOOTER],
      buttons: [{ label: "View Assessment", href: `/assessments/${target}` }],
    };
  }

  // "What is the health of the fleet?" — combined KPI + risk distribution +
  // aircraft ranking + maintenance exposure + compliance exposure + recs.
  if (q.includes("fleet") && q.includes("health")) {
    const f = getFleetAnalytics();
    const c = getComplianceAnalytics();
    const m = getMaintenanceAnalytics();
    const ranked = [...f.aircraftAtRisk].sort((a, b) => (a.risk === b.risk ? 0 : a.risk === "HIGH" ? -1 : 1));
    return {
      id: nextId(),
      question,
      headline: "Fleet Health Summary",
      narrative: [
        `${f.aircraftAtRisk.length} of ${f.fleetSize} aircraft show elevated risk. ${c.nonCompliant + c.reviewRequired} assessment(s) need compliance attention. ${m.overdue.length} work order(s) are overdue.`,
        TRUST_FOOTER,
      ],
      kpis: [...f.kpis, ...c.kpis.slice(0, 2)],
      distribution: { title: "Aircraft Risk Distribution", items: [{ label: "AT_RISK", count: f.aircraftAtRisk.length }, { label: "NOMINAL", count: f.fleetSize - f.aircraftAtRisk.length }] },
      table: { title: "Aircraft Risk Ranking", columns: ["Aircraft", "Risk"], rows: ranked.map((a) => [a.registration, a.risk]) },
      recommendedActions: [
        ...(f.aircraftAtRisk.length > 0 ? [`Review the ${ranked[0]?.registration ?? "highest-risk aircraft"} first.`] : []),
        ...(m.overdue.length > 0 ? [`Address ${m.overdue.length} overdue work order(s).`] : []),
        ...(c.nonCompliant + c.reviewRequired > 0 ? ["Review assessments in Non-Compliant / Review Required status."] : []),
      ],
      buttons: [
        { label: "View Fleet", href: "/aircraft" },
        { label: "Maintenance Operations", href: "/maintenance/operations" },
        { label: "Generate Report", href: "/reports/fleet-risk" },
      ],
      suggestGenerateReport: { reportId: "fleet-risk", title: "Fleet Maintenance Risk Report", scope: "Fleet-wide" },
    };
  }

  // --- M12.6 Maintenance Control Tower / Discrepancy Intelligence branches.
  // All read the same analytics functions the Control Tower and Discrepancy
  // Intelligence pages use (lib/mock/ai/analytics.ts), so a number shown
  // here always matches what's on those pages — no separate AI engine, no
  // separate risk calculation.

  // "Which aircraft is most at risk?"
  if (q.includes("aircraft") && q.includes("most") && q.includes("risk")) {
    const fleet = getControlTowerFleet();
    const ranked = [...fleet].sort((a, b) => (a.risk.risk === b.risk.risk ? 0 : a.risk.risk === "HIGH" ? -1 : b.risk.risk === "HIGH" ? 1 : a.risk.risk === "MEDIUM" ? -1 : 1));
    const top = ranked[0];
    if (!top) return insufficient(question, ["fleet data"]);
    return {
      id: nextId(),
      question,
      headline: `${top.registration} — highest operational risk (${top.risk.risk})`,
      narrative: [...top.risk.reasons, TRUST_FOOTER],
      table: { title: "Aircraft Risk Ranking", columns: ["Aircraft", "Risk"], rows: ranked.slice(0, 8).map((r) => [r.registration, r.risk.risk]) },
      buttons: [{ label: "View Aircraft", href: `/aircraft/${top.aircraftId}` }, { label: "Open Control Tower", href: "/maintenance/control-tower" }],
    };
  }

  // "Why is this aircraft at risk?" (operational risk phrasing — placed
  // before the compliance-risk "why" branch below so operational questions
  // get the defect/work-order/material explanation, not compliance-only).
  if (q.includes("why") && q.includes("risk") && resolveAircraft(question, context)) {
    const a = resolveAircraft(question, context)!;
    const risk = getAircraftOperationalRisk(a.id)!;
    return {
      id: nextId(),
      question,
      headline: `${risk.registration} — why ${risk.risk} operational risk`,
      narrative: [...risk.reasons, TRUST_FOOTER],
      buttons: [{ label: "View Aircraft", href: `/aircraft/${a.id}` }, { label: "Open Control Tower", href: "/maintenance/control-tower" }],
    };
  }

  // "Which aircraft are currently AOG?" — AOG here is the same derived
  // heuristic as the Control Tower table (open HIGH/CRITICAL defect), not a
  // tracked AircraftStatus value; the narrative says so explicitly.
  if (q.includes("aircraft") && q.includes("aog")) {
    const fleet = getControlTowerFleet().filter((r) => r.operationalStatus === "AOG");
    return {
      id: nextId(),
      question,
      headline: `${fleet.length} aircraft currently AOG`,
      narrative: [
        fleet.length > 0 ? "AOG is derived from an open HIGH/CRITICAL-severity defect — there is no separate AOG status field in this dataset." : "No aircraft currently has an open HIGH/CRITICAL-severity defect.",
        TRUST_FOOTER,
      ],
      table: { title: "AOG Aircraft", columns: ["Aircraft", "Reason"], rows: fleet.map((r) => [r.registration, r.aogReason ?? "—"]) },
      buttons: [{ label: "Open Control Tower", href: "/maintenance/control-tower" }],
    };
  }

  // "What discrepancies are recurring?"
  if (q.includes("discrepanc") && q.includes("recurring")) {
    const groups = getDiscrepancyGroups().filter((g) => g.recurringAircraftCount > 0 || g.occurrences > 1);
    return {
      id: nextId(),
      question,
      headline: `${groups.length} ATA chapter(s) with recurring discrepancies`,
      narrative: [groups.length > 0 ? "Grouped by ATA chapter; see Discrepancy Intelligence for full detail on each." : "No ATA chapter currently shows more than one recorded discrepancy.", TRUST_FOOTER],
      table: { title: "Recurring Discrepancy Groups", columns: ["ATA Chapter", "Occurrences", "Aircraft", "Recurring On"], rows: groups.map((g) => [g.ataChapter, g.occurrences, g.aircraftCount, g.recurringAircraftCount]) },
      buttons: [{ label: "Open Discrepancy Intelligence", href: "/maintenance/discrepancies" }],
    };
  }

  // "Which discrepancy is the most common?"
  if (q.includes("discrepanc") && (q.includes("most common") || q.includes("most frequent"))) {
    const groups = getDiscrepancyGroups();
    const top = groups[0];
    if (!top) return insufficient(question, ["defect data"]);
    return {
      id: nextId(),
      question,
      headline: `ATA ${top.ataChapter} — most common discrepancy group (${top.occurrences} occurrence(s))`,
      narrative: [...getDiscrepancyGroupAnalysis(top.ataChapter), TRUST_FOOTER],
      buttons: [{ label: "Open Discrepancy Intelligence", href: "/maintenance/discrepancies" }],
    };
  }

  // "Which aircraft has the most open discrepancies?"
  if (q.includes("aircraft") && q.includes("most") && q.includes("discrepanc")) {
    const fleet = [...getControlTowerFleet()].sort((a, b) => b.openDefects - a.openDefects);
    const top = fleet[0];
    if (!top || top.openDefects === 0) return insufficient(question, ["an aircraft with at least one open discrepancy"]);
    return {
      id: nextId(),
      question,
      headline: `${top.registration} — ${top.openDefects} open discrepancy(ies)`,
      narrative: [TRUST_FOOTER],
      table: { title: "Open Discrepancies by Aircraft", columns: ["Aircraft", "Open"], rows: fleet.filter((r) => r.openDefects > 0).map((r) => [r.registration, r.openDefects]) },
      buttons: [{ label: "View Aircraft", href: `/aircraft/${top.aircraftId}` }],
    };
  }

  // "What should maintenance do next?" — combined recommendation across
  // AOG aircraft, overdue work orders, and recurring discrepancies. Placed
  // before the generic "work orders...attention" branch below since this
  // phrasing is broader (whole-operation, not just work orders).
  if (q.includes("maintenance") && (q.includes("do next") || q.includes("should do") || q.includes("priorit"))) {
    const summary = getControlTowerSummary();
    const m = getMaintenanceAnalytics();
    const recurring = getDiscrepancyGroups().filter((g) => g.recurringAircraftCount > 0);
    const actions: string[] = [];
    if (summary.aog > 0) actions.push(`Address ${summary.aog} AOG aircraft first.`);
    if (m.overdue.length > 0) actions.push(`Escalate ${m.overdue.length} overdue work order(s).`);
    if (recurring.length > 0) actions.push(`Review recurring discrepancies in ATA ${recurring.map((g) => g.ataChapter).join(", ")}.`);
    if (summary.materialShortages > 0) actions.push(`Resolve ${summary.materialShortages} material shortage(s) blocking work.`);
    return {
      id: nextId(),
      question,
      headline: "Recommended maintenance priorities",
      narrative: [actions.length > 0 ? "Based on current AOG, overdue, discrepancy, and material data." : "No urgent maintenance action indicated by current data.", TRUST_FOOTER],
      recommendedActions: actions,
      buttons: [{ label: "Open Control Tower", href: "/maintenance/control-tower" }],
    };
  }

  // "Give me today's maintenance operational report."
  if (q.includes("operational report") || (q.includes("today") && q.includes("maintenance") && q.includes("report"))) {
    const summary = getControlTowerSummary();
    return {
      id: nextId(),
      question,
      headline: "Today's Maintenance Operational Report",
      narrative: [
        `${summary.totalAircraft} aircraft: ${summary.operational} operational, ${summary.underMaintenance} under maintenance, ${summary.aog} AOG.`,
        `${summary.openWorkOrders} open work order(s), ${summary.criticalDiscrepancies} critical discrepancy(ies), ${summary.materialShortages} material shortage(s), ${summary.upcomingMaintenance} upcoming maintenance event(s).`,
        TRUST_FOOTER,
      ],
      kpis: [
        { label: "Operational", value: String(summary.operational), tone: "good" },
        { label: "Under Maintenance", value: String(summary.underMaintenance), tone: "neutral" },
        { label: "AOG", value: String(summary.aog), tone: summary.aog > 0 ? "bad" : "good" },
        { label: "Open Work Orders", value: String(summary.openWorkOrders) },
        { label: "Critical Discrepancies", value: String(summary.criticalDiscrepancies), tone: summary.criticalDiscrepancies > 0 ? "bad" : "good" },
        { label: "Material Shortages", value: String(summary.materialShortages), tone: summary.materialShortages > 0 ? "warning" : "good" },
      ],
      buttons: [{ label: "Open Control Tower", href: "/maintenance/control-tower" }, { label: "Open Discrepancy Intelligence", href: "/maintenance/discrepancies" }],
    };
  }

  // "Which inspections are blocked?"
  if (q.includes("inspection") && q.includes("blocked")) {
    const insp = getInspectionAnalytics();
    const blocked = insp.pending
      .map((p) => {
        const findings = findingsForWorkOrder(p.workOrderId);
        const defects = defectsForWorkOrder(p.workOrderId);
        const reasons: string[] = [];
        if (p.workOrderId === "wo-1042") reasons.push("UNKNOWN checklist item");
        if (findings.some((f) => f.requiresDefect)) reasons.push("finding requiring defect");
        if (defects.length > 0) reasons.push(`${defects.length} open defect(s)`);
        return { ...p, reasons };
      })
      .filter((p) => p.reasons.length > 0);
    return {
      id: nextId(),
      question,
      headline: `${blocked.length} inspection(s) blocked from approval`,
      narrative: [
        blocked.length > 0 ? "Blocking conditions are shown per work order below." : "No pending inspection currently has a blocking condition.",
        TRUST_FOOTER,
      ],
      table: { title: "Blocked Inspections", columns: ["Work Order", "Priority", "Reason"], rows: blocked.map((b) => [b.label, b.priority, b.reasons.join(", ")]) },
      buttons: [{ label: "Open Inspection Queue", href: "/maintenance/inspections" }],
    };
  }

  // "Why was WO-1042 blocked?" — only when a specific work order number
  // resolves; plural phrasing ("which work orders are blocked...") with no
  // resolvable number falls through to the M12.4 fleet-wide branches below
  // instead of dead-ending here.
  if (q.includes("blocked") || (q.includes("why") && q.includes("wo"))) {
    const wo = findWorkOrderFromText(question);
    if (wo) {
      const review = getInspectorReviewForWorkOrder(wo.id);
      const findings = findingsForWorkOrder(wo.id);
      const defects = defectsForWorkOrder(wo.id);
      const narrative: string[] = [];
      if (wo.id === "wo-1042") {
        narrative.push(
          "Checklist item i7 (borescope clearance measurement) is recorded as UNKNOWN — the measurement tool was recalibrating during the shift and clearance was never verified.",
          "Per the inspector decision gate, UNKNOWN checklist items block a PASS approval — UNKNOWN is never silently treated as PASS or FAIL.",
        );
      } else if (findings.length || defects.length) {
        narrative.push(`${findings.length} finding(s) and ${defects.length} open defect(s) are recorded against ${wo.workOrderNumber}.`);
      } else {
        narrative.push(`${wo.workOrderNumber} is currently ${wo.status.replace(/_/g, " ")}; no findings or defects are recorded against it in the demo data.`);
      }
      if (review) narrative.push(`Inspector review status: ${review.status.replace(/_/g, " ")}.`);
      // M12.4 — also surface planning-level blocking (material/technician),
      // using the same getWorkOrderPlanningRow the Planning UI renders, so
      // this answer and the Planning table can never disagree.
      const planningRow = getWorkOrderPlanningRow(wo.id);
      if (planningRow && (planningRow.planningStatus === "MATERIAL_BLOCKED" || planningRow.planningStatus === "BOTH_BLOCKED" || planningRow.planningStatus === "TECHNICIAN_BLOCKED")) {
        narrative.push(`Planning status: ${planningRow.planningStatus.replace(/_/g, " ")} — ${planningRow.recommendedAction}`);
      }
      narrative.push(TRUST_FOOTER);
      return {
        id: nextId(),
        question,
        headline: `${wo.workOrderNumber} — why it's blocked`,
        narrative,
        buttons: [
          { label: "View Work Order", href: `/maintenance/work-orders/${wo.id}` },
          { label: "Open Planning View", href: `/maintenance/planning/${wo.id}` },
          ...(review ? [{ label: "View Inspection", href: `/maintenance/inspections/${review.id}` }] : []),
        ],
      };
    }
    // No specific work order resolved from a "blocked" question — fall
    // through to the M12.4 fleet-wide "which work orders are blocked"
    // branches below rather than dead-ending in insufficient() here.
  }

  // --- M12.4 Work Order Planning & Maintenance Scheduling Intelligence.
  // All of these read getWorkOrderPlanning()/getWorkOrderPlanningSummary()/
  // getNextMaintenanceActions()/getTechnicianAssignmentRecommendation() —
  // the same functions the Planning Center UI renders.

  // "Recommend a technician for WO-1042."
  if (q.includes("recommend") && q.includes("technician")) {
    const wo = findWorkOrderFromText(question);
    if (!wo) return insufficient(question, ["a recognizable work order number, e.g. WO-1042"]);
    const rec = getTechnicianAssignmentRecommendation(wo.id);
    if (!rec) {
      return {
        id: nextId(),
        question,
        headline: `${wo.workOrderNumber} — technician recommendation`,
        narrative: ["Insufficient source data to recommend a technician.", "No technician has a distinguishing certification match, workload advantage, shift availability, or prior aircraft experience for this work order.", TRUST_FOOTER],
        insufficientData: true,
        buttons: [{ label: "Open Planning View", href: `/maintenance/planning/${wo.id}` }],
      };
    }
    return {
      id: nextId(),
      question,
      headline: `${wo.workOrderNumber} — recommended technician: ${rec.name}`,
      narrative: [...rec.reasons, "Certification matching is keyword overlap with the work order title, not verified skill certification — this dataset has no required-certification field.", TRUST_FOOTER],
      buttons: [{ label: "Open Planning View", href: `/maintenance/planning/${wo.id}` }],
    };
  }

  // "Which work orders are ready to start?"
  if (q.includes("work order") && q.includes("ready")) {
    const ready = getReadyToStartWorkOrders();
    return {
      id: nextId(),
      question,
      headline: `${ready.length} work order(s) ready to start`,
      narrative: [ready.length > 0 ? "Material and technician assignment are both in place for these." : "No open work order currently has both material and technician assignment in place.", TRUST_FOOTER],
      table: { title: "Ready to Start", columns: ["Work Order", "Aircraft", "Priority"], rows: ready.map((r) => [r.workOrderNumber, r.aircraftRegistration, r.priority]) },
      buttons: [{ label: "Open Planning Center", href: "/maintenance/planning" }],
    };
  }

  // "Which work orders are blocked by materials?"
  if (q.includes("work order") && q.includes("block") && (q.includes("material") || q.includes("part"))) {
    const blocked = getMaterialBlockedWorkOrders();
    return {
      id: nextId(),
      question,
      headline: `${blocked.length} work order(s) blocked by materials`,
      narrative: [blocked.length > 0 ? "Required part(s) are not currently in stock for these work orders." : "No open work order is currently blocked by a material shortage.", TRUST_FOOTER],
      table: { title: "Material Blocked", columns: ["Work Order", "Aircraft", "Missing Part(s)"], rows: blocked.map((r) => [r.workOrderNumber, r.aircraftRegistration, r.shortParts.map((p) => p.partNumber).join(", ")]) },
      buttons: [{ label: "Open Material Readiness", href: "/maintenance/material-readiness" }],
    };
  }

  // "Which work orders need technician assignment?"
  if (q.includes("work order") && (q.includes("technician assignment") || (q.includes("technician") && q.includes("need")))) {
    const rows = getWorkOrderPlanning().filter((r) => r.planningStatus === "TECHNICIAN_BLOCKED" || r.planningStatus === "BOTH_BLOCKED");
    return {
      id: nextId(),
      question,
      headline: `${rows.length} work order(s) need technician assignment`,
      narrative: [rows.length > 0 ? "These work orders have no assigned technician." : "Every open work order has an assigned technician.", TRUST_FOOTER],
      table: { title: "Needs Technician", columns: ["Work Order", "Aircraft", "Priority"], rows: rows.map((r) => [r.workOrderNumber, r.aircraftRegistration, r.priority]) },
      buttons: [{ label: "Open Planning Center", href: "/maintenance/planning" }],
    };
  }

  // "Which work orders are blocked?" (general)
  if (q.includes("work order") && q.includes("block") && !q.includes("material") && !q.includes("part") && !q.includes("technician")) {
    const rows = getWorkOrderPlanning().filter((r) => r.planningStatus === "MATERIAL_BLOCKED" || r.planningStatus === "TECHNICIAN_BLOCKED" || r.planningStatus === "BOTH_BLOCKED");
    return {
      id: nextId(),
      question,
      headline: `${rows.length} work order(s) currently blocked`,
      narrative: [rows.length > 0 ? "Blocked by material shortage, missing technician assignment, or both." : "No open work order is currently blocked.", TRUST_FOOTER],
      table: { title: "Blocked Work Orders", columns: ["Work Order", "Aircraft", "Blocked By"], rows: rows.map((r) => [r.workOrderNumber, r.aircraftRegistration, r.planningStatus.replace(/_/g, " ")]) },
      buttons: [{ label: "Open Planning Center", href: "/maintenance/planning" }],
    };
  }

  // "Which work orders should maintenance do first?" / "most urgent" / "highest priority"
  if ((q.includes("work order") && (q.includes("first") || q.includes("do first"))) || q.includes("most urgent")) {
    const rows = [...getWorkOrderPlanning()].sort((a, b) => (a.risk === b.risk ? 0 : a.risk === "HIGH" ? -1 : b.risk === "HIGH" ? 1 : a.risk === "MEDIUM" ? -1 : 1));
    const top = rows[0];
    if (!top) return insufficient(question, ["open work order data"]);
    return {
      id: nextId(),
      question,
      headline: `${top.workOrderNumber} — highest planning priority`,
      narrative: [...top.riskReasons, top.recommendedAction, TRUST_FOOTER],
      table: { title: "Work Order Priority Ranking", columns: ["Work Order", "Aircraft", "Risk"], rows: rows.slice(0, 8).map((r) => [r.workOrderNumber, r.aircraftRegistration, r.risk]) },
      buttons: [{ label: "Open Planning View", href: `/maintenance/planning/${top.workOrderId}` }],
    };
  }

  // "Which aircraft has the highest maintenance priority?"
  if (q.includes("aircraft") && q.includes("highest") && q.includes("priorit")) {
    const rows = [...getWorkOrderPlanning()].sort((a, b) => (a.risk === b.risk ? 0 : a.risk === "HIGH" ? -1 : b.risk === "HIGH" ? 1 : a.risk === "MEDIUM" ? -1 : 1));
    const top = rows[0];
    if (!top) return insufficient(question, ["open work order data"]);
    return {
      id: nextId(),
      question,
      headline: `${top.aircraftRegistration} — highest maintenance priority (via ${top.workOrderNumber})`,
      narrative: [...top.riskReasons, TRUST_FOOTER],
      buttons: [{ label: "Open Control Tower", href: "/maintenance/control-tower" }, { label: "Open Planning View", href: `/maintenance/planning/${top.workOrderId}` }],
    };
  }

  // "What should maintenance work on next?" / "today's maintenance priorities"
  if ((q.includes("maintenance") && (q.includes("work on next") || q.includes("should work"))) || (q.includes("today") && q.includes("priorit"))) {
    const actions = getNextMaintenanceActions();
    const summary = getWorkOrderPlanningSummary();
    return {
      id: nextId(),
      question,
      headline: "Today's Maintenance Priorities",
      narrative: [`${summary.readyToStart} ready to start, ${summary.materialBlocked} material blocked, ${summary.technicianAssignmentRequired} need technician assignment.`, TRUST_FOOTER],
      recommendedActions: actions,
      buttons: [{ label: "Open Planning Center", href: "/maintenance/planning" }],
    };
  }

  // --- M12.3 Material Readiness & Procurement Planning branches. All read
  // getMaterialReadinessRows()/getMaterialReadinessSummary() etc. — the same
  // functions the Material Readiness page renders, so the UI and Lisa can
  // never disagree.

  // "Can I procure the part for WO-1042?"
  if (q.includes("procure") && (q.includes("can i") || q.includes("wo"))) {
    const wo = findWorkOrderFromText(question);
    if (!wo) return insufficient(question, ["a recognizable work order number, e.g. WO-1042"]);
    const rows = getWorkOrderMaterialReadiness(wo.id);
    if (rows.length === 0) return insufficient(question, [`a required part on ${wo.workOrderNumber} — none is recorded in the demo data`]);
    const row = rows[0];
    if (!row.bestVendor) {
      return {
        id: nextId(),
        question,
        headline: `${wo.workOrderNumber} — ${row.partNumber} cannot currently be procured`,
        narrative: [row.hasVendorAvailability ? "No vendor currently shows a scoreable price/availability for this part." : "No vendor has a recorded availability line for this part.", TRUST_FOOTER],
        insufficientData: true,
        buttons: [{ label: "Open Material Readiness", href: "/maintenance/material-readiness" }],
      };
    }
    return {
      id: nextId(),
      question,
      headline: `${wo.workOrderNumber} — ${row.partNumber} can be procured from ${row.bestVendor.vendorName}`,
      narrative: [
        `Price: ${row.bestVendor.unitPrice != null ? `${row.bestVendor.currency ?? ""} ${row.bestVendor.unitPrice}` : "Insufficient source data."}`,
        `Lead time: ${row.bestVendor.leadTimeDays != null ? `${row.bestVendor.leadTimeDays} days` : "Insufficient source data."}`,
        `Current procurement status: ${row.procurementStatus}`,
        TRUST_FOOTER,
      ],
      buttons: [{ label: "Open Material Readiness", href: "/maintenance/material-readiness" }, { label: "Open Planning View", href: `/maintenance/planning/${wo.id}` }],
    };
  }

  // "What is the material readiness of N412MX?"
  if (q.includes("material readiness") && resolveAircraft(question, context)) {
    const a = resolveAircraft(question, context)!;
    const rows = getAircraftMaterialReadiness(a.id);
    const blocking = rows.filter((r) => r.materialStatus !== "READY");
    return {
      id: nextId(),
      question,
      headline: `${currentRegistration(a)} — material readiness`,
      narrative: [rows.length === 0 ? "No open work order on this aircraft currently requires material." : blocking.length > 0 ? `${blocking.length} of ${rows.length} required part(s) are not ready.` : "All required parts for open work on this aircraft are ready.", TRUST_FOOTER],
      table: { title: "Required Parts", columns: ["Work Order", "Part", "Status"], rows: rows.map((r) => [r.workOrderNumber, r.partNumber, r.materialStatus]) },
      buttons: [{ label: "Open Material Readiness", href: "/maintenance/material-readiness" }],
    };
  }

  // "Which aircraft have material shortages?" / "which aircraft have material issues?"
  if (q.includes("aircraft") && q.includes("material") && (q.includes("shortage") || q.includes("short") || q.includes("issue"))) {
    const shortages = getMaterialShortages();
    const byAircraft = new Map<string, number>();
    for (const r of shortages) byAircraft.set(r.aircraftRegistration, (byAircraft.get(r.aircraftRegistration) ?? 0) + 1);
    return {
      id: nextId(),
      question,
      headline: `${byAircraft.size} aircraft with material shortages`,
      narrative: [byAircraft.size > 0 ? "Aircraft with at least one part not currently ready." : "No aircraft currently has a recorded material shortage.", TRUST_FOOTER],
      table: { title: "Aircraft With Material Issues", columns: ["Aircraft", "Part(s) Affected"], rows: Array.from(byAircraft.entries()) },
      buttons: [{ label: "Open Material Readiness", href: "/maintenance/material-readiness" }],
    };
  }

  // "Which parts have known vendor availability?"
  if (q.includes("parts") && q.includes("known") && q.includes("vendor")) {
    const rows = getMaterialReadinessRows().filter((r) => r.hasVendorAvailability);
    return {
      id: nextId(),
      question,
      headline: `${rows.length} required part(s) have known vendor availability`,
      narrative: [rows.length > 0 ? "These parts have at least one recorded vendor availability line." : "No required part currently has a recorded vendor availability line.", TRUST_FOOTER],
      table: { title: "Parts With Vendor Data", columns: ["Part", "Work Order", "Best Vendor"], rows: rows.map((r) => [r.partNumber, r.workOrderNumber, r.bestVendor?.vendorName ?? "Insufficient source data."]) },
      buttons: [{ label: "Open Material Readiness", href: "/maintenance/material-readiness" }],
    };
  }

  // "Which shortage should procurement handle first?" / "what parts do I need to procure?"
  if ((q.includes("shortage") && q.includes("first")) || (q.includes("parts") && q.includes("need") && q.includes("procure"))) {
    const actionable = getProcurementActionsForShortages();
    if (actionable.length === 0) return insufficient(question, ["a shortage with enough vendor/price data to recommend a procurement action"]);
    const ranked = [...actionable].sort((a, b) => (a.priority === b.priority ? 0 : a.priority === "CRITICAL" ? -1 : b.priority === "CRITICAL" ? 1 : a.priority === "HIGH" ? -1 : 1));
    const top = ranked[0];
    return {
      id: nextId(),
      question,
      headline: `${top.partNumber} for ${top.workOrderNumber} — highest procurement priority`,
      narrative: [`Work order priority: ${top.priority}. Recommended vendor: ${top.recommendation?.vendorName ?? "Insufficient source data."}.`, TRUST_FOOTER],
      table: { title: "Actionable Shortages", columns: ["Part", "Work Order", "Priority", "Recommended Vendor"], rows: ranked.map((r) => [r.partNumber, r.workOrderNumber, r.priority, r.recommendation?.vendorName ?? "Insufficient source data."]) },
      buttons: [{ label: "Open Material Readiness", href: "/maintenance/material-readiness" }],
    };
  }

  // "What materials are blocking maintenance?" / "which work orders are waiting for parts?" /
  // "what should maintenance do about material shortages?"
  if ((q.includes("material") && (q.includes("block") || q.includes("shortage"))) || (q.includes("work order") && q.includes("waiting") && q.includes("part"))) {
    const summary = getMaterialReadinessSummary();
    const shortages = getMaterialShortages();
    const affectedWorkOrders = new Set(shortages.map((r) => r.workOrderId)).size;
    return {
      id: nextId(),
      question,
      headline: `${affectedWorkOrders} work order(s) affected by material issues`,
      narrative: [
        `${summary.materialShortages} shortage(s), ${summary.partialReadiness} partial, ${summary.partsWithUnknownAvailability} with unknown vendor availability.`,
        TRUST_FOOTER,
      ],
      table: { title: "Material Issues", columns: ["Part", "Work Order", "Aircraft", "Status"], rows: shortages.map((r) => [r.partNumber, r.workOrderNumber, r.aircraftRegistration, r.materialStatus]) },
      buttons: [{ label: "Open Material Readiness", href: "/maintenance/material-readiness" }],
    };
  }

  // --- M12.5 Maintenance Control Center branches. All read
  // getMaintenanceControlCenter()/getMaintenanceControlCenterSummary() —
  // the same aggregation the Control Center page renders, so the UI and
  // Lisa can never disagree.

  // "What needs attention right now?" / "give me the maintenance control report"
  if (q.includes("needs attention") || q.includes("need attention") || (q.includes("maintenance control") && q.includes("report"))) {
    const queue = getMaintenanceControlCenter();
    const summary = getMaintenanceControlCenterSummary();
    const top = queue.slice(0, 5);
    return {
      id: nextId(),
      question,
      headline: `${queue.length} item(s) need attention`,
      narrative: [
        `${summary.aogAircraft} AOG aircraft, ${summary.criticalWorkOrders} critical work order(s), ${summary.materialShortages} material issue(s), ${summary.criticalDiscrepancies} critical discrepancy(ies).`,
        TRUST_FOOTER,
      ],
      table: { title: "Top Priority Items", columns: ["Priority", "Source", "Issue"], rows: top.map((i) => [i.priority, i.source, i.issue]) },
      buttons: [{ label: "Open Maintenance Control Center", href: "/maintenance/control-center" }],
    };
  }

  // "Which aircraft need immediate attention?"
  if (q.includes("aircraft") && (q.includes("immediate attention") || (q.includes("need") && q.includes("attention")))) {
    const fleet = getControlTowerFleet().filter((f) => f.risk.risk !== "LOW");
    return {
      id: nextId(),
      question,
      headline: `${fleet.length} aircraft need immediate attention`,
      narrative: [fleet.length > 0 ? "Ranked by operational risk." : "No aircraft currently shows elevated operational risk.", TRUST_FOOTER],
      table: { title: "Aircraft Needing Attention", columns: ["Aircraft", "Risk", "Open WOs"], rows: fleet.map((f) => [f.registration, f.risk.risk, f.openWorkOrders]) },
      buttons: [{ label: "Open Control Tower", href: "/maintenance/control-tower" }, { label: "Open Maintenance Control Center", href: "/maintenance/control-center" }],
    };
  }

  // "What are the biggest maintenance blockers?" / "what is preventing maintenance from progressing?"
  if ((q.includes("biggest") && q.includes("block")) || (q.includes("prevent") && q.includes("maintenance"))) {
    const queue = getMaintenanceControlCenter().filter((i) => i.priority === "CRITICAL" || i.priority === "HIGH");
    return {
      id: nextId(),
      question,
      headline: `${queue.length} blocker(s) at CRITICAL or HIGH priority`,
      narrative: [queue.length > 0 ? "Ranked by priority; each traces to a real work order, part, or discrepancy group." : "No CRITICAL or HIGH priority blocker currently exists.", TRUST_FOOTER],
      table: { title: "Maintenance Blockers", columns: ["Priority", "Source", "Issue", "Recommended Action"], rows: queue.map((i) => [i.priority, i.source, i.issue, i.recommendedAction]) },
      buttons: [{ label: "Open Maintenance Control Center", href: "/maintenance/control-center" }],
    };
  }

  // "Which discrepancies need attention?"
  if (q.includes("discrepanc") && q.includes("attention")) {
    const groups = getDiscrepancyGroups().filter((g) => g.openCount > 0);
    return {
      id: nextId(),
      question,
      headline: `${groups.length} discrepancy group(s) need attention`,
      narrative: [groups.length > 0 ? "Groups with at least one open occurrence." : "No discrepancy group currently has an open occurrence.", TRUST_FOOTER],
      table: { title: "Discrepancies Needing Attention", columns: ["ATA", "Open", "High Severity", "Recurring"], rows: groups.map((g) => [g.ataChapter, g.openCount, g.highSeverityCount, g.recurringAircraftCount]) },
      buttons: [{ label: "Open Discrepancy Intelligence", href: "/maintenance/discrepancies" }],
    };
  }

  // --- M12.6 Maintenance Execution & Action Center branches. All read
  // getTechnicianEligibilityForWorkOrder()/getExecutionQueue()/
  // getWorkOrdersAwaitingAssignment() — the same functions the Planning
  // detail page and Control Center execution table render.

  // "Who should handle WO-1051?" / "which technician is best suited for this work order?"
  if ((q.includes("who should handle") || q.includes("best suited")) || (q.includes("technician") && q.includes("best") && findWorkOrderFromText(question))) {
    const wo = findWorkOrderFromText(question);
    if (!wo) return insufficient(question, ["a recognizable work order number, e.g. WO-1042"]);
    const eligible = getTechnicianEligibilityForWorkOrder(wo.id).filter((e) => e.eligible);
    if (eligible.length === 0) {
      return {
        id: nextId(),
        question,
        headline: `${wo.workOrderNumber} — no technician recommendation`,
        narrative: ["Insufficient source data to recommend a technician — no technician has a distinguishing certification match, workload advantage, shift availability, or prior aircraft experience for this work order.", TRUST_FOOTER],
        insufficientData: true,
        buttons: [{ label: "Open Planning View", href: `/maintenance/planning/${wo.id}` }],
      };
    }
    const top = eligible[0];
    return {
      id: nextId(),
      question,
      headline: `${wo.workOrderNumber} — ${top.name} recommended`,
      narrative: [...top.reasons, TRUST_FOOTER],
      table: { title: "Eligible Technicians", columns: ["Technician", "Certification Match", "Availability", "Workload"], rows: eligible.map((e) => [e.name, e.certificationMatch, e.availability, e.workload]) },
      buttons: [{ label: "Open Planning View", href: `/maintenance/planning/${wo.id}` }],
    };
  }

  // "Why was this technician recommended?"
  if (q.includes("why") && q.includes("technician") && q.includes("recommend")) {
    const wo = findWorkOrderFromText(question);
    if (!wo) return insufficient(question, ["a recognizable work order number, e.g. WO-1042"]);
    const rec = getTechnicianAssignmentRecommendation(wo.id);
    if (!rec) return insufficient(question, ["a technician with a distinguishing reason for this work order"]);
    return {
      id: nextId(),
      question,
      headline: `${wo.workOrderNumber} — why ${rec.name} was recommended`,
      narrative: [...rec.reasons, "Certification matching is keyword overlap with the work order title, not verified skill certification.", TRUST_FOOTER],
      buttons: [{ label: "Open Planning View", href: `/maintenance/planning/${wo.id}` }],
    };
  }

  // "Which work orders are waiting for technician assignment?" (explicit
  // phrasing variant not already covered by the M12.4 branch)
  if (q.includes("work order") && q.includes("waiting") && q.includes("technician")) {
    const rows = getWorkOrdersAwaitingAssignment();
    return {
      id: nextId(),
      question,
      headline: `${rows.length} work order(s) waiting for technician assignment`,
      narrative: [rows.length > 0 ? "These work orders have no assigned technician." : "Every open work order has an assigned technician.", TRUST_FOOTER],
      table: { title: "Awaiting Assignment", columns: ["Work Order", "Aircraft", "Priority"], rows: rows.map((r) => [r.workOrderNumber, r.aircraftRegistration, r.priority]) },
      buttons: [{ label: "Open Planning Center", href: "/maintenance/planning" }],
    };
  }

  // "What can maintenance complete today?"
  if (q.includes("complete") && (q.includes("today") || q.includes("can maintenance"))) {
    const rows = getExecutionQueue().filter((r) => r.actionType === "COMPLETE");
    return {
      id: nextId(),
      question,
      headline: `${rows.length} work order(s) can be completed today`,
      narrative: [rows.length > 0 ? "In progress and not flagged for escalation." : "No work order is currently in a completable state.", TRUST_FOOTER],
      table: { title: "Ready to Complete", columns: ["Work Order", "Aircraft", "Assigned Technician"], rows: rows.map((r) => [r.workOrderNumber, r.aircraftRegistration, r.assignedTechnicianName ?? "Insufficient source data."]) },
      buttons: [{ label: "Open Maintenance Control Center", href: "/maintenance/control-center" }],
    };
  }

  // "What needs escalation?" (fleet-wide only — a question naming a
  // specific work order, e.g. "when/why was WO-1046 escalated", is handled
  // by the more specific M12.7 traceability branch below instead).
  if (q.includes("escalat") && !findWorkOrderFromText(question)) {
    const rows = getExecutionQueue().filter((r) => r.actionType === "ESCALATE");
    return {
      id: nextId(),
      question,
      headline: `${rows.length} work order(s) need escalation`,
      narrative: [rows.length > 0 ? "In progress with HIGH risk or an AOG aircraft." : "No work order currently meets the escalation criteria.", TRUST_FOOTER],
      table: { title: "Needs Escalation", columns: ["Work Order", "Aircraft", "Priority"], rows: rows.map((r) => [r.workOrderNumber, r.aircraftRegistration, r.priority]) },
      buttons: [{ label: "Open Maintenance Control Center", href: "/maintenance/control-center" }],
    };
  }

  // "What should the planner do next?"
  if (q.includes("planner") && q.includes("next")) {
    const queue = getExecutionQueue().filter((r) => r.planningStatus !== "COMPLETED" && r.planningStatus !== "CANCELLED" && r.planningStatus !== "WAITING_INSPECTION" && r.planningStatus !== "IN_PROGRESS");
    return {
      id: nextId(),
      question,
      headline: `${queue.length} work order(s) need planner action`,
      narrative: [queue.length > 0 ? "Ranked by planning status; each has a real supported action." : "No work order currently needs planner action.", TRUST_FOOTER],
      table: { title: "Planner Action Queue", columns: ["Work Order", "Aircraft", "Action"], rows: queue.map((r) => [r.workOrderNumber, r.aircraftRegistration, r.actionLabel]) },
      buttons: [{ label: "Open Maintenance Control Center", href: "/maintenance/control-center" }],
    };
  }

  // "Which aircraft have work orders that need action?"
  if (q.includes("aircraft") && q.includes("work order") && q.includes("need") && q.includes("action")) {
    const queue = getExecutionQueue().filter((r) => r.actionType !== "REVIEW");
    const byAircraft = new Map<string, number>();
    for (const r of queue) byAircraft.set(r.aircraftRegistration, (byAircraft.get(r.aircraftRegistration) ?? 0) + 1);
    return {
      id: nextId(),
      question,
      headline: `${byAircraft.size} aircraft have work orders needing action`,
      narrative: [TRUST_FOOTER],
      table: { title: "Aircraft With Actionable Work Orders", columns: ["Aircraft", "Count"], rows: Array.from(byAircraft.entries()) },
      buttons: [{ label: "Open Maintenance Control Center", href: "/maintenance/control-center" }],
    };
  }

  // --- M12.7 Maintenance Traceability & Action History branches. All read
  // combinedAuditHistory()/the live auditLog passed via context — the SAME
  // audit trail the Control Center and Planning detail pages render. Never
  // reconstructs a historical value from current state.

  // "What happened to WO-1051?" / "Show the history of WO-1051." / "What changed on this work order?"
  if ((q.includes("what happened") || q.includes("history") || q.includes("what changed")) && findWorkOrderFromText(question)) {
    const wo = findWorkOrderFromText(question)!;
    const log = context?.auditLog ?? auditEvents;
    const history = combinedAuditHistory(wo.workOrderNumber, log);
    if (history.length === 0) return insufficient(question, [`recorded audit events for ${wo.workOrderNumber} — none exist in the current session or seed data`]);
    return {
      id: nextId(),
      question,
      headline: `${wo.workOrderNumber} — ${history.length} recorded action(s)`,
      narrative: [`Most recent: ${history[0].action} by ${history[0].actor} at ${history[0].timestamp}.`, TRUST_FOOTER],
      table: { title: "Work Order History", columns: ["Timestamp", "Action", "Actor", "Before → After"], rows: history.map((e) => [e.timestamp, e.action, e.actor, `${e.previousState ?? "—"} → ${e.newState ?? "—"}`]) },
      buttons: [{ label: "Open Planning View", href: `/maintenance/planning/${wo.id}` }],
    };
  }

  // "Who assigned the technician?" / "Who reassigned this technician?"
  if (q.includes("who") && (q.includes("assigned") || q.includes("reassigned")) && q.includes("technician")) {
    const wo = findWorkOrderFromText(question);
    if (!wo) return insufficient(question, ["a recognizable work order number, e.g. WO-1042"]);
    const log = context?.auditLog ?? auditEvents;
    const history = combinedAuditHistory(wo.workOrderNumber, log).filter((e) => e.action.includes("technician_assigned") || e.action.includes("technician_reassigned"));
    if (history.length === 0) return insufficient(question, [`a recorded technician assignment event for ${wo.workOrderNumber}`]);
    const latest = history[0];
    return {
      id: nextId(),
      question,
      headline: `${wo.workOrderNumber} — technician assignment by ${latest.actor}`,
      narrative: [`${latest.action.includes("reassigned") ? "Reassigned" : "Assigned"}: ${latest.previousState ?? "Unassigned"} → ${latest.newState ?? "Unassigned"}, at ${latest.timestamp}.`, TRUST_FOOTER],
      buttons: [{ label: "Open Planning View", href: `/maintenance/planning/${wo.id}` }],
    };
  }

  // "When was WO-1046 escalated?" / "Why was this work order escalated?"
  if (q.includes("escalat") && findWorkOrderFromText(question)) {
    const wo = findWorkOrderFromText(question)!;
    const log = context?.auditLog ?? auditEvents;
    const escalations = combinedAuditHistory(wo.workOrderNumber, log).filter((e) => e.action.includes("escalated"));
    if (escalations.length === 0) return insufficient(question, [`a recorded escalation event for ${wo.workOrderNumber}`]);
    const latest = escalations[0];
    return {
      id: nextId(),
      question,
      headline: `${wo.workOrderNumber} — escalated at ${latest.timestamp}`,
      narrative: [`Priority: ${latest.previousState ?? "Not recorded."} → ${latest.newState ?? "Not recorded."}.`, `Reason: ${latest.reason ?? "Reason not recorded."}`, TRUST_FOOTER],
      buttons: [{ label: "Open Planning View", href: `/maintenance/planning/${wo.id}` }],
    };
  }

  // "What maintenance actions happened recently?" / "Who made the latest maintenance decision?"
  if ((q.includes("maintenance") && q.includes("action") && q.includes("recent")) || (q.includes("latest") && q.includes("maintenance") && q.includes("decision"))) {
    const log = context?.auditLog ?? auditEvents;
    const recent = [...log].filter((e) => e.action.startsWith("maintenance.")).sort((a, b) => b.timestamp.localeCompare(a.timestamp)).slice(0, 8);
    if (recent.length === 0) return insufficient(question, ["any recorded maintenance action this session"]);
    return {
      id: nextId(),
      question,
      headline: q.includes("latest") ? `Latest maintenance decision: ${recent[0].action} by ${recent[0].actor}` : `${recent.length} recent maintenance action(s)`,
      narrative: [TRUST_FOOTER],
      table: { title: "Recent Maintenance Actions", columns: ["Timestamp", "Action", "Actor", "Entity"], rows: recent.map((e) => [e.timestamp, e.action, e.actor, e.objectLabel]) },
      buttons: [{ label: "Open Maintenance Control Center", href: "/maintenance/control-center" }],
    };
  }

  // "Show me the audit trail for this aircraft."
  if (q.includes("audit trail") && q.includes("aircraft") && resolveAircraft(question, context)) {
    const a = resolveAircraft(question, context)!;
    const log = context?.auditLog ?? auditEvents;
    const history = combinedAuditHistory(currentRegistration(a), log);
    if (history.length === 0) return insufficient(question, [`recorded audit events for ${currentRegistration(a)}`]);
    return {
      id: nextId(),
      question,
      headline: `${currentRegistration(a)} — ${history.length} recorded action(s)`,
      narrative: [TRUST_FOOTER],
      table: { title: "Aircraft Audit Trail", columns: ["Timestamp", "Action", "Actor"], rows: history.map((e) => [e.timestamp, e.action, e.actor]) },
      buttons: [{ label: "View Aircraft", href: `/aircraft/${a.id}` }],
    };
  }

  // "What is putting this project at risk?"
  if (q.includes("project") && q.includes("risk") && !q.includes("analytic")) {
    const project = resolveProject(question, context);
    const a = getProjectAnalytics(project.id);
    if (!a) return insufficient(question, [`project matching "${question}"`]);
    return {
      id: nextId(),
      question,
      headline: `${a.projectNumber} — risk factors`,
      narrative: [a.risks.length > 0 ? `${a.risks.length} risk factor(s) identified.` : "No active risk factors identified.", TRUST_FOOTER],
      risks: a.risks,
      recommendedActions: a.recommendedActions,
      buttons: [
        { label: "View Project", href: `/maintenance/projects/${a.projectId}` },
        { label: "Generate Report", href: `/reports/project-${a.projectId}` },
      ],
      suggestGenerateReport: { reportId: `project-${a.projectId}`, title: `${a.projectNumber} Operations Report`, scope: a.title },
    };
  }

  // "Show project progress and remaining work."
  if (q.includes("project") && (q.includes("progress") || q.includes("remaining"))) {
    const project = resolveProject(question, context);
    const a = getProjectAnalytics(project.id);
    if (!a) return insufficient(question, [`project matching "${question}"`]);
    const remaining = a.workPackageProgress.filter((w) => w.percent < 100);
    return {
      id: nextId(),
      question,
      headline: `${a.projectNumber} — progress`,
      narrative: [
        remaining.length > 0 ? `${remaining.length} work package(s) remain incomplete.` : "All work packages are complete.",
        TRUST_FOOTER,
      ],
      bars: { title: "Work Package Progress", items: a.workPackageProgress },
      buttons: [{ label: "View Project", href: `/maintenance/projects/${a.projectId}` }],
    };
  }

  // "Show resource utilization for this project."
  if (q.includes("project") && (q.includes("resource") || q.includes("utilization"))) {
    const project = resolveProject(question, context);
    const wos = workOrders.filter((w) => w.projectId === project.id);
    const byTechnician = new Map<string, number>();
    for (const w of wos) {
      if (!w.assignedTechnicianId) continue;
      byTechnician.set(w.assignedTechnicianId, (byTechnician.get(w.assignedTechnicianId) ?? 0) + 1);
    }
    const rows = Array.from(byTechnician.entries()).map(([id, count]) => [getTechnicianById(id)?.name ?? id, count]);
    return {
      id: nextId(),
      question,
      headline: `${project.projectNumber} — resource utilization`,
      narrative: [rows.length > 0 ? `${rows.length} technician(s) assigned across ${wos.length} work order(s).` : "No technicians currently assigned.", TRUST_FOOTER],
      table: { title: "Technician Assignments", columns: ["Technician", "Work Orders"], rows },
      buttons: [{ label: "View Project", href: `/maintenance/projects/${project.id}` }, { label: "View Technicians", href: "/maintenance/technicians" }],
    };
  }

  // Project analytics / report (general analyze/health/summary)
  if (q.includes("project") && (q.includes("analytic") || q.includes("health") || q.includes("summary") || q.includes("analyze"))) {
    const project = resolveProject(question, context);
    const a = getProjectAnalytics(project.id);
    if (!a) return insufficient(question, [`project matching "${question}"`]);
    return {
      id: nextId(),
      question,
      headline: `${a.projectNumber} — ${a.title}`,
      narrative: [`Overall Health: ${a.health.replace(/_/g, " ")}`, TRUST_FOOTER],
      kpis: a.kpis,
      bars: { title: "Work Package Progress", items: a.workPackageProgress.map((w) => ({ label: w.label, percent: w.percent })) },
      distribution: { title: "Work Order Status", items: a.workOrderStatusDistribution },
      risks: a.risks,
      recommendedActions: a.recommendedActions,
      complianceChain: [`Requirement`, `Work Order`, `Assessment`, `Evidence`],
      buttons: [
        { label: "View Project", href: `/maintenance/projects/${a.projectId}` },
        { label: "View Work Orders", href: `/maintenance/work-orders` },
        { label: "Generate Report", href: `/reports/project-${a.projectId}` },
      ],
      suggestGenerateReport: { reportId: `project-${a.projectId}`, title: `${a.projectNumber} Operations Report`, scope: a.title },
    };
  }

  // Aircraft health analysis
  if (q.includes("health") && resolveAircraft(question, context)) {
    const a = resolveAircraft(question, context)!;
    const analytics = getAircraftAnalytics(a.id)!;
    return {
      id: nextId(),
      question,
      headline: `${analytics.registration} — health analysis`,
      narrative: [...analytics.reasons, TRUST_FOOTER],
      kpis: analytics.kpis,
      buttons: [
        { label: "View Aircraft", href: `/aircraft/${a.id}` },
        { label: "Generate Aircraft Compliance Report", href: `/reports/aircraft-${a.id}` },
      ],
      suggestGenerateReport: { reportId: `aircraft-${a.id}`, title: `${analytics.registration} Compliance Exposure Report`, scope: analytics.registration },
    };
  }

  // Maintenance actions due for an aircraft
  if (resolveAircraft(question, context) && (q.includes("due") || q.includes("maintenance action"))) {
    const a = resolveAircraft(question, context)!;
    const events = maintenanceEventsForAircraft(a.id);
    const outstanding = events.filter((e) => e.status !== "COMPLETED");
    return {
      id: nextId(),
      question,
      headline: `Maintenance actions due — ${currentRegistration(a)}`,
      narrative: [outstanding.length > 0 ? `${outstanding.length} maintenance event(s) not yet completed.` : "No outstanding maintenance events.", TRUST_FOOTER],
      table: { title: "Maintenance Events", columns: ["Date", "Type", "Status", "Description"], rows: outstanding.map((e) => [e.date, e.eventType, e.status.replace(/_/g, " "), e.description]) },
      buttons: [{ label: "View Aircraft", href: `/aircraft/${a.id}` }],
    };
  }

  // Which work orders need attention / at risk / backlog / delayed
  // M9.0 — "delayed" is a real-world synonym for overdue that no branch
  // previously recognized; added here rather than a new branch since this
  // is the same underlying question.
  if ((q.includes("work orders") || q.includes("work order")) && (q.includes("risk") || q.includes("attention") || q.includes("backlog") || q.includes("delayed") || q.includes("delay"))) {
    const m = getMaintenanceAnalytics();
    return {
      id: nextId(),
      question,
      headline: "Work orders needing attention",
      narrative: [
        `${m.overdue.length} overdue, ${m.waitingParts} waiting on parts, ${m.waitingInspection} waiting on inspection.`,
        TRUST_FOOTER,
      ],
      kpis: m.kpis,
      table: { title: "Overdue Work Orders", columns: ["Work Order", "Due Date", "Priority"], rows: m.overdue.map((w) => [w.label, w.dueDate, w.priority]) },
      buttons: [{ label: "View Work Orders", href: "/maintenance/work-orders" }, { label: "Generate Report", href: "/reports/fleet-risk" }],
      suggestGenerateReport: { reportId: "fleet-risk", title: "Fleet Maintenance Risk Report", scope: "Fleet-wide" },
    };
  }

  // Which parts are at risk (broader than "waiting for parts" work orders)
  if (q.includes("parts") && q.includes("risk")) {
    const atRisk = getPartsAtRisk();
    return {
      id: nextId(),
      question,
      headline: `${atRisk.length} part(s) at risk`,
      narrative: [atRisk.length > 0 ? "Parts not currently in stock (ordered or awaiting receipt)." : "All required parts are in stock.", TRUST_FOOTER],
      table: { title: "Parts At Risk", columns: ["Part", "Description", "Status"], rows: atRisk.map((p) => [p.partNumber, p.description, p.status.replace(/_/g, " ")]) },
      buttons: [{ label: "View Parts", href: "/maintenance/parts" }],
    };
  }

  // Work orders waiting for parts
  if (q.includes("waiting") && q.includes("parts")) {
    const waiting = workOrders.filter((w) => w.status === "WAITING_PARTS");
    return {
      id: nextId(),
      question,
      headline: `${waiting.length} work order(s) waiting on parts`,
      narrative: [TRUST_FOOTER],
      table: { title: "Waiting on Parts", columns: ["Work Order", "Title", "Priority"], rows: waiting.map((w) => [w.workOrderNumber, w.title, w.priority]) },
      buttons: [{ label: "View Parts", href: "/maintenance/parts" }],
    };
  }

  // Technician workload
  if (q.includes("technician") && q.includes("workload")) {
    const workload = getTechnicianWorkload().filter((t) => t.openWorkOrders > 0);
    return {
      id: nextId(),
      question,
      headline: "Technician workload",
      narrative: [TRUST_FOOTER],
      table: { title: "Open Work Orders by Technician", columns: ["Technician", "Open", "Overdue", "On Shift"], rows: workload.map((t) => [t.name, t.openWorkOrders, t.overdueWorkOrders, t.onShift ? "Yes" : "No"]) },
      buttons: [{ label: "View Technicians", href: "/maintenance/technicians" }],
    };
  }

  // Upcoming regulatory deadlines
  if ((q.includes("upcoming") || q.includes("coming up")) && (q.includes("regulator") || q.includes("deadline") || q.includes("compliance"))) {
    const events = upcomingMaintenanceEvents(8).filter((e) => e.relatedRequirementId);
    return {
      id: nextId(),
      question,
      headline: `${events.length} upcoming regulatory deadline(s)`,
      narrative: [events.length > 0 ? "Scheduled maintenance events linked to a regulatory requirement." : "No upcoming events are currently linked to a regulatory requirement.", TRUST_FOOTER],
      table: { title: "Upcoming Regulatory Deadlines", columns: ["Date", "Description", "Requirement"], rows: events.map((e) => [e.date, e.description, e.relatedRequirementId ?? "—"]) },
      buttons: [{ label: "View Regulations", href: "/regulations" }],
    };
  }

  // Overdue maintenance (compliance-linked events) — check before generic overdue
  if (q.includes("overdue") && (q.includes("regulator") || q.includes("compliance"))) {
    const events = overdueMaintenanceEvents();
    return {
      id: nextId(),
      question,
      headline: `${events.length} overdue regulatory/compliance-linked action(s)`,
      narrative: [TRUST_FOOTER],
      table: { title: "Overdue Actions", columns: ["Date", "Description", "Requirement"], rows: events.map((e) => [e.date, e.description, e.relatedRequirementId ?? "—"]) },
      buttons: [{ label: "View Audit Trail", href: "/audit" }],
    };
  }

  // Overdue maintenance (generic)
  if (q.includes("overdue")) {
    const m = getMaintenanceAnalytics();
    return {
      id: nextId(),
      question,
      headline: "Overdue maintenance activities",
      narrative: [`${m.overdue.length} work order(s) are past their due date and not yet completed.`, TRUST_FOOTER],
      table: { title: "Overdue Work Orders", columns: ["Work Order", "Due Date", "Priority"], rows: m.overdue.map((w) => [w.label, w.dueDate, w.priority]) },
      buttons: [{ label: "View Work Orders", href: "/maintenance/work-orders" }],
    };
  }

  // Inspections waiting for review / prioritize
  if (q.includes("inspection") && (q.includes("waiting") || q.includes("review") || q.includes("prioritiz") || q.includes("priorit"))) {
    const insp = getInspectionAnalytics();
    return {
      id: nextId(),
      question,
      headline: q.includes("priorit") ? "Inspection queue — prioritized" : "Inspections awaiting review",
      narrative: [
        `${insp.pending.length} inspection(s) pending. ${q.includes("priorit") ? "Ranked by work order priority (CRITICAL first) — this is prototype triage logic, not a certified safety decision." : ""}`,
        TRUST_FOOTER,
      ],
      kpis: insp.kpis,
      table: { title: "Inspection Queue", columns: ["Work Order", "Priority"], rows: insp.pending.map((p) => [p.label, p.priority]) },
      buttons: [
        { label: "Open Inspection Queue", href: "/maintenance/inspections" },
        { label: "Generate Report", href: "/reports/inspection-queue" },
      ],
      suggestGenerateReport: { reportId: "inspection-queue", title: "Inspection Queue Summary", scope: "Open inspections" },
    };
  }

  // Which aircraft have compliance risk (plural aircraft-wide)
  if (q.includes("aircraft") && q.includes("compliance") && q.includes("risk")) {
    const f = getFleetAnalytics();
    return {
      id: nextId(),
      question,
      headline: "Aircraft with compliance risk",
      narrative: [`${f.aircraftAtRisk.length} of ${f.fleetSize} aircraft show elevated compliance/maintenance risk.`, TRUST_FOOTER],
      table: { title: "Aircraft At Risk", columns: ["Aircraft", "Risk"], rows: f.aircraftAtRisk.map((a) => [a.registration, a.risk]) },
      buttons: [{ label: "View Assessments", href: "/assessments" }],
    };
  }

  // Aircraft compliance risk explanation (single aircraft)
  if (q.includes("compliance risk") || (q.includes("why") && resolveAircraft(question, context))) {
    const a = resolveAircraft(question, context);
    if (a) {
      const analytics = getAircraftAnalytics(a.id)!;
      return {
        id: nextId(),
        question,
        headline: `${analytics.registration} — compliance risk: ${analytics.complianceRisk}`,
        narrative: [...analytics.reasons, TRUST_FOOTER],
        kpis: analytics.kpis,
        buttons: [
          { label: "View Aircraft", href: `/aircraft/${a.id}` },
          { label: "Generate Aircraft Compliance Report", href: `/reports/aircraft-${a.id}` },
        ],
        suggestGenerateReport: { reportId: `aircraft-${a.id}`, title: `${analytics.registration} Compliance Exposure Report`, scope: analytics.registration },
      };
    }
    return insufficient(question, ["a recognizable aircraft registration, e.g. VT-ABC"]);
  }

  // Which aircraft have open compliance actions
  if (q.includes("aircraft") && (q.includes("compliance action") || q.includes("open compliance"))) {
    const c = getComplianceAnalytics();
    return {
      id: nextId(),
      question,
      headline: "Aircraft with open compliance actions",
      narrative: [`${c.nonCompliant + c.reviewRequired} assessment(s) across the fleet are Non-Compliant or Review Required.`, TRUST_FOOTER],
      kpis: c.kpis,
      buttons: [{ label: "View Assessments", href: "/assessments" }],
    };
  }

  // Biggest maintenance risks this week / fleet
  if (q.includes("biggest") || (q.includes("risk") && q.includes("week")) || q.includes("fleet")) {
    const f = getFleetAnalytics();
    return {
      id: nextId(),
      question,
      headline: "Fleet maintenance risk",
      narrative: [`${f.aircraftAtRisk.length} of ${f.fleetSize} aircraft currently show elevated risk.`, TRUST_FOOTER],
      kpis: f.kpis,
      table: { title: "Aircraft At Risk", columns: ["Aircraft", "Risk"], rows: f.aircraftAtRisk.map((a) => [a.registration, a.risk]) },
      buttons: [{ label: "Generate Report", href: "/reports/fleet-risk" }],
      suggestGenerateReport: { reportId: "fleet-risk", title: "Fleet Maintenance Risk Report", scope: "Fleet-wide" },
    };
  }

  // Aircraft defects
  if (resolveAircraft(question, context) && q.includes("defect")) {
    const a = resolveAircraft(question, context)!;
    const defs = defectsForAircraft(a.id);
    const openDefs = defs.filter((d) => d.status === "OPEN");
    return {
      id: nextId(),
      question,
      headline: `${currentRegistration(a)} — defects`,
      narrative: [openDefs.length > 0 ? `${openDefs.length} open defect(s) on this aircraft.` : "No open defects on this aircraft.", TRUST_FOOTER],
      table: { title: "Defects", columns: ["Description", "Severity", "Status"], rows: defs.map((d) => [d.description, d.severity, d.status]) },
      buttons: [{ label: "View Aircraft", href: `/aircraft/${a.id}` }],
    };
  }

  // Aircraft inspection status
  if (resolveAircraft(question, context) && q.includes("inspection") && q.includes("status")) {
    const a = resolveAircraft(question, context)!;
    const aircraftWos = workOrders.filter((w) => w.aircraftId === a.id && w.inspectorReviewId);
    if (aircraftWos.length === 0) return insufficient(question, [`inspection records for ${currentRegistration(a)}`]);
    return {
      id: nextId(),
      question,
      headline: `${currentRegistration(a)} — inspection status`,
      narrative: [TRUST_FOOTER],
      table: { title: "Inspections", columns: ["Work Order", "Status"], rows: aircraftWos.map((w) => [w.workOrderNumber, getInspectorReviewForWorkOrder(w.id)?.status.replace(/_/g, " ") ?? "—"]) },
      buttons: [{ label: "View Aircraft", href: `/aircraft/${a.id}` }],
    };
  }

  // Fleet-wide findings
  if (q.includes("finding")) {
    const requiringDefect = findings.filter((f) => f.requiresDefect);
    return {
      id: nextId(),
      question,
      headline: `${findings.length} finding(s) recorded`,
      narrative: [requiringDefect.length > 0 ? `${requiringDefect.length} finding(s) required a defect to be raised.` : "No findings currently require a defect.", TRUST_FOOTER],
      table: { title: "Findings", columns: ["Work Order", "Severity", "Description"], rows: findings.map((f) => [workOrders.find((w) => w.id === f.workOrderId)?.workOrderNumber ?? f.workOrderId, f.severity, f.description]) },
      buttons: [{ label: "View Defects", href: "/maintenance/defects" }],
    };
  }

  // Compliance health
  if (q.includes("compliance") && q.includes("health")) {
    const c = getComplianceAnalytics();
    return {
      id: nextId(),
      question,
      headline: "Compliance health",
      narrative: [`${c.compliant} of ${c.totalAssessments} assessments are compliant fleet-wide.`, TRUST_FOOTER],
      kpis: c.kpis,
      buttons: [{ label: "Compliance Intelligence", href: "/compliance" }, { label: "Generate Report", href: "/reports/compliance-weekly" }],
      suggestGenerateReport: { reportId: "compliance-weekly", title: "Weekly Compliance Report", scope: "Organization-wide" },
    };
  }

  // Non-compliance
  if (q.includes("non-compliant") || q.includes("non compliance") || q.includes("noncompliance")) {
    const nonCompliant = assessments.filter((a) => a.finalStatus === "NON_COMPLIANT");
    return {
      id: nextId(),
      question,
      headline: `${nonCompliant.length} non-compliant assessment(s)`,
      narrative: [nonCompliant.length > 0 ? "These require human review before further dispatch decisions." : "No assessments are currently Non-Compliant.", TRUST_FOOTER],
      table: { title: "Non-Compliant Assessments", columns: ["Assessment", "Requirement"], rows: nonCompliant.map((a) => [a.id, requirementLabel(a.regulatoryRequirementId)]) },
      buttons: [{ label: "View Assessments", href: "/assessments" }],
    };
  }

  // Evidence gaps
  if (q.includes("evidence") && q.includes("gap")) {
    const noEvidence = assessments.filter((a) => evidenceForAssessment(a.id).length === 0);
    return {
      id: nextId(),
      question,
      headline: `${noEvidence.length} assessment(s) without evidence`,
      narrative: [noEvidence.length > 0 ? "These assessments have no linked evidence on file." : "Every assessment has at least one linked evidence record.", TRUST_FOOTER],
      table: { title: "Assessments Without Evidence", columns: ["Assessment", "Requirement", "Status"], rows: noEvidence.map((a) => [a.id, requirementLabel(a.regulatoryRequirementId), a.finalStatus]) },
      buttons: [{ label: "View Assessments", href: "/assessments" }],
    };
  }

  // Inspection aging
  if (q.includes("inspection") && q.includes("aging")) {
    const insp = getInspectionAnalytics();
    return {
      id: nextId(),
      question,
      headline: "Inspection aging",
      narrative: [`${insp.pending.length} inspection(s) currently pending review.`, TRUST_FOOTER],
      table: { title: "Pending Inspections", columns: ["Work Order", "Priority"], rows: insp.pending.map((p) => [p.label, p.priority]) },
      buttons: [{ label: "Open Inspection Queue", href: "/maintenance/inspections" }],
    };
  }

  // Failed checklist items
  if (q.includes("failed") && q.includes("checklist")) {
    const withFindings = findings.filter((f) => f.requiresDefect);
    return {
      id: nextId(),
      question,
      headline: `${withFindings.length} checklist finding(s) with a raised defect`,
      narrative: ["Live PASS/FAIL/UNKNOWN state is tracked per work order — open a work order's checklist to see current item-level results.", TRUST_FOOTER],
      table: { title: "Findings Requiring Defect", columns: ["Work Order", "Description"], rows: withFindings.map((f) => [workOrders.find((w) => w.id === f.workOrderId)?.workOrderNumber ?? f.workOrderId, f.description]) },
      buttons: [{ label: "Open Inspection Queue", href: "/maintenance/inspections" }],
    };
  }

  // Aircraft ranking (fleet-wide)
  if (q.includes("aircraft") && q.includes("ranking")) {
    const f = getFleetAnalytics();
    const ranked = [...f.aircraftAtRisk].sort((a, b) => (a.risk === b.risk ? 0 : a.risk === "HIGH" ? -1 : 1));
    return {
      id: nextId(),
      question,
      headline: "Aircraft risk ranking",
      narrative: [TRUST_FOOTER],
      table: { title: "Aircraft Ranking", columns: ["Aircraft", "Risk"], rows: ranked.map((a) => [a.registration, a.risk]) },
      buttons: [{ label: "View Fleet", href: "/aircraft" }],
    };
  }

  // M5.2 — AMM/IPC/SRM/CMM/MPD/MEL reference matching. The mock dataset does
  // not contain any source-document reference library, so this is always
  // INSUFFICIENT_DATA — that is the correct, honest answer, not a gap in
  // this branch. Never fabricate a reference number.
  if (/\b(amm|ipc|srm|cmm|mpd|mel)\b/.test(q) && (q.includes("reference") || q.includes("procedure") || q.includes("which") || q.includes("what"))) {
    return insufficient(question, [
      "a source-document reference library (AMM/IPC/SRM/CMM/MPD/MEL) is not present in the current demo dataset — no reference can be returned without fabricating one",
    ]);
  }

  // M5.0 — Defect Intelligence: single-defect deep dive.
  const mentionedDefect = defects.find((d) => q.includes(d.id));
  if (mentionedDefect || (q.includes("defect") && (q.includes("intelligence") || q.includes("explain") || q.includes("tell me about")))) {
    const defect = mentionedDefect ?? defectsForAircraft(context?.aircraftId ?? "")[0];
    if (!defect) return insufficient(question, ["a specific defect ID, or an aircraft context with a recorded defect"]);
    const wo = defect.workOrderId ? workOrders.find((w) => w.id === defect.workOrderId) : undefined;
    const relatedFindings = defect.workOrderId ? findingsForWorkOrder(defect.workOrderId) : [];
    const missing: string[] = [];
    if (!defect.correctiveAction) missing.push("corrective action not yet recorded");
    if (!wo?.relatedRequirementId) missing.push("no regulatory requirement linked to the associated work order");
    const confidence: "LOW" | "MEDIUM" | "HIGH" = defect.correctiveAction && wo ? "HIGH" : wo ? "MEDIUM" : "LOW";
    return {
      id: nextId(),
      question,
      headline: `Defect ${defect.id} — intelligence`,
      narrative: [
        `Observed condition: ${defect.description}`,
        `Known evidence: ${relatedFindings.length} linked finding(s), severity ${defect.severity}, status ${defect.status}.`,
        defect.correctiveAction ? `Recorded corrective action: ${defect.correctiveAction}` : "No corrective action recorded — Insufficient source data.",
        wo?.relatedRequirementId ? `Regulatory implication: linked via ${wo.workOrderNumber} to ${requirementLabel(wo.relatedRequirementId)}.` : "No regulatory implication is supported by current source data.",
        `Confidence: ${confidence}.`,
        missing.length > 0 ? `Missing information: ${missing.join("; ")}.` : "",
        TRUST_FOOTER,
      ].filter(Boolean),
      buttons: [
        { label: "View Aircraft", href: `/aircraft/${defect.aircraftId}` },
        ...(wo ? [{ label: "View Work Order", href: `/maintenance/work-orders/${wo.id}` }] : []),
      ],
    };
  }

  // M5.1 — Defect → Task recommendation. Only recommends an EXISTING
  // checklist item on the SAME work order when its label/instruction text
  // overlaps the defect description — never invents a task.
  if (q.includes("defect") && (q.includes("recommend") || q.includes("which task"))) {
    const defect = defects.find((d) => q.includes(d.id)) ?? defectsForAircraft(context?.aircraftId ?? "")[0];
    if (!defect || !defect.workOrderId) return insufficient(question, ["a defect linked to a work order with an existing checklist"]);
    const checklist = getChecklistByWorkOrderId(defect.workOrderId);
    if (!checklist) return insufficient(question, [`a checklist on ${defect.workOrderId} to match against`]);
    const words = defect.description.toLowerCase().split(/\W+/).filter((w) => w.length > 4);
    const scored = checklist.items
      .map((item) => ({ item, score: words.filter((w) => item.label.toLowerCase().includes(w) || item.instruction.toLowerCase().includes(w)).length }))
      .filter((s) => s.score > 0)
      .sort((a, b) => b.score - a.score);
    const match = scored[0];
    return {
      id: nextId(),
      question,
      headline: `Defect ${defect.id} — task recommendation`,
      narrative: match
        ? [`Exact source-supported match: checklist item "${match.item.label}" on ${checklist.title}.`, TRUST_FOOTER]
        : ["Insufficient source data to recommend a specific task.", TRUST_FOOTER],
      buttons: defect.workOrderId ? [{ label: "View Work Order", href: `/maintenance/work-orders/${defect.workOrderId}` }] : [],
    };
  }

  // M5.3 — Explainable TAT (turnaround time) risk.
  if (q.includes("tat") && (q.includes("risk") || q.includes("why") || q.includes("driving") || q.includes("drives"))) {
    const wo = findWorkOrderFromText(question) ?? (context?.aircraftId ? workOrders.find((w) => w.aircraftId === context.aircraftId && w.status !== "COMPLETED" && w.status !== "CANCELLED") : undefined);
    // M9.0 — no specific work order named: give a fleet-wide TAT driver
    // summary instead of INSUFFICIENT_DATA. Still entirely source-grounded
    // (real overdue/waiting-parts/waiting-inspection work orders), just at
    // fleet scope instead of a single work order.
    if (!wo) {
      const m = getMaintenanceAnalytics();
      const drivers: string[] = [];
      if (m.overdue.length > 0) drivers.push(`${m.overdue.length} overdue work order(s)`);
      if (m.waitingParts > 0) drivers.push(`${m.waitingParts} work order(s) waiting on parts`);
      if (m.waitingInspection > 0) drivers.push(`${m.waitingInspection} work order(s) waiting on inspection`);
      if (drivers.length === 0) return insufficient(question, ["a recognizable work order number, or fleet-wide TAT driver data (none of overdue/waiting-parts/waiting-inspection work orders currently exist)"]);
      return {
        id: nextId(),
        question,
        headline: "Fleet-wide TAT risk drivers",
        narrative: [
          `Top drivers: ${drivers.join("; ")}.`,
          "Name a specific work order (e.g. \"What is the TAT risk for WO-1042?\") for a single-work-order breakdown with primary/secondary drivers.",
          TRUST_FOOTER,
        ],
        kpis: m.kpis,
        table: { title: "Overdue Work Orders", columns: ["Work Order", "Due Date", "Priority"], rows: m.overdue.map((w) => [w.label, w.dueDate, w.priority]) },
        buttons: [{ label: "View Work Orders", href: "/maintenance/work-orders" }],
      };
    }
    // Note: checklist item completion/UNKNOWN state lives in MroStateContext
    // (client-only) and is not available to this server-safe engine module —
    // TAT risk here is computed from work-order-level source data only.
    // M7.7 — each factor is scored so the highest-weight driver can be
    // reported as the Primary Driver and the rest as Secondary Drivers,
    // rather than a flat, unranked list.
    const scoredFactors: { text: string; points: number }[] = [];
    if (isOverdue(wo)) scoredFactors.push({ text: `overdue since ${wo.dueDate}`, points: 2 });
    if (wo.priority === "CRITICAL" || wo.priority === "HIGH") scoredFactors.push({ text: `${wo.priority} priority`, points: 1 });
    if (wo.status === "WAITING_PARTS") scoredFactors.push({ text: "waiting on parts", points: 2 });
    if (wo.status === "WAITING_INSPECTION") scoredFactors.push({ text: "waiting on inspection", points: 1 });
    const openDefectsOnWo = defectsForWorkOrder(wo.id).filter((d) => d.status === "OPEN");
    if (openDefectsOnWo.some((d) => d.severity === "CRITICAL" || d.severity === "HIGH")) scoredFactors.push({ text: `${openDefectsOnWo.length} open HIGH/CRITICAL defect(s)`, points: 2 });
    if (wo.relatedRequirementId) scoredFactors.push({ text: `tied to regulatory requirement ${requirementLabel(wo.relatedRequirementId)}`, points: 0 });
    const riskPoints = scoredFactors.reduce((s, f) => s + f.points, 0);
    const tatRisk: "LOW" | "MEDIUM" | "HIGH" = riskPoints >= 3 ? "HIGH" : riskPoints >= 1 ? "MEDIUM" : "LOW";
    const ranked = [...scoredFactors].sort((a, b) => b.points - a.points);
    const primaryDriver = ranked[0];
    const secondaryDrivers = ranked.slice(1);
    const unknownFactors: string[] = [];
    unknownFactors.push("Checklist item completion/UNKNOWN state (session-only, client-side) is not evaluated by this server-safe calculation.");

    let recommendedAction: string;
    if (wo.status === "WAITING_PARTS") recommendedAction = "Expedite outstanding parts to unblock this work order.";
    else if (openDefectsOnWo.length > 0) recommendedAction = "Resolve open defects before further progress.";
    else if (isOverdue(wo)) recommendedAction = "Escalate — due date has passed.";
    else if (wo.status === "WAITING_INSPECTION") recommendedAction = "Assign an inspector to clear the review backlog.";
    else recommendedAction = "No urgent action indicated by current source data.";

    return {
      id: nextId(),
      question,
      headline: `${wo.workOrderNumber} — TAT risk: ${tatRisk}`,
      narrative: [
        `Current TAT Risk: ${tatRisk}`,
        `Primary Driver: ${primaryDriver ? primaryDriver.text : "None identified from current source data."}`,
        `Secondary Drivers: ${secondaryDrivers.length > 0 ? secondaryDrivers.map((f) => f.text).join("; ") : "None."}`,
        `Recommended Action: ${recommendedAction}`,
        `Unknown Factors: ${unknownFactors.join("; ")}`,
        TRUST_FOOTER,
      ],
      buttons: [{ label: "View Work Order", href: `/maintenance/work-orders/${wo.id}` }],
    };
  }

  // M7.6 — Prescriptive AI 2.0: "what should happen next?" Extends this same
  // engine (no second AI system) with a fixed, source-grounded answer
  // format. Every field is derived from real work-order/part/defect state —
  // when the source data cannot support a recommendation, this returns the
  // standard INSUFFICIENT_DATA response rather than guessing.
  if (
    !q.includes("procurement") && (
      q.includes("what should happen next") ||
      q.includes("next step") ||
      (q.includes("recommend") && q.includes("next")) ||
      (q.includes("technician") && q.includes("next")) ||
      (q.includes("do next"))
    )
  ) {
    const wo = findWorkOrderFromText(question) ?? (context?.aircraftId ? workOrders.find((w) => w.aircraftId === context.aircraftId && w.status !== "COMPLETED" && w.status !== "CANCELLED") : undefined);
    if (!wo) return insufficient(question, ["a recognizable work order number or an aircraft context with active work to base a recommendation on"]);

    const openDefectsOnWo = defectsForWorkOrder(wo.id).filter((d) => d.status === "OPEN");
    const criticalDefects = openDefectsOnWo.filter((d) => d.severity === "CRITICAL" || d.severity === "HIGH");
    const woParts = partsForWorkOrder(wo.id);
    const partsNotInStock = woParts.filter((p) => p.status !== "IN_STOCK");
    const missingCertParts = woParts.filter((p) => {
      const certs = certificatesForPart(p.id);
      return certs.length === 0 || certs.some((c) => c.verificationStatus !== "PRESENT");
    });
    const review = getInspectorReviewForWorkOrder(wo.id);

    const supportingRecords: string[] = [`Work Order ${wo.workOrderNumber} (status: ${wo.status.replace(/_/g, " ")})`];
    const unknowns: string[] = [];
    let recommendation: string;
    let reason: string;
    let confidence: "LOW" | "MEDIUM" | "HIGH";
    let humanDecisionRequired: string;

    if (criticalDefects.length > 0) {
      recommendation = `Resolve ${criticalDefects.length} open HIGH/CRITICAL defect(s) on ${wo.workOrderNumber} before proceeding.`;
      reason = `Defect(s) ${criticalDefects.map((d) => d.id).join(", ")} are open with HIGH or CRITICAL severity and are the highest-risk factor currently on this work order.`;
      supportingRecords.push(...criticalDefects.map((d) => `Defect ${d.id}: ${d.description}`));
      confidence = "HIGH";
      humanDecisionRequired = "A qualified technician/inspector must confirm defect resolution before further sign-off.";
    } else if (wo.status === "WAITING_PARTS" && partsNotInStock.length > 0) {
      recommendation = `Expedite the ${partsNotInStock.length} part(s) currently not in stock for ${wo.workOrderNumber}.`;
      reason = `Work order status is WAITING_PARTS and ${partsNotInStock.map((p) => p.partNumber).join(", ")} are not currently IN_STOCK.`;
      supportingRecords.push(...partsNotInStock.map((p) => `Part ${p.partNumber}: ${p.status.replace(/_/g, " ")}`));
      confidence = "HIGH";
      humanDecisionRequired = "Maintenance planning must confirm parts ETA before rescheduling.";
    } else if (missingCertParts.length > 0) {
      recommendation = `Confirm certificate evidence for ${missingCertParts.map((p) => p.partNumber).join(", ")} before closing ${wo.workOrderNumber}.`;
      reason = "One or more parts on this work order do not have a verified (PRESENT) certificate on file — this is an evidence gap, not a compliance failure by itself.";
      supportingRecords.push(...missingCertParts.map((p) => `Part ${p.partNumber}: traceability ${traceabilityStatusForPart(p.id).replace(/_/g, " ")}`));
      unknowns.push("Whether a certificate exists but is simply not yet logged, or genuinely was never issued.");
      confidence = "MEDIUM";
      humanDecisionRequired = "Quality/compliance staff must verify certificate status against the physical/vendor record.";
    } else if (!review && wo.status === "WAITING_INSPECTION") {
      recommendation = `Assign an inspector to review ${wo.workOrderNumber}.`;
      reason = "Work order status is WAITING_INSPECTION and no inspector review record exists yet.";
      confidence = "MEDIUM";
      humanDecisionRequired = "An inspector must be assigned and complete the review.";
    } else if (isOverdue(wo)) {
      recommendation = `Escalate ${wo.workOrderNumber} — it is overdue.`;
      reason = `Due date ${wo.dueDate} has passed and the work order is not yet COMPLETED or CANCELLED.`;
      confidence = "MEDIUM";
      humanDecisionRequired = "Maintenance management must decide whether to reprioritize or reassign.";
    } else {
      return insufficient(question, [`a clear next-step driver for ${wo.workOrderNumber} — no open critical defect, parts gap, certificate gap, pending inspection, or overdue condition was found in current source data`]);
    }

    return {
      id: nextId(),
      question,
      headline: `${wo.workOrderNumber} — Recommendation`,
      narrative: [
        `Recommendation: ${recommendation}`,
        `Reason: ${reason}`,
        `Supporting Records: ${supportingRecords.join("; ")}`,
        `Evidence Status: ${missingCertParts.length > 0 ? "Certificate evidence gap present" : "No certificate evidence gap identified"}`,
        `Confidence: ${confidence}`,
        `Unknowns: ${unknowns.length > 0 ? unknowns.join("; ") : "None identified from current source data."}`,
        `Human Decision Required: ${humanDecisionRequired}`,
        TRUST_FOOTER,
      ],
      recommendedActions: [recommendation],
      buttons: [{ label: "View Work Order", href: `/maintenance/work-orders/${wo.id}` }],
    };
  }

  // M9.0 — "Which aircraft has the highest maintenance risk?" Ranks real
  // aircraft using the same getAircraftAnalytics() driver data shown
  // everywhere else (Executive "Why?", Aircraft Health) — no separate
  // scoring system, no black-box number.
  if (q.includes("aircraft") && (q.includes("highest") || q.includes("most")) && (q.includes("risk") || q.includes("maintenance"))) {
    const ranked = aircraft
      .map((a) => getAircraftAnalytics(a.id)!)
      .filter((a) => a.complianceRisk !== "LOW")
      .sort((a, b) => (b.overdueWorkOrders + b.criticalOrHighDefects) - (a.overdueWorkOrders + a.criticalOrHighDefects));
    const top = ranked[0];
    if (!top) return insufficient(question, ["any aircraft currently showing elevated risk in the current dataset"]);
    const inspectionNote = workOrdersForAircraft(top.aircraftId).some((w) => w.status === "WAITING_INSPECTION") ? "waiting inspection" : null;
    return {
      id: nextId(),
      question,
      headline: `Highest identified maintenance risk: ${top.registration}`,
      narrative: [
        `Risk drivers: ${top.reasons.join("; ")}${inspectionNote ? `; ${inspectionNote}` : ""}.`,
        `Recommended action: ${top.criticalOrHighDefects > 0 ? "Prioritize resolution of open HIGH/CRITICAL defects." : top.overdueWorkOrders > 0 ? "Prioritize the overdue work order(s)." : "Review the flagged assessment(s)."}`,
        "Source: Aircraft → Work Orders → Defects → Inspection → Evidence.",
        TRUST_FOOTER,
      ],
      kpis: top.kpis,
      buttons: [{ label: "View Aircraft", href: `/aircraft/${top.aircraftId}` }, { label: "Why is this aircraft at risk?", href: `/fleet/aircraft/${top.aircraftId}/health` }],
    };
  }

  // M9.0 — "Why is this aircraft at risk?" without a named aircraft: resolve
  // from context if available, otherwise ask for one rather than a generic
  // "not a recognized topic" message (the topic IS understood).
  if (q.includes("why") && q.includes("aircraft") && q.includes("risk") && !resolveAircraft(question, context)) {
    return insufficient(question, ["a specific aircraft registration — this question is understood, but no aircraft was named or in context to evaluate"]);
  }

  // M9.0 — Executive operational summary: "what is the current operational
  // risk?" / "what should management focus on today?" Combines the SAME
  // fleet/maintenance/compliance/parts analytics used across Executive and
  // Compliance Intelligence — no new calculation, just a synthesized view.
  if (
    (q.includes("operational") && q.includes("risk")) ||
    (q.includes("management") && q.includes("focus")) ||
    (q.includes("focus") && q.includes("today"))
  ) {
    const fleet = getFleetAnalytics();
    const maint = getMaintenanceAnalytics();
    const compliance = getComplianceAnalytics();
    const partsAtRisk = getPartsAtRisk();
    const priorities: string[] = [];
    if (fleet.aircraftAtRisk.length > 0) priorities.push(`${fleet.aircraftAtRisk.length} aircraft at elevated risk (${fleet.aircraftAtRisk.map((a) => a.registration).join(", ")})`);
    if (maint.overdue.length > 0) priorities.push(`${maint.overdue.length} overdue work order(s)`);
    if (compliance.nonCompliant + compliance.reviewRequired > 0) priorities.push(`${compliance.nonCompliant + compliance.reviewRequired} compliance assessment(s) needing review`);
    if (partsAtRisk.length > 0) priorities.push(`${partsAtRisk.length} part(s) at risk (not in stock)`);
    return {
      id: nextId(),
      question,
      headline: "Executive operational summary",
      narrative: [
        priorities.length > 0 ? `Top priorities: ${priorities.join("; ")}.` : "No significant fleet, maintenance, compliance, or parts risk currently identified.",
        TRUST_FOOTER,
      ],
      kpis: fleet.kpis,
      buttons: [{ label: "Open Executive Control Center", href: "/executive" }, { label: "Generate Report", href: "/reports/general-operational" }],
      suggestGenerateReport: { reportId: "general-operational", title: "General Operational Report", scope: "Fleet-wide" },
    };
  }

  // M9.2 — "Give me a general operational report." Triggers the visual
  // report engine (lib/mock/reports.ts) rather than answering inline — the
  // AI's job here is to recognize the request and hand off, not to render
  // a second reporting surface.
  if (q.includes("operational report") || (q.includes("operational") && q.includes("report"))) {
    return {
      id: nextId(),
      question,
      headline: "General Operational Report",
      narrative: ["Generating the visual operational report from current fleet, maintenance, parts, and compliance data.", TRUST_FOOTER],
      buttons: [{ label: "Open Operational Report", href: "/reports/general-operational" }],
      suggestGenerateReport: { reportId: "general-operational", title: "General Operational Report", scope: "Fleet-wide" },
    };
  }

  // M10.7 — MRO Financial Intelligence questions. Extends this same engine
  // with plain arithmetic answers from lib/mock/finance.ts — no AI/LLM
  // computation, no invented price/margin/vendor figure. Cost data exists
  // for only 3 of 10 work orders; every branch below says so explicitly
  // when the specific aircraft/work order/vendor asked about has none.

  if (q.includes("generate") && (q.includes("financial") || q.includes("profitability") || (q.includes("maintenance") && q.includes("cost") && q.includes("report")))) {
    return {
      id: nextId(),
      question,
      headline: "MRO Financial Intelligence Report",
      narrative: ["Generating the visual financial report from current cost, vendor, and customer charge data.", TRUST_FOOTER],
      buttons: [{ label: "Open Financial Report", href: "/reports/financial-intelligence" }],
      suggestGenerateReport: { reportId: "financial-intelligence", title: "MRO Financial Intelligence Report", scope: "Fleet-wide" },
    };
  }

  // "How much did VT-ABC cost us?" / aircraft-specific cost
  if (resolveAircraft(question, context) && (q.includes("cost") || q.includes("expensive") || q.includes("margin"))) {
    const a = resolveAircraft(question, context)!;
    const woIds = workOrdersForAircraft(a.id).map((w) => w.id);
    const summary = getAircraftCostSummary(a.id, woIds);
    if (!summary || summary.coverage === "INSUFFICIENT_DATA") {
      return insufficient(question, [`cost data for ${currentRegistration(a)} — no labor, parts, or vendor cost records exist for any of its work orders`]);
    }
    return {
      id: nextId(),
      question,
      headline: `${summary.registration} — maintenance cost`,
      narrative: [
        `Total cost: ${summary.totalCost.toLocaleString()} USD (Labor ${summary.laborCost.toLocaleString()}, Parts ${summary.partsCost.toLocaleString()}, Vendor ${summary.vendorCost.toLocaleString()}), based on ${summary.workOrdersWithCostData} of ${summary.totalWorkOrders} work order(s) with recorded cost data.`,
        summary.customerCharge !== null ? `Customer charge: ${summary.customerCharge.toLocaleString()} USD. Gross margin: ${summary.grossMargin?.toLocaleString()} USD.` : "Customer charge: Insufficient source data for the remaining work order(s).",
        TRUST_FOOTER,
      ],
      buttons: [{ label: "View Financial Detail", href: `/finance/${a.id}` }],
    };
  }

  // "Which aircraft is most/highest cost to maintain?" / "costing us the most"
  if (q.includes("aircraft") && (q.includes("most") || q.includes("highest") || q.includes("costing")) && (q.includes("cost") || q.includes("expensive"))) {
    const ranked = aircraft
      .map((a) => getAircraftCostSummary(a.id, workOrdersForAircraft(a.id).map((w) => w.id)))
      .filter((s): s is NonNullable<typeof s> => s !== null && s.coverage !== "INSUFFICIENT_DATA")
      .sort((a, b) => b.totalCost - a.totalCost);
    if (ranked.length === 0) return insufficient(question, ["aircraft-level cost data — no work order on any aircraft has recorded cost data"]);
    const top = ranked[0];
    return {
      id: nextId(),
      question,
      headline: `Highest maintenance cost: ${top.registration}`,
      narrative: [
        `Total cost: ${top.totalCost.toLocaleString()} USD across ${top.workOrdersWithCostData} of ${top.totalWorkOrders} work order(s) with cost data.`,
        ranked.length < aircraft.length ? `Only ${ranked.length} of ${aircraft.length} aircraft have any cost data — this ranking is partial, not fleet-complete.` : "",
        TRUST_FOOTER,
      ].filter(Boolean),
      table: { title: "Aircraft Cost Ranking", columns: ["Aircraft", "Total Cost", "Work Orders Costed"], rows: ranked.map((a) => [a.registration, a.totalCost, `${a.workOrdersWithCostData}/${a.totalWorkOrders}`]) },
      buttons: [{ label: "View Financial Detail", href: `/finance/${top.aircraftId}` }],
    };
  }

  // "Which work orders are losing money?"
  if (q.includes("work order") && (q.includes("losing money") || q.includes("unprofitable") || (q.includes("negative") && q.includes("margin")))) {
    const losing = workOrderIdsWithCostData()
      .map((id) => getWorkOrderCostSummary(id)!)
      .filter((s) => s.grossMargin !== null && s.grossMargin < 0);
    return {
      id: nextId(),
      question,
      headline: losing.length > 0 ? `${losing.length} work order(s) losing money` : "No work orders currently show a negative margin",
      narrative: [losing.length === 0 ? "Of the work orders with both cost and customer-charge data, none show a negative gross margin." : "These work orders' recorded customer charge is less than their recorded cost.", TRUST_FOOTER],
      table: losing.length > 0 ? { title: "Unprofitable Work Orders", columns: ["Work Order", "Total Cost", "Customer Charge", "Margin"], rows: losing.map((s) => [s.workOrderNumber, s.totalCost, s.customerCharge ?? 0, s.grossMargin ?? 0]) } : undefined,
      buttons: [{ label: "View Financial Intelligence", href: "/finance" }],
    };
  }

  // "Where are we overspending?" / "biggest cost drivers"
  if ((q.includes("overspend") || (q.includes("cost") && q.includes("driver"))) ) {
    const topPart = highestCostPartCost();
    const topVendor = highestVendorSpend();
    if (!topPart && !topVendor) return insufficient(question, ["cost driver data — no part or vendor cost records exist"]);
    return {
      id: nextId(),
      question,
      headline: "Biggest maintenance cost drivers",
      narrative: [
        topPart ? `Highest single part cost: ${topPart.partId} on work order ${topPart.workOrderId} — ${topPart.amount.toLocaleString()} USD.` : "No part cost data available.",
        topVendor ? `Highest single vendor line item: ${topVendor.vendorName} — ${topVendor.amount.toLocaleString()} USD.` : "No vendor cost data available.",
        TRUST_FOOTER,
      ],
      buttons: [{ label: "View Financial Intelligence", href: "/finance" }],
    };
  }

  // "Which vendors cost us the most?"
  if (q.includes("vendor") && (q.includes("most") || q.includes("costing") || q.includes("highest"))) {
    if (vendorCosts.length === 0) return insufficient(question, ["vendor expenditure data — no vendor cost records exist"]);
    const byVendor = new Map<string, number>();
    for (const v of vendorCosts) byVendor.set(v.vendorName, (byVendor.get(v.vendorName) ?? 0) + v.amount);
    const ranked = Array.from(byVendor.entries()).sort((a, b) => b[1] - a[1]);
    return {
      id: nextId(),
      question,
      headline: `Highest vendor spend: ${ranked[0][0]}`,
      narrative: [`Total recorded spend: ${ranked[0][1].toLocaleString()} USD.`, TRUST_FOOTER],
      table: { title: "Vendor Spend", columns: ["Vendor", "Total Spend"], rows: ranked.map(([name, amount]) => [name, amount]) },
      buttons: [{ label: "View Financial Intelligence", href: "/finance" }],
    };
  }

  // M11.6 — Prescriptive Procurement AI. Extends this same engine — no
  // second AI system — with vendor/procurement questions, sourced entirely
  // from lib/mock/procurement.ts. Never invents stock, price, lead time, or
  // certification for a vendor/part combination that has no seeded record.

  // M11.4 — "What is in my procurement cart?" / "how much will this
  // procurement request cost?" Reuses cartSummary()/cartItemLineTotal(),
  // the SAME functions the cart page itself uses, so Lisa's answer and the
  // cart UI can never disagree.
  if (q.includes("cart") && (q.includes("what") || q.includes("in my"))) {
    const cart = cartItems;
    if (cart.length === 0) return insufficient(question, ["any items currently in the procurement cart — the cart is empty"]);
    const summary = cartSummary();
    return {
      id: nextId(),
      question,
      headline: `${summary.itemCount} item(s) in the procurement cart`,
      narrative: [
        summary.fullyCalculable
          ? `Estimated total: ${summary.currency ?? ""} ${summary.knownTotal.toLocaleString()}.`
          : summary.itemsWithKnownPrice > 0
          ? `Estimated total is partially calculable — ${summary.itemsWithKnownPrice} of ${summary.itemCount} item(s) have known pricing.`
          : "No item in the cart has a known price yet.",
        TRUST_FOOTER,
      ],
      table: { title: "Procurement Cart", columns: ["Part", "Qty", "Vendor", "Line Total"], rows: cart.map((item) => {
        const vendor = item.preferredVendorId ? getVendorById(item.preferredVendorId) : undefined;
        const total = cartItemLineTotal(item);
        return [item.partNumber, item.quantity, vendor?.name ?? "Insufficient source data.", total !== null ? total.toLocaleString() : "Insufficient source data."];
      }) },
      buttons: [{ label: "View Cart", href: "/procurement/cart" }],
    };
  }

  if (q.includes("how much") && (q.includes("procurement request") || q.includes("this request") || (q.includes("cost") && q.includes("cart")))) {
    const cart = cartItems;
    const summary = cartSummary();
    if (cart.length === 0) return insufficient(question, ["any items in the procurement cart to estimate a cost for"]);
    return {
      id: nextId(),
      question,
      headline: summary.fullyCalculable ? `Estimated cost: ${summary.currency ?? ""} ${summary.knownTotal.toLocaleString()}` : "Estimated cost is only partially calculable",
      narrative: [
        `${summary.itemsWithKnownPrice} of ${summary.itemCount} cart item(s) have known pricing.`,
        summary.itemsWithKnownPrice > 0 && !summary.fullyCalculable ? `Known portion: ${summary.currency ?? ""} ${summary.knownTotal.toLocaleString()} — the remaining item(s) have no vendor price on file.` : "",
        TRUST_FOOTER,
      ].filter(Boolean),
      buttons: [{ label: "View Cart", href: "/procurement/cart" }],
    };
  }

  // "Which vendor should we use for P/N-123?" / "which vendor for this part?"
  // / "why was this vendor recommended?" — all use the SAME deterministic
  // scoreVendorOptionsForPart() as /procurement/parts, so the AI's answer
  // and the comparison UI can never disagree.
  if (q.includes("vendor") && (q.includes("should we use") || q.includes("recommend") || q.includes("why") && q.includes("recommended"))) {
    const part = parts.find((p) => q.includes(p.partNumber.toLowerCase()));
    if (!part) return insufficient(question, ["a recognizable part number to compare vendors for"]);
    const scored = scoreVendorOptionsForPart(part.id);
    if (scored.length === 0) return insufficient(question, [`vendor availability data for ${part.partNumber} — no vendor has a recorded line for this part`]);
    const top = scored[0];
    const confidenceNote = top.confidence === "LOW" || top.confidence === "UNKNOWN"
      ? "Recommendation confidence limited by insufficient source data."
      : `Recommendation confidence: ${top.confidence}.`;
    return {
      id: nextId(),
      question,
      headline: top.score !== null ? `${top.vendorName} appears preferable for ${part.partNumber}` : `Insufficient source data to recommend a vendor for ${part.partNumber}`,
      narrative: [
        `Factors: ${top.factors.length > 0 ? top.factors.join("; ") : "no scoreable factors recorded"}.`,
        top.missingFactors.length > 0 ? `Missing: ${top.missingFactors.join("; ")}.` : "",
        confidenceNote,
        TRUST_FOOTER,
      ].filter(Boolean),
      table: { title: "Vendor Comparison", columns: ["Vendor", "Score", "Availability", "Price", "Lead Time", "Certification"], rows: scored.map((s) => [s.vendorName, s.score !== null ? String(s.score) : "Insufficient source data.", s.line.availabilityStatus.replace(/_/g, " "), s.line.unitPrice !== null ? `${s.line.currency} ${s.line.unitPrice}` : "Insufficient source data.", s.line.leadTimeDays !== null ? `${s.line.leadTimeDays}d` : "Insufficient source data.", s.line.certificationStatus.replace(/_/g, " ")]) },
      buttons: [{ label: "View Vendor", href: `/procurement/vendors/${top.vendorId}` }],
    };
  }

  // "Which parts are at procurement risk?" / "which parts have insufficient supplier data?"
  if (q.includes("procurement") && q.includes("risk") || (q.includes("parts") && q.includes("insufficient") && q.includes("supplier"))) {
    const noVendorData = partsWithoutVendorAvailability(parts.map((p) => p.id));
    return {
      id: nextId(),
      question,
      headline: `${noVendorData.length} of ${parts.length} part(s) have no vendor availability data`,
      narrative: [noVendorData.length > 0 ? "These parts have no known vendor, price, or lead time on file — a procurement blind spot, not a stock-out." : "Every part has at least one vendor availability record.", TRUST_FOOTER],
      table: noVendorData.length > 0 ? { title: "Parts Without Vendor Data", columns: ["Part Number"], rows: noVendorData.map((id) => [parts.find((p) => p.id === id)?.partNumber ?? id]) } : undefined,
      buttons: [{ label: "View Vendor Intelligence", href: "/procurement/vendors" }],
    };
  }

  // "Which AOG parts need immediate attention?"
  if (q.includes("aog") && (q.includes("part") || q.includes("attention") || q.includes("immediate"))) {
    const aogRequests = partRequests.filter((r) => r.priority === "AOG" && !["RECEIVED", "CLOSED", "REJECTED"].includes(r.status));
    if (aogRequests.length === 0) return insufficient(question, ["any open AOG-priority part request — none currently exists in the source data"]);
    return {
      id: nextId(),
      question,
      headline: `${aogRequests.length} open AOG part request(s)`,
      narrative: [aogRequests.map((r) => `${r.partNumber} for ${r.aircraftId} — status ${r.status.replace(/_/g, " ")}`).join("; "), TRUST_FOOTER],
      buttons: [{ label: "View Procurement Control Center", href: "/procurement" }],
    };
  }

  // "Which vendor has the best delivery performance?"
  if (q.includes("vendor") && q.includes("delivery") && (q.includes("best") || q.includes("performance"))) {
    const scored = vendors.filter((v) => v.deliveryScore !== null).sort((a, b) => (b.deliveryScore ?? 0) - (a.deliveryScore ?? 0));
    if (scored.length === 0) return insufficient(question, ["delivery performance data — no vendor has a recorded delivery score"]);
    return {
      id: nextId(),
      question,
      headline: `Best delivery performance: ${scored[0].name}`,
      narrative: [`Delivery score: ${scored[0].deliveryScore}.`, scored.length < vendors.length ? `${vendors.length - scored.length} of ${vendors.length} vendors have no delivery score recorded and are excluded from this ranking.` : "", TRUST_FOOTER].filter(Boolean),
      table: { title: "Vendor Delivery Scores", columns: ["Vendor", "Delivery Score"], rows: scored.map((v) => [v.name, v.deliveryScore as number]) },
      buttons: [{ label: "View Vendor Intelligence", href: "/procurement/vendors" }],
    };
  }

  // "Which pending requests should I approve first?"
  if (q.includes("pending request") || (q.includes("approve") && q.includes("first"))) {
    const pending = partRequests.filter((r) => r.status === "SUBMITTED" || r.status === "UNDER_REVIEW");
    if (pending.length === 0) return insufficient(question, ["any request currently pending approval"]);
    const ranked = [...pending].sort((a, b) => (a.priority === "AOG" ? -1 : b.priority === "AOG" ? 1 : 0));
    return {
      id: nextId(),
      question,
      headline: `${ranked.length} request(s) pending approval`,
      narrative: [`Highest priority: ${ranked[0].partNumber} (${ranked[0].priority}) for ${ranked[0].aircraftId} — ${ranked[0].reason}`, TRUST_FOOTER],
      table: { title: "Pending Requests", columns: ["Request", "Part", "Priority", "Aircraft"], rows: ranked.map((r) => [r.id, r.partNumber, r.priority, r.aircraftId]) },
      buttons: [{ label: "View Procurement Control Center", href: "/procurement" }],
    };
  }

  // "What should procurement do next?"
  if (q.includes("procurement") && (q.includes("next") || q.includes("should"))) {
    const aogOpen = partRequests.filter((r) => r.priority === "AOG" && !["RECEIVED", "CLOSED", "REJECTED"].includes(r.status));
    const noVendorData = partsWithoutVendorAvailability(parts.map((p) => p.id));
    const unapprovedVendors = vendors.filter((v) => v.approvalStatus !== "APPROVED");
    const actions: string[] = [];
    if (aogOpen.length > 0) actions.push(`Resolve ${aogOpen.length} open AOG request(s) first.`);
    if (noVendorData.length > 0) actions.push(`Source vendor coverage for ${noVendorData.length} part(s) with no vendor data.`);
    if (unapprovedVendors.length > 0) actions.push(`Review approval status for ${unapprovedVendors.length} vendor(s) not yet APPROVED.`);
    if (actions.length === 0) return insufficient(question, ["a clear procurement priority — no open AOG requests, vendor coverage gaps, or unapproved vendors were found"]);
    return {
      id: nextId(),
      question,
      headline: "Recommended procurement priorities",
      narrative: [...actions, TRUST_FOOTER],
      recommendedActions: actions,
      buttons: [{ label: "Open Procurement Control Center", href: "/procurement" }],
    };
  }

  // M11.6 (cont.) — "What part requests are waiting for approval?"
  if (q.includes("request") && (q.includes("waiting") || q.includes("wait")) && q.includes("approval")) {
    const waiting = partRequests.filter((r) => r.status === "SUBMITTED" || r.status === "UNDER_REVIEW");
    return {
      id: nextId(),
      question,
      headline: `${waiting.length} request(s) waiting for approval`,
      narrative: [TRUST_FOOTER],
      table: waiting.length > 0 ? { title: "Awaiting Approval", columns: ["Request", "Part", "Priority", "Aircraft"], rows: waiting.map((r) => [r.id, r.partNumber, r.priority, r.aircraftId]) } : undefined,
      buttons: [{ label: "Open Approval Center", href: "/procurement/approvals" }],
    };
  }

  // "Which procurement requests have missing certification?"
  if (q.includes("request") && q.includes("missing") && q.includes("certif")) {
    const flagged = partRequests.filter((r) => {
      if (!r.partId) return false;
      const scored = scoreVendorOptionsForPart(r.partId);
      const chosen = scored.find((s) => s.vendorId === (r.selectedVendorId ?? r.preferredVendorId));
      return chosen ? chosen.line.certificationStatus !== "VERIFIED" : scored.length === 0;
    });
    return {
      id: nextId(),
      question,
      headline: `${flagged.length} request(s) with missing/unverified certification`,
      narrative: [flagged.length > 0 ? "Certificate status is not VERIFIED for the vendor line associated with these requests — this is an evidence gap, not confirmed non-compliance." : "No open request currently has a missing-certification vendor line.", TRUST_FOOTER],
      table: flagged.length > 0 ? { title: "Certification Gaps", columns: ["Request", "Part", "Status"], rows: flagged.map((r) => [r.id, r.partNumber, r.status.replace(/_/g, " ")]) } : undefined,
      buttons: [{ label: "Open Approval Center", href: "/procurement/approvals" }],
    };
  }

  // "Which approved requests do not yet have a purchase order?"
  if (q.includes("approved") && q.includes("request") && (q.includes("purchase order") || q.includes("po"))) {
    const poRequestIds = new Set(purchaseOrders.flatMap((po) => po.requestIds));
    const noPo = partRequests.filter((r) => r.status === "APPROVED" && !poRequestIds.has(r.id));
    return {
      id: nextId(),
      question,
      headline: `${noPo.length} approved request(s) without a purchase order`,
      narrative: [TRUST_FOOTER],
      table: noPo.length > 0 ? { title: "Approved, No PO Yet", columns: ["Request", "Part", "Aircraft"], rows: noPo.map((r) => [r.id, r.partNumber, r.aircraftId]) } : undefined,
      buttons: [{ label: "View Purchase Orders", href: "/procurement/purchase-orders" }],
    };
  }

  // "Which purchase orders are awaiting vendor response?"
  if (q.includes("purchase order") && (q.includes("awaiting") || q.includes("waiting")) ) {
    const awaiting = purchaseOrders.filter((po) => po.status === "SENT" && !po.vendorAcknowledgedAt);
    return {
      id: nextId(),
      question,
      headline: `${awaiting.length} purchase order(s) awaiting vendor acknowledgement`,
      narrative: [TRUST_FOOTER],
      table: awaiting.length > 0 ? { title: "Awaiting Vendor Response", columns: ["PO", "Vendor", "Sent"], rows: awaiting.map((po) => [po.poNumber, po.vendorId, po.sentAt ?? "Insufficient source data."]) } : undefined,
      buttons: [{ label: "View Purchase Orders", href: "/procurement/purchase-orders" }],
    };
  }

  // "Generate a procurement report."
  if (q.includes("procurement") && (q.includes("report") || q.includes("performance"))) {
    return {
      id: nextId(),
      question,
      headline: "Procurement Intelligence Report",
      narrative: ["Generating the visual procurement report from current vendor, request, and spend data.", TRUST_FOOTER],
      buttons: [{ label: "Open Procurement Report", href: "/reports/procurement-intelligence" }],
      suggestGenerateReport: { reportId: "procurement-intelligence", title: "Procurement Intelligence Report", scope: "Fleet-wide" },
    };
  }

  // "What is our margin?" (fleet-wide)
  if (q.includes("margin") && !q.includes("aircraft")) {
    const fleet = getFleetFinancialSummary(workOrders.map((w) => w.id));
    if (fleet.grossMargin === null) return insufficient(question, ["fleet-wide margin — no work order with cost data also has a recorded customer charge"]);
    return {
      id: nextId(),
      question,
      headline: "Fleet-wide gross margin",
      narrative: [
        `Gross margin: ${fleet.grossMargin.toLocaleString()} USD across ${fleet.workOrdersWithCharge} of ${fleet.workOrdersWithCostData} costed work order(s) that also have a customer charge on file.`,
        fleet.workOrdersWithCostData < fleet.totalWorkOrders ? `${fleet.totalWorkOrders - fleet.workOrdersWithCostData} of ${fleet.totalWorkOrders} work orders have no cost data at all and are excluded from this figure.` : "",
        TRUST_FOOTER,
      ].filter(Boolean),
      buttons: [{ label: "View Financial Intelligence", href: "/finance" }],
    };
  }

  // "How much should we charge the customer?" — NEVER estimate a price;
  // only report what has already been recorded for a named work order.
  if (q.includes("charge") && (q.includes("customer") || q.includes("should we"))) {
    const wo = findWorkOrderFromText(question);
    if (!wo) return insufficient(question, ["a specific work order — and even then, this system reports the recorded customer charge, it does not calculate a recommended price without a markup/rate-card model, which does not exist in the current domain model"]);
    const charge = getWorkOrderCostSummary(wo.id);
    if (!charge || charge.customerCharge === null) return insufficient(question, [`a recorded customer charge for ${wo.workOrderNumber}`]);
    return {
      id: nextId(),
      question,
      headline: `${wo.workOrderNumber} — recorded customer charge`,
      narrative: [`Recorded customer charge: ${charge.customerCharge.toLocaleString()} USD against a total cost of ${charge.totalCost.toLocaleString()} USD.`, "This is the recorded charge, not a system-generated price recommendation — no markup/rate-card model exists in the current domain model.", TRUST_FOOTER],
      buttons: [{ label: "View Financial Detail", href: `/finance/${wo.id}` }],
    };
  }

  // "What caused the cost increase?" — no historical/period-over-period
  // cost data exists anywhere, so this is honestly unanswerable.
  if (q.includes("cost") && (q.includes("increase") || q.includes("caused"))) {
    return insufficient(question, ["cost history/trend data — only a single current snapshot of cost records exists; there is no prior-period data to compare against"]);
  }

  // Generic cost/charge/margin/spend catch-all — the topic is financial,
  // but no branch above matched a specific, answerable shape of it.
  if (q.includes("cost") || q.includes("costing") || q.includes("charge") || q.includes("margin") || q.includes("expensive") || q.includes("spend")) {
    return insufficient(question, ["a more specific financial question — try naming an aircraft or work order, or ask 'which aircraft is most expensive to maintain?' / 'what is our margin?' / 'which vendors cost us the most?'"]);
  }

  return insufficient(question, [
    "a recognized topic — try a project number, aircraft registration, work order number, or one of the suggested questions",
  ]);
}

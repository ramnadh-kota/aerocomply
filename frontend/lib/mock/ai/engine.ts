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

import { maintenanceProjects } from "../maintenanceProjects";
import { getAircraftByRegistration } from "../aircraft";
import { workOrders } from "../workOrders";
import { findingsForWorkOrder } from "../findings";
import { defectsForWorkOrder } from "../defects";
import { getInspectorReviewForWorkOrder } from "../inspectorReviews";
import {
  getProjectAnalytics,
  getAircraftAnalytics,
  getMaintenanceAnalytics,
  getComplianceAnalytics,
  getInspectionAnalytics,
  getFleetAnalytics,
  assessmentDiffSummary,
  type KpiCard,
  type RiskItem,
} from "./analytics";

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
}

export const SUGGESTED_QUESTIONS = [
  "Give me analytics of Project PRJ-2026-001.",
  "Which work orders are at risk?",
  "Why is VT-ABC showing compliance risk?",
  "What inspections are waiting for review?",
  "Which aircraft have open compliance actions?",
  "Show me overdue maintenance activities.",
  "Why was WO-1042 blocked?",
  "What changed between assessment asmt-1 and asmt-2?",
  "What are the biggest maintenance risks this week?",
];

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
  const tokens = text.toUpperCase().match(/[A-Z0-9]{4,7}/g) ?? [];
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

const TRUST_FOOTER = "AI Prototype · Based on current AeroComply demo data · Non-authoritative · Human review required.";

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

export function answerQuestion(question: string): AiResponse {
  const q = question.toLowerCase();

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
        buttons: [
          { label: "View Assessment", href: `/assessments/${ids[1]}` },
        ],
      };
    }
    return insufficient(question, ["two assessment IDs to compare (e.g. asmt-1 and asmt-2)"]);
  }

  // "Why was WO-1042 blocked?"
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
      narrative.push(TRUST_FOOTER);
      return {
        id: nextId(),
        question,
        headline: `${wo.workOrderNumber} — why it's blocked`,
        narrative,
        buttons: [
          { label: "View Work Order", href: `/maintenance/work-orders/${wo.id}` },
          ...(review ? [{ label: "View Inspection", href: `/maintenance/inspections/${review.id}` }] : []),
        ],
      };
    }
    return insufficient(question, ["a recognizable work order number, e.g. WO-1042"]);
  }

  // Project analytics / report
  if (q.includes("project") && (q.includes("analytic") || q.includes("health") || q.includes("summary") || q.includes("analyze"))) {
    const project = findProjectFromText(question) ?? maintenanceProjects[0];
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
    };
  }

  // Which work orders are at risk
  if (q.includes("work orders") && q.includes("risk")) {
    const m = getMaintenanceAnalytics();
    return {
      id: nextId(),
      question,
      headline: "Work orders at risk",
      narrative: [
        `${m.overdue.length} overdue, ${m.waitingParts} waiting on parts, ${m.waitingInspection} waiting on inspection.`,
        TRUST_FOOTER,
      ],
      kpis: m.kpis,
      table: { title: "Overdue Work Orders", columns: ["Work Order", "Due Date", "Priority"], rows: m.overdue.map((w) => [w.label, w.dueDate, w.priority]) },
      buttons: [{ label: "View Work Orders", href: "/maintenance/work-orders" }, { label: "Generate Report", href: "/reports/fleet-risk" }],
    };
  }

  // Overdue maintenance
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
        `${insp.pending.length} inspection(s) pending. ${q.includes("priorit") ? "Ranked by work order priority (CRITICAL first) — this is a suggested review order, not an automatic decision." : ""}`,
        TRUST_FOOTER,
      ],
      kpis: insp.kpis,
      table: { title: "Inspection Queue", columns: ["Work Order", "Priority"], rows: insp.pending.map((p) => [p.label, p.priority]) },
      buttons: [
        { label: "Open Inspection Queue", href: "/maintenance/inspections" },
        { label: "Generate Report", href: "/reports/inspection-queue" },
      ],
    };
  }

  // Aircraft compliance risk explanation
  if (q.includes("compliance risk") || (q.includes("why") && findAircraftFromText(question))) {
    const a = findAircraftFromText(question);
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
    };
  }

  return insufficient(question, [
    "a recognized topic — try a project number, aircraft registration, work order number, or one of the suggested questions",
  ]);
}

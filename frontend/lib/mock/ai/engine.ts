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
import { getAircraftByRegistration, getAircraftById, currentRegistration } from "../aircraft";
import { workOrders, isOverdue } from "../workOrders";
import { findings, findingsForWorkOrder } from "../findings";
import { defects, defectsForAircraft, defectsForWorkOrder } from "../defects";
import { getInspectorReviewForWorkOrder } from "../inspectorReviews";
import { getChecklistByWorkOrderId } from "../checklists";
import { evidenceForAssessment } from "../evidence";
import { overdueMaintenanceEvents, maintenanceEventsForAircraft, upcomingMaintenanceEvents } from "../maintenance";
import { assessments } from "../assessments";
import { getTechnicianById } from "../technicians";
import { partsForWorkOrder } from "../parts";
import { certificatesForPart, traceabilityStatusForPart } from "../partTraceability";
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

export function answerQuestion(question: string, context?: AiQuestionContext): AiResponse {
  const q = question.toLowerCase();

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

  // Which work orders need attention / at risk / backlog
  if ((q.includes("work orders") || q.includes("work order")) && (q.includes("risk") || q.includes("attention") || q.includes("backlog"))) {
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
  if (q.includes("tat") && (q.includes("risk") || q.includes("why"))) {
    const wo = findWorkOrderFromText(question) ?? (context?.aircraftId ? workOrders.find((w) => w.aircraftId === context.aircraftId && w.status !== "COMPLETED" && w.status !== "CANCELLED") : undefined);
    if (!wo) return insufficient(question, ["a recognizable work order number or an aircraft context with active work"]);
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
  if (q.includes("what should happen next") || q.includes("next step") || (q.includes("recommend") && q.includes("next"))) {
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

  return insufficient(question, [
    "a recognized topic — try a project number, aircraft registration, work order number, or one of the suggested questions",
  ]);
}

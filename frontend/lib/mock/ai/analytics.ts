// Analytics builders — all values are DERIVED from existing mock datasets,
// never randomly invented. This is the layer the AI engine (./engine.ts) and
// the report builder (../reports.ts) both read from, so a number shown in an
// AI answer always matches the number shown in a generated report.

import { maintenanceProjects, workPackages, getProjectById } from "../maintenanceProjects";
import { workOrders, isOverdue, workOrdersForProject, workOrdersForAircraft } from "../workOrders";
import { partsForWorkOrder } from "../parts";
import { defects, defectsForAircraft } from "../defects";
import { inspectorReviews } from "../inspectorReviews";
import { getAircraftById, aircraft, currentRegistration } from "../aircraft";
import { assessmentsForAircraft, getAssessmentById } from "../assessments";
import { getRequirementById } from "../regulations";
import type { WorkOrder, Priority } from "../types";

export type RiskLevel = "LOW" | "MEDIUM" | "HIGH";

export interface RiskItem {
  label: string;
  detail: string;
  level: RiskLevel;
  href?: string;
}

export interface KpiCard {
  label: string;
  value: string;
  tone?: "neutral" | "good" | "warning" | "bad";
}

export interface ProjectAnalytics {
  projectId: string;
  projectNumber: string;
  title: string;
  aircraftId: string;
  aircraftRegistration: string;
  health: "ON_TRACK" | "AT_RISK" | "CRITICAL";
  kpis: KpiCard[];
  workPackageProgress: { label: string; percent: number }[];
  workOrderStatusDistribution: { label: string; count: number }[];
  risks: RiskItem[];
  complianceExposure: "LOW" | "MEDIUM" | "HIGH";
  recommendedActions: string[];
}

export function getProjectAnalytics(projectId: string): ProjectAnalytics | null {
  const project = getProjectById(projectId);
  if (!project) return null;
  const wos = workOrdersForProject(projectId);
  const wps = workPackages.filter((wp) => wp.projectId === projectId);
  const aircraftRow = getAircraftById(project.aircraftId);

  const completeWps = wps.filter((wp) => wp.status === "COMPLETED").length;
  const openWos = wos.filter((w) => w.status !== "COMPLETED" && w.status !== "CANCELLED");
  const overdueWos = wos.filter((w) => isOverdue(w));
  const waitingPartsWos = wos.filter((w) => w.status === "WAITING_PARTS");
  const waitingInspectionWos = wos.filter((w) => w.status === "WAITING_INSPECTION");
  const partsWaiting = wos.flatMap((w) => partsForWorkOrder(w.id)).filter((p) => p.status !== "IN_STOCK");
  const criticalDefects = defectsForAircraft(project.aircraftId).filter((d) => d.severity === "CRITICAL" || d.severity === "HIGH");

  const complianceExposure: ProjectAnalytics["complianceExposure"] =
    criticalDefects.length > 0 || project.priority === "CRITICAL" ? "HIGH" : overdueWos.length > 0 ? "MEDIUM" : "LOW";

  const health: ProjectAnalytics["health"] =
    overdueWos.length > 0 && complianceExposure === "HIGH"
      ? "CRITICAL"
      : overdueWos.length > 0 || waitingPartsWos.length > 0 || complianceExposure === "MEDIUM"
      ? "AT_RISK"
      : "ON_TRACK";

  const statusCounts = new Map<string, number>();
  for (const w of wos) statusCounts.set(w.status, (statusCounts.get(w.status) ?? 0) + 1);

  const risks: RiskItem[] = [];
  for (const w of waitingPartsWos) {
    risks.push({ label: `${w.workOrderNumber} waiting on parts`, detail: w.title, level: "MEDIUM", href: `/maintenance/work-orders/${w.id}` });
  }
  for (const w of waitingInspectionWos) {
    risks.push({ label: `${w.workOrderNumber} inspection pending`, detail: w.title, level: "MEDIUM", href: `/maintenance/work-orders/${w.id}` });
  }
  for (const w of overdueWos) {
    risks.push({ label: `${w.workOrderNumber} overdue`, detail: `Due ${w.dueDate}, priority ${w.priority}`, level: w.priority === "CRITICAL" ? "HIGH" : "HIGH", href: `/maintenance/work-orders/${w.id}` });
  }
  for (const note of project.riskNotes) {
    risks.push({ label: "Project risk note", detail: note, level: "MEDIUM" });
  }

  return {
    projectId: project.id,
    projectNumber: project.projectNumber,
    title: project.title,
    aircraftId: project.aircraftId,
    aircraftRegistration: aircraftRow ? currentRegistration(aircraftRow) : project.aircraftId,
    health,
    kpis: [
      { label: "Work Packages", value: `${completeWps}/${wps.length} complete`, tone: completeWps === wps.length ? "good" : "neutral" },
      { label: "Open Work Orders", value: String(openWos.length), tone: openWos.length > 2 ? "warning" : "neutral" },
      { label: "Overdue", value: String(overdueWos.length), tone: overdueWos.length > 0 ? "bad" : "good" },
      { label: "Parts Waiting", value: String(partsWaiting.length), tone: partsWaiting.length > 0 ? "warning" : "good" },
      { label: "Inspection Pending", value: String(waitingInspectionWos.length), tone: waitingInspectionWos.length > 0 ? "warning" : "good" },
      { label: "Compliance Exposure", value: complianceExposure, tone: complianceExposure === "HIGH" ? "bad" : complianceExposure === "MEDIUM" ? "warning" : "good" },
    ],
    workPackageProgress: wps.map((wp) => ({ label: wp.title, percent: wp.completionPercent })),
    workOrderStatusDistribution: Array.from(statusCounts.entries()).map(([label, count]) => ({ label, count })),
    risks,
    complianceExposure,
    recommendedActions: buildRecommendations({ waitingPartsWos, waitingInspectionWos, overdueWos }),
  };
}

function buildRecommendations(input: { waitingPartsWos: WorkOrder[]; waitingInspectionWos: WorkOrder[]; overdueWos: WorkOrder[] }): string[] {
  const actions: string[] = [];
  for (const w of input.waitingPartsWos) {
    const p = partsForWorkOrder(w.id)[0];
    actions.push(p ? `Expedite part ${p.partNumber} for ${w.workOrderNumber}` : `Resolve parts blocker on ${w.workOrderNumber}`);
  }
  for (const w of input.waitingInspectionWos) actions.push(`Review ${w.workOrderNumber} in the Inspection Queue`);
  for (const w of input.overdueWos) actions.push(`Escalate overdue ${w.workOrderNumber} (${w.priority} priority)`);
  return actions.slice(0, 6);
}

export interface AircraftAnalytics {
  aircraftId: string;
  registration: string;
  openWorkOrders: number;
  overdueWorkOrders: number;
  openDefects: number;
  criticalOrHighDefects: number;
  complianceRisk: "LOW" | "MEDIUM" | "HIGH";
  reasons: string[];
  kpis: KpiCard[];
}

export function getAircraftAnalytics(aircraftId: string): AircraftAnalytics | null {
  const a = getAircraftById(aircraftId);
  if (!a) return null;
  const wos = workOrdersForAircraft(aircraftId);
  const openWos = wos.filter((w) => w.status !== "COMPLETED" && w.status !== "CANCELLED");
  const overdue = wos.filter((w) => isOverdue(w));
  const defs = defectsForAircraft(aircraftId);
  const openDefs = defs.filter((d) => d.status === "OPEN");
  const seriousDefs = openDefs.filter((d) => d.severity === "HIGH" || d.severity === "CRITICAL");
  const assessments = assessmentsForAircraft(aircraftId);
  const reviewNeeded = assessments.filter((asmt) => asmt.finalStatus === "REVIEW_REQUIRED" || asmt.finalStatus === "NON_COMPLIANT");

  const reasons: string[] = [];
  if (overdue.length > 0) reasons.push(`${overdue.length} overdue work order(s)`);
  if (seriousDefs.length > 0) reasons.push(`${seriousDefs.length} open HIGH/CRITICAL defect(s)`);
  if (reviewNeeded.length > 0) reasons.push(`${reviewNeeded.length} assessment(s) requiring review or non-compliant`);

  const complianceRisk: AircraftAnalytics["complianceRisk"] =
    seriousDefs.length > 0 || reviewNeeded.length > 0 ? "HIGH" : overdue.length > 0 ? "MEDIUM" : "LOW";

  return {
    aircraftId,
    registration: currentRegistration(a),
    openWorkOrders: openWos.length,
    overdueWorkOrders: overdue.length,
    openDefects: openDefs.length,
    criticalOrHighDefects: seriousDefs.length,
    complianceRisk,
    reasons: reasons.length ? reasons : ["No overdue work, no serious open defects, no assessments requiring review."],
    kpis: [
      { label: "Open Work Orders", value: String(openWos.length) },
      { label: "Overdue", value: String(overdue.length), tone: overdue.length > 0 ? "bad" : "good" },
      { label: "Open Defects", value: String(openDefs.length), tone: openDefs.length > 0 ? "warning" : "good" },
      { label: "Compliance Risk", value: complianceRisk, tone: complianceRisk === "HIGH" ? "bad" : complianceRisk === "MEDIUM" ? "warning" : "good" },
    ],
  };
}

export interface MaintenanceAnalytics {
  totalOpenWorkOrders: number;
  overdue: { id: string; label: string; dueDate: string; priority: Priority; href: string }[];
  waitingParts: number;
  waitingInspection: number;
  openDefectsBySeverity: Record<string, number>;
  kpis: KpiCard[];
}

export function getMaintenanceAnalytics(): MaintenanceAnalytics {
  const open = workOrders.filter((w) => w.status !== "COMPLETED" && w.status !== "CANCELLED");
  const overdue = workOrders.filter((w) => isOverdue(w));
  const waitingParts = workOrders.filter((w) => w.status === "WAITING_PARTS").length;
  const waitingInspection = workOrders.filter((w) => w.status === "WAITING_INSPECTION").length;
  const bySeverity: Record<string, number> = {};
  for (const d of defects.filter((d) => d.status === "OPEN")) bySeverity[d.severity] = (bySeverity[d.severity] ?? 0) + 1;

  return {
    totalOpenWorkOrders: open.length,
    overdue: overdue.map((w) => ({ id: w.id, label: w.workOrderNumber, dueDate: w.dueDate, priority: w.priority, href: `/maintenance/work-orders/${w.id}` })),
    waitingParts,
    waitingInspection,
    openDefectsBySeverity: bySeverity,
    kpis: [
      { label: "Open Work Orders", value: String(open.length) },
      { label: "Overdue", value: String(overdue.length), tone: overdue.length > 0 ? "bad" : "good" },
      { label: "Waiting Parts", value: String(waitingParts), tone: waitingParts > 0 ? "warning" : "good" },
      { label: "Waiting Inspection", value: String(waitingInspection), tone: waitingInspection > 0 ? "warning" : "good" },
    ],
  };
}

export interface ComplianceAnalytics {
  totalAssessments: number;
  compliant: number;
  nonCompliant: number;
  reviewRequired: number;
  insufficientData: number;
  kpis: KpiCard[];
}

export function getComplianceAnalytics(): ComplianceAnalytics {
  const all = aircraft.flatMap((a) => assessmentsForAircraft(a.id));
  const count = (s: string) => all.filter((a) => a.finalStatus === s).length;
  const compliant = count("COMPLIANT");
  const nonCompliant = count("NON_COMPLIANT");
  const reviewRequired = count("REVIEW_REQUIRED");
  const insufficientData = count("INSUFFICIENT_DATA");
  return {
    totalAssessments: all.length,
    compliant,
    nonCompliant,
    reviewRequired,
    insufficientData,
    kpis: [
      { label: "Compliant", value: String(compliant), tone: "good" },
      { label: "Non-Compliant", value: String(nonCompliant), tone: nonCompliant > 0 ? "bad" : "good" },
      { label: "Review Required", value: String(reviewRequired), tone: reviewRequired > 0 ? "warning" : "good" },
      { label: "Insufficient Data", value: String(insufficientData), tone: insufficientData > 0 ? "warning" : "good" },
    ],
  };
}

export interface InspectionAnalytics {
  pending: { id: string; workOrderId: string; label: string; href: string; priority: Priority }[];
  approved: number;
  rejected: number;
  returned: number;
  kpis: KpiCard[];
}

export function getInspectionAnalytics(): InspectionAnalytics {
  const pendingReviews = inspectorReviews.filter((r) => r.status === "PENDING_INSPECTION");
  const pending = pendingReviews.map((r) => {
    const wo = workOrders.find((w) => w.id === r.workOrderId);
    return { id: r.id, workOrderId: r.workOrderId, label: wo?.workOrderNumber ?? r.workOrderId, href: `/maintenance/inspections/${r.id}`, priority: wo?.priority ?? ("MEDIUM" as Priority) };
  });
  // Rank pending inspections by priority for the "prioritize" AI query.
  const rank: Record<Priority, number> = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 };
  pending.sort((a, b) => rank[a.priority] - rank[b.priority]);
  return {
    pending,
    approved: inspectorReviews.filter((r) => r.status === "APPROVED").length,
    rejected: inspectorReviews.filter((r) => r.status === "REJECTED").length,
    returned: inspectorReviews.filter((r) => r.status === "RETURNED_FOR_CORRECTION").length,
    kpis: [
      { label: "Awaiting Review", value: String(pending.length), tone: pending.length > 0 ? "warning" : "good" },
      { label: "Approved", value: String(inspectorReviews.filter((r) => r.status === "APPROVED").length), tone: "good" },
      { label: "Rejected", value: String(inspectorReviews.filter((r) => r.status === "REJECTED").length) },
      { label: "Returned", value: String(inspectorReviews.filter((r) => r.status === "RETURNED_FOR_CORRECTION").length) },
    ],
  };
}

export interface FleetAnalytics {
  fleetSize: number;
  openWorkOrders: number;
  overdueWorkOrders: number;
  openDefects: number;
  aircraftAtRisk: { aircraftId: string; registration: string; risk: RiskLevel }[];
  kpis: KpiCard[];
}

export function getFleetAnalytics(): FleetAnalytics {
  const maint = getMaintenanceAnalytics();
  const atRisk = aircraft
    .map((a) => {
      const analytics = getAircraftAnalytics(a.id)!;
      return { aircraftId: a.id, registration: analytics.registration, risk: analytics.complianceRisk as RiskLevel };
    })
    .filter((a) => a.risk !== "LOW");

  return {
    fleetSize: aircraft.length,
    openWorkOrders: maint.totalOpenWorkOrders,
    overdueWorkOrders: maint.overdue.length,
    openDefects: defects.filter((d) => d.status === "OPEN").length,
    aircraftAtRisk: atRisk,
    kpis: [
      { label: "Fleet Size", value: String(aircraft.length) },
      { label: "Open Work Orders", value: String(maint.totalOpenWorkOrders) },
      { label: "Overdue", value: String(maint.overdue.length), tone: maint.overdue.length > 0 ? "bad" : "good" },
      { label: "Aircraft At Risk", value: String(atRisk.length), tone: atRisk.length > 0 ? "warning" : "good" },
    ],
  };
}

export function assessmentDiffSummary(assessmentAId: string, assessmentBId: string): { found: boolean; summary: string[] } {
  const a = getAssessmentById(assessmentAId);
  const b = getAssessmentById(assessmentBId);
  if (!a || !b) return { found: false, summary: [] };
  const summary: string[] = [];
  if (a.finalStatus !== b.finalStatus) summary.push(`Final status changed: ${a.finalStatus} → ${b.finalStatus}`);
  if (a.systemResult !== b.systemResult) summary.push(`System result changed: ${a.systemResult} → ${b.systemResult}`);
  if (a.humanDecision !== b.humanDecision) summary.push(`Human decision changed: ${a.humanDecision} → ${b.humanDecision}`);
  if (a.ruleVersion !== b.ruleVersion) summary.push(`Rule version changed: ${a.ruleVersion} → ${b.ruleVersion}`);
  if (a.evidenceIds.length !== b.evidenceIds.length) summary.push(`Evidence count changed: ${a.evidenceIds.length} → ${b.evidenceIds.length}`);
  if (b.changeReason) summary.push(`Change reason recorded: ${b.changeReason}`);
  if (summary.length === 0) summary.push("No material differences detected between these two assessment versions.");
  return { found: true, summary };
}

export function requirementLabel(requirementId: string | null): string {
  if (!requirementId) return "—";
  const req = getRequirementById(requirementId);
  return req ? `${req.requirementType} ${req.requirementNumber}` : requirementId;
}

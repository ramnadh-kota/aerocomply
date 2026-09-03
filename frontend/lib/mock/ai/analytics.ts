// Analytics builders — all values are DERIVED from existing mock datasets,
// never randomly invented. This is the layer the AI engine (./engine.ts) and
// the report builder (../reports.ts) both read from, so a number shown in an
// AI answer always matches the number shown in a generated report.

import { maintenanceProjects, workPackages, getProjectById } from "../maintenanceProjects";
import { workOrders, isOverdue, workOrdersForProject, workOrdersForAircraft, workOrdersForTechnician, MOCK_TODAY } from "../workOrders";
import { parts, partsForWorkOrder, getPartById } from "../parts";
import { defects, defectsForAircraft, defectsForWorkOrder } from "../defects";
import { inspectorReviews, getInspectorReviewForWorkOrder } from "../inspectorReviews";
import { getAircraftById, aircraft, currentRegistration, getAircraftVariant } from "../aircraft";
import { assessmentsForAircraft, getAssessmentById } from "../assessments";
import { getRequirementById } from "../regulations";
import { technicians, getTechnicianById, isOnShiftNow } from "../technicians";
import { upcomingMaintenanceEvents } from "../maintenance";
import { vendorPartAvailabilityForPart, scoreVendorOptionsForPart, cartItems, partRequests, purchaseOrders, getVendorById } from "../procurement";
import { getMaintenanceTaskById } from "../maintenanceTasks";
import { deferredItems } from "../deferredItems";
import { cannibalizationRequests } from "../cannibalization";
import type { WorkOrder, Priority, Defect, Technician, ExecutionState, SafetyGate, SignatureRecord, AutomationQueueItem } from "../types";

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

// --- M0.6 Operations Command Center additions ---
// Same rule as above: every value here is derived from existing mock data,
// nothing invented. "Grounded" is a derived heuristic (an aircraft with an
// open HIGH/CRITICAL defect), not a new AircraftStatus value — Aircraft
// status stays ACTIVE/STORED/WRITTEN_OFF exactly as defined in types.ts.

export interface TechnicianWorkload {
  technicianId: string;
  name: string;
  openWorkOrders: number;
  overdueWorkOrders: number;
  onShift: boolean;
}

export function getTechnicianWorkload(): TechnicianWorkload[] {
  return technicians.map((t) => {
    const assigned = workOrders.filter((w) => w.assignedTechnicianId === t.id && w.status !== "COMPLETED" && w.status !== "CANCELLED");
    return {
      technicianId: t.id,
      name: t.name,
      openWorkOrders: assigned.length,
      overdueWorkOrders: assigned.filter((w) => isOverdue(w)).length,
      onShift: isOnShiftNow(t),
    };
  });
}

export function getPartsAtRisk(): { partNumber: string; description: string; status: string; workOrderId: string | null }[] {
  return parts
    .filter((p) => p.status !== "IN_STOCK")
    .map((p) => ({ partNumber: p.partNumber, description: p.description, status: p.status, workOrderId: p.workOrderId }));
}

export interface OperationsAnalytics {
  aircraftRequiringMaintenance: { aircraftId: string; registration: string }[];
  aircraftGrounded: { aircraftId: string; registration: string; reason: string }[];
  openProjects: number;
  openWorkOrders: number;
  workOrderStatusCounts: Record<string, number>;
  overdue: number;
  highPriority: number;
  openDefects: number;
  unknownChecklistWorkOrderIds: string[];
  pendingInspections: number;
  technicianWorkload: TechnicianWorkload[];
  partsAtRisk: ReturnType<typeof getPartsAtRisk>;
  activeProjectCount: number;
}

export function getOperationsAnalytics(unknownChecklistWorkOrderIds: string[] = []): OperationsAnalytics {
  const withOpenWos = new Set(workOrders.filter((w) => w.status !== "COMPLETED" && w.status !== "CANCELLED").map((w) => w.aircraftId));
  const aircraftRequiringMaintenance = aircraft
    .filter((a) => withOpenWos.has(a.id))
    .map((a) => ({ aircraftId: a.id, registration: currentRegistration(a) }));

  const aircraftGrounded = aircraft
    .map((a) => {
      const seriousDefect = defectsForAircraft(a.id).find((d) => d.status === "OPEN" && (d.severity === "HIGH" || d.severity === "CRITICAL"));
      return seriousDefect ? { aircraftId: a.id, registration: currentRegistration(a), reason: seriousDefect.description } : null;
    })
    .filter((x): x is { aircraftId: string; registration: string; reason: string } => x !== null);

  const statusCounts: Record<string, number> = {};
  for (const w of workOrders) statusCounts[w.status] = (statusCounts[w.status] ?? 0) + 1;

  const openWos = workOrders.filter((w) => w.status !== "COMPLETED" && w.status !== "CANCELLED");
  const openProjects = maintenanceProjects.filter((p) => p.status === "IN_PROGRESS" || p.status === "PLANNED").length;

  return {
    aircraftRequiringMaintenance,
    aircraftGrounded,
    openProjects,
    openWorkOrders: openWos.length,
    workOrderStatusCounts: statusCounts,
    overdue: workOrders.filter((w) => isOverdue(w)).length,
    highPriority: openWos.filter((w) => w.priority === "HIGH" || w.priority === "CRITICAL").length,
    openDefects: defects.filter((d) => d.status === "OPEN").length,
    unknownChecklistWorkOrderIds,
    pendingInspections: inspectorReviews.filter((r) => r.status === "PENDING_INSPECTION").length,
    technicianWorkload: getTechnicianWorkload(),
    partsAtRisk: getPartsAtRisk(),
    activeProjectCount: openProjects,
  };
}

export function assessmentUnknownReasons(assessmentId: string): string[] {
  const a = getAssessmentById(assessmentId);
  if (!a) return [];
  const unknownConditions = a.conditionEvaluations.filter((c) => c.result === "UNKNOWN");
  if (unknownConditions.length === 0) return ["No condition on this assessment is currently UNKNOWN."];
  return unknownConditions.map((c) => `${c.label}: expected ${c.expected}, actual ${c.actual ?? "not recorded"}${c.note ? ` — ${c.note}` : ""}`);
}

// --- M12.1 Maintenance Control Tower additions ---
// Same rule as the Operations Command Center above: every KPI and risk
// reason here is derived from existing mock data (Aircraft, WorkOrder,
// Defect, Part). Aircraft status stays ACTIVE/STORED/WRITTEN_OFF exactly as
// defined in types.ts — "Operational"/"Under Maintenance"/"AOG" below are
// derived operational-state labels for the tower's fleet view, not new
// AircraftStatus values, following the same pattern as the existing
// aircraftGrounded heuristic in getOperationsAnalytics(). There is no
// Flight/schedule concept anywhere in the mock dataset — "next flight" is
// never computed here; callers must render "Insufficient source data."
// rather than infer one.

export type OperationalStatus = "OPERATIONAL" | "UNDER_MAINTENANCE" | "AOG" | "STORED" | "WRITTEN_OFF";

export interface AircraftRiskAssessment {
  aircraftId: string;
  registration: string;
  risk: RiskLevel;
  reasons: string[];
}

/** Explainable operational risk for one aircraft — every reason traces to a
 * real record (open defect, open work order, or a part shortage tied to one
 * of this aircraft's work orders). Never fabricates a flight-schedule or
 * location-based reason, since no such data exists in the mock dataset. */
export function getAircraftOperationalRisk(aircraftId: string): AircraftRiskAssessment | null {
  const a = getAircraftById(aircraftId);
  if (!a) return null;
  const registration = currentRegistration(a);
  const defs = defectsForAircraft(aircraftId);
  const openDefs = defs.filter((d) => d.status === "OPEN");
  const seriousOpenDefs = openDefs.filter((d) => d.severity === "HIGH" || d.severity === "CRITICAL");
  const wos = workOrdersForAircraft(aircraftId);
  const openWos = wos.filter((w) => w.status !== "COMPLETED" && w.status !== "CANCELLED");
  const criticalOpenWos = openWos.filter((w) => w.priority === "CRITICAL" || w.priority === "HIGH");
  const overdueWos = wos.filter((w) => isOverdue(w));

  // Recurring signal: this aircraft has more than one defect (any status)
  // recorded against the same ATA chapter.
  const byChapter = new Map<string, Defect[]>();
  for (const d of defs) byChapter.set(d.ataChapter, [...(byChapter.get(d.ataChapter) ?? []), d]);
  const recurringChapters = Array.from(byChapter.entries()).filter(([, list]) => list.length > 1);

  // Material shortage tied to one of this aircraft's own work orders.
  const woIds = new Set(wos.map((w) => w.id));
  const shortageParts = getPartsAtRisk().filter((p) => p.workOrderId && woIds.has(p.workOrderId));

  const reasons: string[] = [];
  for (const [chapter, list] of recurringChapters) {
    reasons.push(`${list.length} recurring defect(s) in ATA ${chapter}`);
  }
  if (criticalOpenWos.length > 0) reasons.push(`${criticalOpenWos.length} open HIGH/CRITICAL-priority work order(s)`);
  if (seriousOpenDefs.length > 0) reasons.push(`${seriousOpenDefs.length} open HIGH/CRITICAL-severity defect(s)`);
  if (shortageParts.length > 0) reasons.push(`Required part unavailable: ${shortageParts.map((p) => p.partNumber).join(", ")}`);
  if (overdueWos.length > 0) reasons.push(`${overdueWos.length} overdue work order(s)`);

  const risk: RiskLevel = seriousOpenDefs.length > 0 || reasons.length >= 2 ? "HIGH" : reasons.length === 1 ? "MEDIUM" : "LOW";

  return {
    aircraftId,
    registration,
    risk,
    reasons: reasons.length > 0 ? reasons : ["No open serious defects, no critical work orders, no material shortages, and no recurring defect pattern found."],
  };
}

export interface ControlTowerAircraftRow {
  aircraftId: string;
  registration: string;
  model: string;
  operationalStatus: OperationalStatus;
  aogReason: string | null;
  openWorkOrders: number;
  openDefects: number;
  criticalOpenDefects: number;
  nextMaintenanceDue: string | null;
  materialShortageCount: number;
  risk: AircraftRiskAssessment;
}

/** One row per aircraft for the Control Tower fleet table. Location and next
 * flight are deliberately absent — no such data exists in the mock dataset,
 * and the page must render "Insufficient source data." for them rather than
 * this function inventing a value. */
export function getControlTowerFleet(): ControlTowerAircraftRow[] {
  const events = upcomingMaintenanceEvents(50);
  return aircraft.map((a) => {
    const registration = currentRegistration(a);
    const variant = getAircraftVariant(a.aircraftVariantId);
    const wos = workOrdersForAircraft(a.id);
    const openWos = wos.filter((w) => w.status !== "COMPLETED" && w.status !== "CANCELLED");
    const defs = defectsForAircraft(a.id);
    const openDefs = defs.filter((d) => d.status === "OPEN");
    const seriousOpenDefect = openDefs.find((d) => d.severity === "HIGH" || d.severity === "CRITICAL");
    const woIds = new Set(wos.map((w) => w.id));
    const shortageParts = getPartsAtRisk().filter((p) => p.workOrderId && woIds.has(p.workOrderId));
    const nextEvent = events.find((e) => e.aircraftId === a.id);

    let operationalStatus: OperationalStatus;
    if (a.status === "STORED") operationalStatus = "STORED";
    else if (a.status === "WRITTEN_OFF") operationalStatus = "WRITTEN_OFF";
    else if (seriousOpenDefect) operationalStatus = "AOG";
    else if (openWos.length > 0) operationalStatus = "UNDER_MAINTENANCE";
    else operationalStatus = "OPERATIONAL";

    return {
      aircraftId: a.id,
      registration,
      model: variant?.modelDesignation ?? "Insufficient source data.",
      operationalStatus,
      aogReason: seriousOpenDefect ? seriousOpenDefect.description : null,
      openWorkOrders: openWos.length,
      openDefects: openDefs.length,
      criticalOpenDefects: openDefs.filter((d) => d.severity === "HIGH" || d.severity === "CRITICAL").length,
      nextMaintenanceDue: nextEvent?.date ?? null,
      materialShortageCount: shortageParts.length,
      risk: getAircraftOperationalRisk(a.id)!,
    };
  });
}

export interface ControlTowerSummary {
  totalAircraft: number;
  operational: number;
  underMaintenance: number;
  aog: number;
  openWorkOrders: number;
  criticalDiscrepancies: number;
  upcomingMaintenance: number;
  materialShortages: number;
}

export function getControlTowerSummary(): ControlTowerSummary {
  const fleet = getControlTowerFleet();
  const m = getMaintenanceAnalytics();
  return {
    totalAircraft: fleet.length,
    operational: fleet.filter((r) => r.operationalStatus === "OPERATIONAL").length,
    underMaintenance: fleet.filter((r) => r.operationalStatus === "UNDER_MAINTENANCE").length,
    aog: fleet.filter((r) => r.operationalStatus === "AOG").length,
    openWorkOrders: m.totalOpenWorkOrders,
    criticalDiscrepancies: defects.filter((d) => d.status === "OPEN" && (d.severity === "HIGH" || d.severity === "CRITICAL")).length,
    upcomingMaintenance: upcomingMaintenanceEvents(50).length,
    materialShortages: getPartsAtRisk().length,
  };
}

// --- M12.2 AI Discrepancy Intelligence additions ---
// "Discrepancy" in this platform's domain model is the existing Defect
// entity (see lib/mock/defects.ts) — there is no separate Discrepancy type,
// by design, to avoid a duplicate entity for the same concept. Grouping is
// done by ATA chapter, the only structural attribute defects already share
// that maps to "system" in the aviation sense the product spec asks for.

export interface DiscrepancyGroup {
  ataChapter: string;
  occurrences: number;
  aircraftIds: string[];
  aircraftCount: number;
  recurringAircraftCount: number;
  highSeverityCount: number;
  firstOccurrence: string;
  latestOccurrence: string;
  openCount: number;
  deferredCount: number;
  resolvedCount: number;
  defects: Defect[];
}

export function getDiscrepancyGroups(): DiscrepancyGroup[] {
  const byChapter = new Map<string, Defect[]>();
  for (const d of defects) byChapter.set(d.ataChapter, [...(byChapter.get(d.ataChapter) ?? []), d]);

  const groups: DiscrepancyGroup[] = Array.from(byChapter.entries()).map(([ataChapter, list]) => {
    const byAircraft = new Map<string, Defect[]>();
    for (const d of list) byAircraft.set(d.aircraftId, [...(byAircraft.get(d.aircraftId) ?? []), d]);
    const dates = list.map((d) => d.reportedDate).sort();
    return {
      ataChapter,
      occurrences: list.length,
      aircraftIds: Array.from(byAircraft.keys()),
      aircraftCount: byAircraft.size,
      recurringAircraftCount: Array.from(byAircraft.values()).filter((l) => l.length > 1).length,
      highSeverityCount: list.filter((d) => d.severity === "HIGH" || d.severity === "CRITICAL").length,
      firstOccurrence: dates[0],
      latestOccurrence: dates[dates.length - 1],
      openCount: list.filter((d) => d.status === "OPEN").length,
      deferredCount: list.filter((d) => d.status === "DEFERRED").length,
      resolvedCount: list.filter((d) => d.status === "RESOLVED").length,
      defects: list,
    };
  });

  return groups.sort((a, b) => b.occurrences - a.occurrences);
}

export function getDiscrepancyGroup(ataChapter: string): DiscrepancyGroup | null {
  return getDiscrepancyGroups().find((g) => g.ataChapter === ataChapter) ?? null;
}

// --- M12.4 Work Order Planning & Maintenance Scheduling Intelligence ---
// WorkOrder has no createdDate/labor-hours field and Technician has no
// skill field distinct from certifications, and no WorkOrder field records a
// required certification — so "age" below is derived from dueDate (the only
// date-based signal that exists), and technician recommendation is derived
// from workload/shift/prior-aircraft-experience plus a keyword overlap
// between a technician's certifications and the work order title (a real,
// checkable signal, not an invented skill-matching system). Never presented
// as certified skill verification.

export type PlanningStatus = "READY" | "MATERIAL_BLOCKED" | "TECHNICIAN_BLOCKED" | "BOTH_BLOCKED" | "IN_PROGRESS" | "WAITING_INSPECTION" | "COMPLETED" | "CANCELLED";

export interface ShortPart {
  partNumber: string;
  description: string;
  status: string;
  quantity: number;
}

export interface WorkOrderPlanningRow {
  workOrderId: string;
  workOrderNumber: string;
  title: string;
  aircraftId: string;
  aircraftRegistration: string;
  priority: Priority;
  status: WorkOrder["status"];
  planningStatus: PlanningStatus;
  shortParts: ShortPart[];
  assignedTechnicianId: string | null;
  assignedTechnicianName: string | null;
  dueDate: string;
  daysOverdue: number | null;
  aogAircraft: boolean;
  risk: RiskLevel;
  riskReasons: string[];
  recommendedAction: string;
}

function daysBetween(a: string, b: string): number {
  return Math.round((new Date(a).getTime() - new Date(b).getTime()) / 86400000);
}

function buildPlanningRow(w: WorkOrder): WorkOrderPlanningRow {
  const a = getAircraftById(w.aircraftId);
  const registration = a ? currentRegistration(a) : w.aircraftId;
  const reqParts = partsForWorkOrder(w.id);
  const shortParts: ShortPart[] = reqParts.filter((p) => p.status !== "IN_STOCK").map((p) => ({ partNumber: p.partNumber, description: p.description, status: p.status, quantity: p.quantity }));
  const materialBlocked = shortParts.length > 0;
  const technicianBlocked = w.assignedTechnicianId === null;
  const tech = w.assignedTechnicianId ? getTechnicianById(w.assignedTechnicianId) : undefined;
  const overdue = isOverdue(w);
  const daysOverdue = overdue ? daysBetween(MOCK_TODAY, w.dueDate) : null;
  const aircraftRisk = a ? getAircraftOperationalRisk(a.id) : null;
  const aogAircraft = aircraftRisk?.reasons.some((r) => r.includes("HIGH/CRITICAL-severity defect")) ?? false;

  // Planning status is derived from actual part/technician records, not the
  // WorkOrder.status label alone — the mock dataset has at least one work
  // order (WO-1050) whose status says WAITING_PARTS while its linked part
  // is actually IN_STOCK. Trusting the status label there would produce a
  // "blocked by: (nothing)" answer; trusting the part record instead keeps
  // every claim backed by a concrete record. The mismatch itself is
  // surfaced in dataInconsistencyNote rather than hidden.
  const statusSaysWaitingParts = w.status === "WAITING_PARTS";
  const dataInconsistencyNote = statusSaysWaitingParts && !materialBlocked
    ? `Work order status is WAITING_PARTS, but no part currently linked to this work order shows a shortage (source: lib/mock/parts.ts).`
    : null;

  let planningStatus: PlanningStatus;
  if (w.status === "COMPLETED") planningStatus = "COMPLETED";
  else if (w.status === "CANCELLED") planningStatus = "CANCELLED";
  else if (w.status === "IN_PROGRESS") planningStatus = "IN_PROGRESS";
  else if (w.status === "WAITING_INSPECTION") planningStatus = "WAITING_INSPECTION";
  else if (materialBlocked && technicianBlocked) planningStatus = "BOTH_BLOCKED";
  else if (materialBlocked) planningStatus = "MATERIAL_BLOCKED";
  else if (technicianBlocked) planningStatus = "TECHNICIAN_BLOCKED";
  else planningStatus = "READY";

  const riskReasons: string[] = [];
  if (aogAircraft) riskReasons.push("Aircraft is AOG (open HIGH/CRITICAL defect)");
  if (w.priority === "CRITICAL" || w.priority === "HIGH") riskReasons.push(`Work order priority is ${w.priority}`);
  if (overdue) riskReasons.push(`Overdue by ${daysOverdue} day(s)`);
  if (materialBlocked) riskReasons.push(`Required material unavailable: ${shortParts.map((p) => p.partNumber).join(", ")}`);
  if (dataInconsistencyNote) riskReasons.push(dataInconsistencyNote);
  const risk: RiskLevel = aogAircraft || (overdue && (w.priority === "CRITICAL" || w.priority === "HIGH")) ? "HIGH" : riskReasons.length > 0 ? "MEDIUM" : "LOW";

  let recommendedAction: string;
  if (planningStatus === "COMPLETED" || planningStatus === "CANCELLED") recommendedAction = "No action required.";
  else if (planningStatus === "BOTH_BLOCKED") recommendedAction = `Assign a technician and resolve material shortage (${shortParts.map((p) => p.partNumber).join(", ")}) before starting.`;
  else if (planningStatus === "MATERIAL_BLOCKED") recommendedAction = `Do not start — required part unavailable: ${shortParts.map((p) => p.partNumber).join(", ")}.`;
  else if (planningStatus === "TECHNICIAN_BLOCKED") recommendedAction = "Assign a technician before starting.";
  else if (planningStatus === "READY" && dataInconsistencyNote) recommendedAction = `Ready per part records, though work order status still reads WAITING_PARTS — ${dataInconsistencyNote}`;
  else if (planningStatus === "READY" && (aogAircraft || w.priority === "CRITICAL")) recommendedAction = `Start ${w.workOrderNumber} now — ${aogAircraft ? "aircraft is AOG" : "priority is CRITICAL"} and material is available.`;
  else if (planningStatus === "READY") recommendedAction = `Ready to start when scheduled — material and technician are in place.`;
  else if (planningStatus === "WAITING_INSPECTION") recommendedAction = "Awaiting inspector review — no further planning action.";
  else recommendedAction = "In progress — no further planning action.";

  return {
    workOrderId: w.id,
    workOrderNumber: w.workOrderNumber,
    title: w.title,
    aircraftId: w.aircraftId,
    aircraftRegistration: registration,
    priority: w.priority,
    status: w.status,
    planningStatus,
    shortParts,
    assignedTechnicianId: w.assignedTechnicianId,
    assignedTechnicianName: tech?.name ?? null,
    dueDate: w.dueDate,
    daysOverdue,
    aogAircraft,
    risk,
    riskReasons: riskReasons.length > 0 ? riskReasons : ["No AOG condition, overdue status, or material shortage found for this work order."],
    recommendedAction,
  };
}

export function getWorkOrderPlanning(): WorkOrderPlanningRow[] {
  return workOrders.filter((w) => w.status !== "COMPLETED" && w.status !== "CANCELLED").map(buildPlanningRow);
}

export function getWorkOrderPlanningRow(workOrderId: string): WorkOrderPlanningRow | null {
  const w = workOrders.find((x) => x.id === workOrderId);
  return w ? buildPlanningRow(w) : null;
}

export function getMaterialBlockedWorkOrders(): WorkOrderPlanningRow[] {
  return getWorkOrderPlanning().filter((r) => r.planningStatus === "MATERIAL_BLOCKED" || r.planningStatus === "BOTH_BLOCKED");
}

export function getReadyToStartWorkOrders(): WorkOrderPlanningRow[] {
  return getWorkOrderPlanning().filter((r) => r.planningStatus === "READY");
}

export interface WorkOrderPlanningSummary {
  openWorkOrders: number;
  criticalHigh: number;
  readyToStart: number;
  materialBlocked: number;
  technicianAssignmentRequired: number;
  overdue: number;
  aogRelated: number;
  plannedInProgress: number;
}

export function getWorkOrderPlanningSummary(): WorkOrderPlanningSummary {
  const rows = getWorkOrderPlanning();
  return {
    openWorkOrders: rows.length,
    criticalHigh: rows.filter((r) => r.priority === "CRITICAL" || r.priority === "HIGH").length,
    readyToStart: rows.filter((r) => r.planningStatus === "READY").length,
    materialBlocked: rows.filter((r) => r.planningStatus === "MATERIAL_BLOCKED" || r.planningStatus === "BOTH_BLOCKED").length,
    technicianAssignmentRequired: rows.filter((r) => r.planningStatus === "TECHNICIAN_BLOCKED" || r.planningStatus === "BOTH_BLOCKED").length,
    overdue: rows.filter((r) => r.daysOverdue !== null).length,
    aogRelated: rows.filter((r) => r.aogAircraft).length,
    plannedInProgress: rows.filter((r) => r.planningStatus === "IN_PROGRESS" || r.planningStatus === "WAITING_INSPECTION").length,
  };
}

export interface TechnicianRecommendation {
  technicianId: string;
  name: string;
  reasons: string[];
}

export interface TechnicianEligibility {
  technicianId: string;
  name: string;
  reasons: string[];
  eligible: boolean;
  certificationMatch: string;
  availability: string;
  workload: string;
}

const CERT_KEYWORDS_STOPLIST = new Set(["and", "the", "of", "for", "b1.1", "b2"]);

function certificationKeywordMatches(t: Technician, title: string): string[] {
  const titleLower = title.toLowerCase();
  return t.certifications.filter((c) => {
    const words = c.toLowerCase().split(/\s+/).filter((w) => w.length > 3 && !CERT_KEYWORDS_STOPLIST.has(w));
    return words.some((w) => titleLower.includes(w));
  });
}

interface RankedTechnicianCandidate {
  technicianId: string;
  name: string;
  reasons: string[];
  openWorkOrders: number;
  onShift: boolean;
  certMatches: number;
  priorAircraftCount: number;
}

/** The ONE ranking pass for technician-to-work-order suitability, shared by
 * getTechnicianAssignmentRecommendation (top pick only) and
 * getTechnicianEligibilityForWorkOrder (full ranked list) so the two can
 * never disagree. Uses only fields that actually exist: current open/
 * overdue workload, on-shift status, prior assignment history on this same
 * aircraft, and a keyword overlap between a technician's certifications and
 * the work order title. There is no field anywhere recording a work
 * order's *required* certification or a technician's location/working
 * hours beyond shiftStart/shiftEnd — those criteria are never fabricated. */
function rankTechniciansForWorkOrder(w: WorkOrder): RankedTechnicianCandidate[] {
  const workload = getTechnicianWorkload();
  const candidates = technicians.map((t) => {
    const wl = workload.find((x) => x.technicianId === t.id)!;
    const certMatches = certificationKeywordMatches(t, w.title);
    const priorAircraftWos = workOrdersForTechnician(t.id).filter((pw) => pw.aircraftId === w.aircraftId && pw.id !== w.id);
    const reasons: string[] = [];
    if (certMatches.length > 0) reasons.push(`Certification match: ${certMatches.join(", ")}`);
    if (wl.onShift) reasons.push("On shift now");
    if (wl.openWorkOrders === 0) reasons.push("No other open work orders");
    if (priorAircraftWos.length > 0) reasons.push(`Prior work order experience on this aircraft (${priorAircraftWos.length})`);
    return { technicianId: t.id, name: t.name, reasons, openWorkOrders: wl.openWorkOrders, onShift: wl.onShift, certMatches: certMatches.length, priorAircraftCount: priorAircraftWos.length };
  });
  return candidates.sort((a, b) => b.certMatches - a.certMatches || Number(b.onShift) - Number(a.onShift) || a.openWorkOrders - b.openWorkOrders);
}

/** Explainable technician recommendation — the top-ranked candidate only.
 * Returns null when no technician has any distinguishing signal at all,
 * rather than picking one arbitrarily and calling it a recommendation. */
export function getTechnicianAssignmentRecommendation(workOrderId: string): TechnicianRecommendation | null {
  const w = workOrders.find((x) => x.id === workOrderId);
  if (!w) return null;
  const top = rankTechniciansForWorkOrder(w)[0];
  if (!top || top.reasons.length === 0) return null;
  return { technicianId: top.technicianId, name: top.name, reasons: top.reasons };
}

/** Full ranked candidate list (not just the top pick) so a planner can see
 * every technician and why — or why not — they're eligible. "Eligible"
 * here means at least one real, source-backed reason exists; it is never a
 * numeric score. Certification match and availability are reported
 * per-candidate as explicit strings so the UI never has to guess what
 * "Insufficient source data." means for a specific technician. */
export function getTechnicianEligibilityForWorkOrder(workOrderId: string): TechnicianEligibility[] {
  const w = workOrders.find((x) => x.id === workOrderId);
  if (!w) return [];
  return rankTechniciansForWorkOrder(w).map((c) => ({
    technicianId: c.technicianId,
    name: c.name,
    reasons: c.reasons,
    eligible: c.reasons.length > 0,
    certificationMatch: c.certMatches > 0 ? `${c.certMatches} keyword match(es)` : "Insufficient source data.",
    availability: c.onShift ? "On shift now" : "Not on shift now",
    workload: `${c.openWorkOrders} open work order(s)`,
  }));
}

// M14.9 — technician authorization hard-block classification. A read-only
// wrapper over the SAME getTechnicianEligibilityForWorkOrder ranking (never
// a second ranking engine) — classifies each candidate as hard-blocked or
// not, with real reasons drawn from the same availability/certMatch/workload
// signals already computed there. Missing qualification data is NEVER
// treated as "qualified" — it hard-blocks, per the same UNKNOWN-is-not-PASS
// principle the safety gates use.
export interface TechnicianAuthorizationView extends TechnicianEligibility {
  hardBlocked: boolean;
  blockReasons: string[];
}

export function getTechnicianAuthorizationForWorkOrder(workOrderId: string): TechnicianAuthorizationView[] {
  return getTechnicianEligibilityForWorkOrder(workOrderId).map((e) => {
    const blockReasons: string[] = [];
    if (e.certificationMatch === "Insufficient source data.") blockReasons.push("No certification-keyword match on file for this work order.");
    if (e.availability !== "On shift now") blockReasons.push("Not currently on shift.");
    const openCount = parseInt(e.workload, 10);
    if (!Number.isNaN(openCount) && openCount >= 3) blockReasons.push(`Workload already at ${openCount} open work order(s).`);
    return { ...e, hardBlocked: blockReasons.length >= 2, blockReasons };
  });
}

export function getWorkOrdersAwaitingAssignment(): WorkOrderPlanningRow[] {
  return getWorkOrderPlanning().filter((r) => r.planningStatus === "TECHNICIAN_BLOCKED" || r.planningStatus === "BOTH_BLOCKED");
}

/** Deterministic, source-backed "what should maintenance do next" list —
 * shared by the Planning UI and Lisa so they can never disagree. */
export function getNextMaintenanceActions(): string[] {
  const rows = getWorkOrderPlanning();
  const actions: string[] = [];
  for (const r of rows.filter((x) => x.planningStatus === "READY" && (x.aogAircraft || x.priority === "CRITICAL"))) {
    actions.push(`Start ${r.workOrderNumber} because: ${r.riskReasons.join("; ")}.`);
  }
  for (const r of rows.filter((x) => x.planningStatus === "MATERIAL_BLOCKED" || x.planningStatus === "BOTH_BLOCKED")) {
    actions.push(`Do not start ${r.workOrderNumber} — required part(s) unavailable: ${r.shortParts.map((p) => p.partNumber).join(", ")}. Procurement action required.`);
  }
  for (const r of rows.filter((x) => x.planningStatus === "TECHNICIAN_BLOCKED")) {
    actions.push(`Assign a technician before starting ${r.workOrderNumber}.`);
  }
  return actions.length > 0 ? actions : ["No urgent planning action indicated by current data."];
}

// --- M12.3 Material Readiness & Procurement Planning ---
// Reuses part status (lib/mock/parts.ts), vendor availability/scoring
// (lib/mock/procurement.ts — the SAME scoreVendorOptionsForPart used by the
// procurement/parts comparison page, so a recommendation shown here can
// never disagree with the one on that page), and existing PartRequest/
// ProcurementCartItem/PurchaseOrder records. No inventory quantity is
// invented: a part with zero vendor lines and no IN_STOCK record is UNKNOWN,
// never silently treated as a shortage.

export type MaterialReadinessStatus = "READY" | "PARTIAL" | "SHORTAGE" | "UNKNOWN";

export interface MaterialVendorOption {
  vendorId: string;
  vendorName: string;
  availabilityStatus: string;
  unitPrice: number | null;
  currency: string | null;
  leadTimeDays: number | null;
}

export interface MaterialProcurementRecommendation {
  vendorName: string;
  reasons: string[];
}

export interface MaterialReadinessRow {
  workOrderId: string;
  workOrderNumber: string;
  priority: Priority;
  aircraftId: string;
  aircraftRegistration: string;
  partId: string | null;
  partNumber: string;
  description: string;
  materialStatus: MaterialReadinessStatus;
  bestVendor: MaterialVendorOption | null;
  hasVendorAvailability: boolean;
  procurementStatus: string;
  recommendation: MaterialProcurementRecommendation | null;
}

function deriveMaterialStatus(partInStock: boolean, scores: ReturnType<typeof scoreVendorOptionsForPart>): MaterialReadinessStatus {
  if (partInStock) return "READY";
  const known = scores.filter((s) => s.line.availabilityStatus !== "UNKNOWN");
  if (known.some((s) => s.line.availabilityStatus === "IN_STOCK")) return "READY";
  if (known.some((s) => s.line.availabilityStatus === "LIMITED" || s.line.availabilityStatus === "ON_ORDER")) return "PARTIAL";
  if (known.length > 0) return "SHORTAGE";
  return "UNKNOWN";
}

/** Existing PartRequest/cart/PurchaseOrder records for this part+work order —
 * never a new procurement state, just reading what already exists. */
function procurementStatusFor(workOrderId: string, partNumber: string): string {
  const inCart = cartItems.some((c) => c.workOrderId === workOrderId && c.partNumber === partNumber);
  if (inCart) return "In Cart (not yet submitted)";

  const request = partRequests.find((r) => r.workOrderId === workOrderId && r.partNumber === partNumber);
  if (request) {
    const po = purchaseOrders.find((p) => p.requestIds.includes(request.id));
    if (po) return `Purchase Order ${po.poNumber} — ${po.status.replace(/_/g, " ")}`;
    return `Request ${request.id} — ${request.status.replace(/_/g, " ")}`;
  }
  return "Not yet requested";
}

function buildMaterialRow(w: WorkOrder, partId: string): MaterialReadinessRow | null {
  const part = getPartById(partId);
  if (!part) return null;
  const a = getAircraftById(w.aircraftId);
  const scores = scoreVendorOptionsForPart(partId);
  const materialStatus = deriveMaterialStatus(part.status === "IN_STOCK", scores);

  const scored = scores.filter((s) => s.score !== null).sort((x, y) => (y.score ?? 0) - (x.score ?? 0));
  const best = scored[0];
  const bestVendor: MaterialVendorOption | null = best
    ? { vendorId: best.vendorId, vendorName: best.vendorName, availabilityStatus: best.line.availabilityStatus, unitPrice: best.line.unitPrice, currency: best.line.currency, leadTimeDays: best.line.leadTimeDays }
    : null;

  let recommendation: MaterialProcurementRecommendation | null = null;
  if (materialStatus !== "READY" && best) {
    const cheapest = scores.filter((s) => s.line.unitPrice !== null).sort((x, y) => (x.line.unitPrice ?? 0) - (y.line.unitPrice ?? 0))[0];
    const reasons: string[] = [];
    if (best.line.availabilityStatus === "IN_STOCK" || best.line.availabilityStatus === "LIMITED") reasons.push(`Part availability known (${best.line.availabilityStatus.replace(/_/g, " ")})`);
    if (best.line.unitPrice !== null) reasons.push("Price known");
    const vendor = getVendorById(best.vendorId);
    if (vendor && vendor.approvalStatus === "APPROVED") reasons.push("Vendor relationship verified");
    if (cheapest?.vendorId === best.vendorId) reasons.push("Lowest known cost among available options");
    if (reasons.length > 0) recommendation = { vendorName: best.vendorName, reasons };
  }

  return {
    workOrderId: w.id,
    workOrderNumber: w.workOrderNumber,
    priority: w.priority,
    aircraftId: w.aircraftId,
    aircraftRegistration: a ? currentRegistration(a) : w.aircraftId,
    partId: part.id,
    partNumber: part.partNumber,
    description: part.description,
    materialStatus,
    bestVendor,
    hasVendorAvailability: scores.length > 0,
    procurementStatus: procurementStatusFor(w.id, part.partNumber),
    recommendation,
  };
}

/** One row per (open work order, required part) — the full material
 * readiness table, not just shortages. */
export function getMaterialReadinessRows(): MaterialReadinessRow[] {
  const rows: MaterialReadinessRow[] = [];
  for (const w of workOrders.filter((x) => x.status !== "COMPLETED" && x.status !== "CANCELLED")) {
    for (const partId of w.requiredPartIds) {
      const row = buildMaterialRow(w, partId);
      if (row) rows.push(row);
    }
  }
  return rows;
}

export function getWorkOrderMaterialReadiness(workOrderId: string): MaterialReadinessRow[] {
  return getMaterialReadinessRows().filter((r) => r.workOrderId === workOrderId);
}

export function getAircraftMaterialReadiness(aircraftId: string): MaterialReadinessRow[] {
  return getMaterialReadinessRows().filter((r) => r.aircraftId === aircraftId);
}

export function getMaterialShortages(): MaterialReadinessRow[] {
  return getMaterialReadinessRows().filter((r) => r.materialStatus === "SHORTAGE" || r.materialStatus === "PARTIAL" || r.materialStatus === "UNKNOWN");
}

export function getPartsBlockingWorkOrders(): MaterialReadinessRow[] {
  return getMaterialReadinessRows().filter((r) => r.materialStatus === "SHORTAGE");
}

export function getProcurementActionsForShortages(): MaterialReadinessRow[] {
  return getMaterialReadinessRows().filter((r) => r.materialStatus !== "READY" && r.recommendation !== null);
}

export interface MaterialReadinessSummary {
  workOrdersRequiringMaterial: number;
  materialReady: number;
  partialReadiness: number;
  materialShortages: number;
  procurementRequests: number;
  partsWithVendorAvailability: number;
  partsWithUnknownAvailability: number;
}

export function getMaterialReadinessSummary(): MaterialReadinessSummary {
  const rows = getMaterialReadinessRows();
  const workOrderIds = new Set(rows.map((r) => r.workOrderId));
  const distinctParts = new Map<string, MaterialReadinessRow>();
  for (const r of rows) if (!distinctParts.has(r.partNumber)) distinctParts.set(r.partNumber, r);

  return {
    workOrdersRequiringMaterial: workOrderIds.size,
    materialReady: rows.filter((r) => r.materialStatus === "READY").length,
    partialReadiness: rows.filter((r) => r.materialStatus === "PARTIAL").length,
    materialShortages: rows.filter((r) => r.materialStatus === "SHORTAGE").length,
    procurementRequests: partRequests.filter((r) => rows.some((row) => row.workOrderId === r.workOrderId && row.partNumber === r.partNumber)).length,
    partsWithVendorAvailability: Array.from(distinctParts.values()).filter((r) => r.hasVendorAvailability).length,
    partsWithUnknownAvailability: Array.from(distinctParts.values()).filter((r) => !r.hasVendorAvailability && r.materialStatus !== "READY").length,
  };
}

/** Lisa's narrative for one discrepancy group. Only claims a recurrence
 * pattern when the data actually shows it (recurring on >1 aircraft, or the
 * same chapter opened repeatedly) — otherwise says so plainly instead of
 * inventing a cause. */
export function getDiscrepancyGroupAnalysis(ataChapter: string): string[] {
  const g = getDiscrepancyGroup(ataChapter);
  if (!g) return ["Insufficient source data — no defects recorded against this ATA chapter."];
  if (g.occurrences < 2 || (g.recurringAircraftCount === 0 && g.aircraftCount < 2)) {
    return ["Insufficient source data to determine the recurrence cause."];
  }
  const parts: string[] = [];
  parts.push(
    `${g.occurrences} ATA ${g.ataChapter} discrepanc${g.occurrences === 1 ? "y has" : "ies have"} appeared on ${g.aircraftCount} aircraft` +
      (g.recurringAircraftCount > 0 ? `, including ${g.recurringAircraftCount} aircraft with more than one occurrence.` : ".")
  );
  if (g.resolvedCount > 0 || g.deferredCount > 0) {
    parts.push(
      `${g.resolvedCount} occurrence(s) were resolved by corrective action, ${g.deferredCount} deferred, and ${g.openCount} remain open.`
    );
  } else {
    parts.push(`All ${g.openCount} occurrence(s) are currently open.`);
  }
  if (g.recurringAircraftCount > 0) {
    parts.push("The recurrence pattern suggests this should be reviewed as a repeated component/system issue rather than treated as isolated events.");
  }
  return parts;
}

// --- M12.5 Maintenance Control Center ---
// A single aggregation over the FOUR existing analytics surfaces (Control
// Tower fleet/aircraft risk, Work Order Planning, Material Readiness,
// Discrepancy Intelligence). This function computes nothing new — every
// number and reason here is read from the functions those pages already
// call, so the Control Center, those pages, and Lisa can never disagree.

export type ControlCenterPriority = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "UNKNOWN";

export interface ControlCenterItem {
  priority: ControlCenterPriority;
  aircraftId: string | null;
  aircraftRegistration: string | null;
  category: "WORK_ORDER" | "DISCREPANCY" | "MATERIAL";
  label: string;
  issue: string;
  reasons: string[];
  status: string;
  recommendedAction: string;
  href: string;
  source: string;
}

const PRIORITY_RANK: Record<ControlCenterPriority, number> = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3, UNKNOWN: 4 };

function workOrderControlCenterPriority(r: WorkOrderPlanningRow): ControlCenterPriority {
  if (r.aogAircraft && r.priority === "CRITICAL") return "CRITICAL";
  if (r.risk === "HIGH") return r.aogAircraft || r.priority === "CRITICAL" ? "CRITICAL" : "HIGH";
  if (r.risk === "MEDIUM") return "MEDIUM";
  if (r.risk === "LOW") return "LOW";
  return "UNKNOWN";
}

function materialControlCenterPriority(r: MaterialReadinessRow): ControlCenterPriority {
  if (r.materialStatus === "READY") return "LOW";
  if (r.materialStatus === "UNKNOWN") return "UNKNOWN";
  if (r.priority === "CRITICAL") return "CRITICAL";
  if (r.priority === "HIGH" || r.materialStatus === "SHORTAGE") return "HIGH";
  return "MEDIUM";
}

function discrepancyControlCenterPriority(g: DiscrepancyGroup): ControlCenterPriority {
  if (g.highSeverityCount > 0 && g.recurringAircraftCount > 0) return "CRITICAL";
  if (g.highSeverityCount > 0) return "HIGH";
  if (g.openCount > 0) return "MEDIUM";
  return "LOW";
}

/** The prioritized "what needs attention now" queue — one item per open
 * work order, active material issue, and discrepancy group that isn't
 * fully clean, ranked CRITICAL first. Every reason traces to a real record;
 * nothing here is a numeric black-box score. */
export function getMaintenanceControlCenter(): ControlCenterItem[] {
  const items: ControlCenterItem[] = [];

  for (const r of getWorkOrderPlanning()) {
    if (r.planningStatus === "COMPLETED" || r.planningStatus === "CANCELLED") continue;
    if (r.risk === "LOW" && r.planningStatus === "READY") continue;
    items.push({
      priority: workOrderControlCenterPriority(r),
      aircraftId: r.aircraftId,
      aircraftRegistration: r.aircraftRegistration,
      category: "WORK_ORDER",
      label: r.workOrderNumber,
      issue: r.title,
      reasons: r.riskReasons,
      status: r.planningStatus.replace(/_/g, " "),
      recommendedAction: r.recommendedAction,
      href: `/maintenance/planning/${r.workOrderId}`,
      source: r.workOrderNumber,
    });
  }

  for (const r of getMaterialShortages()) {
    items.push({
      priority: materialControlCenterPriority(r),
      aircraftId: r.aircraftId,
      aircraftRegistration: r.aircraftRegistration,
      category: "MATERIAL",
      label: r.partNumber,
      issue: `Material ${r.materialStatus.toLowerCase()} for ${r.workOrderNumber}`,
      reasons: [
        r.materialStatus === "UNKNOWN" ? "No vendor availability record for this part." : `Best known vendor: ${r.bestVendor?.vendorName ?? "Insufficient source data."}`,
        `Procurement status: ${r.procurementStatus}`,
      ],
      status: r.materialStatus,
      recommendedAction: r.recommendation ? `Review procurement — recommended vendor ${r.recommendation.vendorName}` : "Review material readiness — insufficient data to recommend a vendor",
      href: "/maintenance/material-readiness",
      source: r.partNumber,
    });
  }

  for (const g of getDiscrepancyGroups()) {
    if (g.openCount === 0) continue;
    items.push({
      priority: discrepancyControlCenterPriority(g),
      aircraftId: null,
      aircraftRegistration: null,
      category: "DISCREPANCY",
      label: `ATA ${g.ataChapter}`,
      issue: `${g.occurrences} discrepancy occurrence(s), ${g.openCount} open`,
      reasons: [
        `${g.aircraftCount} aircraft affected, ${g.recurringAircraftCount} recurring`,
        `${g.highSeverityCount} high/critical severity occurrence(s)`,
      ],
      status: g.openCount > 0 ? "OPEN" : "RESOLVED",
      recommendedAction: g.recurringAircraftCount > 0 ? "Investigate recurring pattern" : "Review open occurrences",
      href: "/maintenance/discrepancies",
      source: `ATA ${g.ataChapter}`,
    });
  }

  return items.sort((a, b) => PRIORITY_RANK[a.priority] - PRIORITY_RANK[b.priority]);
}

export interface MaintenanceControlCenterSummary {
  aircraftRequiringAttention: number;
  aogAircraft: number;
  criticalWorkOrders: number;
  criticalDiscrepancies: number;
  materialShortages: number;
  workOrdersWaitingForParts: number;
  overdueAtRiskMaintenance: number;
  highRiskAircraft: number;
}

export function getMaintenanceControlCenterSummary(): MaintenanceControlCenterSummary {
  const fleet = getControlTowerFleet();
  const towerSummary = getControlTowerSummary();
  const planningSummary = getWorkOrderPlanningSummary();
  const materialRows = getMaterialReadinessRows();

  return {
    aircraftRequiringAttention: fleet.filter((f) => f.risk.risk !== "LOW").length,
    aogAircraft: towerSummary.aog,
    criticalWorkOrders: getWorkOrderPlanning().filter((r) => r.priority === "CRITICAL").length,
    criticalDiscrepancies: towerSummary.criticalDiscrepancies,
    materialShortages: materialRows.filter((r) => r.materialStatus !== "READY").length,
    workOrdersWaitingForParts: getMaterialBlockedWorkOrders().length,
    overdueAtRiskMaintenance: planningSummary.overdue,
    highRiskAircraft: fleet.filter((f) => f.risk.risk === "HIGH").length,
  };
}

// --- M12.6 Maintenance Execution & Action Center ---
// Turns the existing WorkOrderPlanningRow.planningStatus into a concrete,
// supported next action. Every action type maps to a real mutation already
// present in lib/mock/workOrders.ts (assignTechnician/startWorkOrder) or
// added in this milestone (unassignTechnician/completeWorkOrder/
// escalateWorkOrder) — never a fake workflow transition.

export type ExecutionActionType = "ASSIGN_TECHNICIAN" | "RESOLVE_MATERIAL_BLOCKER" | "START_WORK" | "ESCALATE" | "REVIEW" | "COMPLETE";

export interface ExecutionQueueItem extends WorkOrderPlanningRow {
  actionType: ExecutionActionType;
  actionLabel: string;
}

function deriveExecutionAction(r: WorkOrderPlanningRow): { actionType: ExecutionActionType; actionLabel: string } {
  if (r.planningStatus === "BOTH_BLOCKED" || r.planningStatus === "TECHNICIAN_BLOCKED") return { actionType: "ASSIGN_TECHNICIAN", actionLabel: "Assign technician" };
  if (r.planningStatus === "MATERIAL_BLOCKED") return { actionType: "RESOLVE_MATERIAL_BLOCKER", actionLabel: "Resolve material blocker" };
  if (r.planningStatus === "READY") return { actionType: "START_WORK", actionLabel: "Start work" };
  if (r.planningStatus === "IN_PROGRESS" && (r.risk === "HIGH" || r.aogAircraft)) return { actionType: "ESCALATE", actionLabel: "Escalate" };
  if (r.planningStatus === "IN_PROGRESS") return { actionType: "COMPLETE", actionLabel: "Complete" };
  return { actionType: "REVIEW", actionLabel: "Review" };
}

/** The actionable execution queue — one row per open work order, each
 * carrying a real supported action. Shared by the Control Center UI and
 * Lisa so "what can maintenance complete today" always matches. */
export function getExecutionQueue(): ExecutionQueueItem[] {
  return getWorkOrderPlanning().map((r) => ({ ...r, ...deriveExecutionAction(r) }));
}

// --- M12.9 ASAL Foundation: Safety-Gated Execution ---
// The key architectural change of this milestone: WorkOrderStatus.COMPLETED
// (existing, unchanged) means the technician's step is done — it must never
// be read as "released" or "airworthy". ExecutionState is a second, derived
// lens over the SAME existing fields (status, inspectorReviewId, the
// InspectorReview it points to) — no new stored field, so it can never
// disagree with what Planning/Control Center already show for `status`.

/** Whether a work order's underlying maintenance step requires independent
 * inspection before it can be considered released — derived from the linked
 * MaintenanceTask when one exists, otherwise from the existing
 * InspectorReview/WAITING_INSPECTION signal already used elsewhere in this
 * file (getWorkOrderPlanningRow). Never fabricated. */
export function isInspectionRequired(w: WorkOrder): boolean {
  const task = w.maintenanceTaskId ? getMaintenanceTaskById(w.maintenanceTaskId) : undefined;
  if (task) return task.inspectionRequired;
  return w.inspectorReviewId !== null || w.status === "WAITING_INSPECTION";
}

export function getExecutionState(w: WorkOrder): ExecutionState {
  if (w.status === "DRAFT" || w.status === "ASSIGNED") {
    const row = getWorkOrderPlanningRow(w.id);
    return row && row.shortParts.length > 0 ? "BLOCKED" : "NOT_STARTED";
  }
  if (w.status === "IN_PROGRESS") return "IN_PROGRESS";
  if (w.status === "WAITING_PARTS") return "BLOCKED";
  if (w.status === "WAITING_INSPECTION") return "INSPECTION_REQUIRED";
  if (w.status === "CANCELLED") return "NOT_STARTED";
  // status === "COMPLETED" from here — the technician's step is done. This
  // is exactly where the milestone's required distinction is made explicit.
  if (!isInspectionRequired(w)) return "RELEASED";
  const review = getInspectorReviewForWorkOrder(w.id);
  if (!review) return "TECHNICIAN_COMPLETED";
  if (review.status === "APPROVED") return "RELEASED";
  if (review.status === "PENDING_INSPECTION") return "TECHNICIAN_COMPLETED";
  // REJECTED / RETURNED_FOR_CORRECTION — inspection happened but did not
  // clear the work order for release.
  return "INSPECTION_COMPLETED";
}

/** Lightweight, derived safety gates — reuses the same material/technician
 * blocking signal as getWorkOrderPlanningRow (never a second calculation),
 * plus the new inspection/evidence/release distinctions above. Not a rules
 * engine: each gate is a direct read of one existing fact. */
/** Independent inspectors eligible for this work order — the ONE place RII
 * (Required Inspection Item) exclusion is enforced: whoever performed the
 * work (assignedTechnicianId) can never appear as an eligible inspector for
 * their own work order, no matter how well-qualified. Reuses the existing
 * isInspector flag and workload/shift signals already used by
 * rankTechniciansForWorkOrder — no second ranking system. */
export function getEligibleInspectorsForWorkOrder(workOrderId: string): TechnicianEligibility[] {
  const w = workOrders.find((x) => x.id === workOrderId);
  if (!w) return [];
  return getTechnicianEligibilityForWorkOrder(workOrderId).filter((e) => {
    const t = getTechnicianById(e.technicianId);
    return t?.isInspector === true && e.technicianId !== w.assignedTechnicianId;
  });
}

export function getSafetyGatesForWorkOrder(workOrderId: string): SafetyGate[] {
  const w = workOrders.find((x) => x.id === workOrderId);
  if (!w) return [];
  const planningRow = getWorkOrderPlanningRow(workOrderId);
  const task = w.maintenanceTaskId ? getMaintenanceTaskById(w.maintenanceTaskId) : undefined;
  const execState = getExecutionState(w);
  const gates: SafetyGate[] = [];

  const materialBlocked = planningRow?.planningStatus === "MATERIAL_BLOCKED" || planningRow?.planningStatus === "BOTH_BLOCKED";
  gates.push({
    type: "MATERIAL_GATE",
    open: materialBlocked,
    state: materialBlocked ? "FAIL" : "PASS",
    reason: planningRow && planningRow.shortParts.length > 0 ? `Required material unavailable: ${planningRow.shortParts.map((p) => p.partNumber).join(", ")}` : "No material shortage recorded for this work order.",
  });

  const qualificationOpen = w.assignedTechnicianId === null && w.status !== "COMPLETED" && w.status !== "CANCELLED";
  gates.push({
    type: "QUALIFICATION_GATE",
    open: qualificationOpen,
    state: qualificationOpen ? "FAIL" : "PASS",
    reason: w.assignedTechnicianId ? "A technician is assigned." : "No technician currently assigned.",
  });

  const inspectionRequired = isInspectionRequired(w);
  const inspectionOpen = inspectionRequired && execState !== "RELEASED" && execState !== "INSPECTION_COMPLETED";
  const eligibleInspectors = inspectionRequired ? getEligibleInspectorsForWorkOrder(workOrderId) : [];
  gates.push({
    type: "INSPECTION_GATE",
    open: inspectionOpen,
    state: !inspectionRequired ? "NOT_REQUIRED" : inspectionOpen ? (eligibleInspectors.length === 0 ? "UNKNOWN" : "FAIL") : "PASS",
    reason: !inspectionRequired
      ? "No inspection is indicated as required for this work order."
      : !inspectionOpen
      ? "Required inspection has been completed and approved."
      : eligibleInspectors.length > 0
      ? `Independent inspection required before release — eligible inspector(s): ${eligibleInspectors.map((e) => e.name).join(", ")}. The assigned technician cannot inspect their own work.`
      : "Independent inspection required before release — no eligible inspector (other than the assigned technician) currently identified.",
  });

  const evidenceUnknown = task ? task.evidenceStatus === "SOURCE_UNKNOWN" : true;
  gates.push({
    type: "EVIDENCE_GATE",
    open: evidenceUnknown,
    state: !task ? "UNKNOWN" : evidenceUnknown ? "UNKNOWN" : "PASS",
    reason: task
      ? task.evidenceStatus === "SOURCE_UNKNOWN"
        ? "Authoritative maintenance reference is not available in the current dataset for this task."
        : `Reference on file: ${task.referenceType}${task.referenceId ? ` (${requirementLabel(task.referenceId)})` : ""}.`
      : "No maintenance task reference is linked to this work order.",
  });

  gates.push({
    type: "RELEASE_GATE",
    open: execState !== "RELEASED",
    state: execState === "RELEASED" ? "PASS" : "FAIL",
    reason: execState === "RELEASED" ? "Released — technician completion and (where required) inspection are both on record." : `Not yet released — current execution state: ${execState.replace(/_/g, " ")}.`,
  });

  return gates;
}

/** Work orders whose technician step is done but release is not yet
 * cleared — the "release queue" the Control Center and Executive KPIs
 * reuse (never a second calculation of what "released" means). */
export function getReleaseQueue(): { workOrderId: string; workOrderNumber: string; aircraftRegistration: string; executionState: ExecutionState }[] {
  return workOrders
    .filter((w) => w.status === "COMPLETED" || w.status === "WAITING_INSPECTION")
    .map((w) => ({ w, state: getExecutionState(w) }))
    .filter(({ state }) => state !== "RELEASED")
    .map(({ w, state }) => {
      const a = getAircraftById(w.aircraftId);
      return { workOrderId: w.id, workOrderNumber: w.workOrderNumber, aircraftRegistration: a ? currentRegistration(a) : w.aircraftId, executionState: state };
    });
}

/** Derived signature-record view over the existing TechnicianSignOff /
 * InspectorReview fields — never a second stored record. A prototype
 * compliance-ready foundation only; NOT a claim of electronic-signature
 * regulatory compliance. */
export function getSignatureRecordsForWorkOrder(workOrderId: string): SignatureRecord[] {
  const w = workOrders.find((x) => x.id === workOrderId);
  if (!w) return [];
  const records: SignatureRecord[] = [];
  if (w.signOff) {
    records.push({
      id: `sig-signoff-${w.id}`,
      userId: w.signOff.technicianId,
      action: "TECHNICIAN_SIGN_OFF",
      recordType: "WorkOrder",
      recordId: w.id,
      timestamp: w.signOff.timestamp,
      authenticationMethod: "PROTOTYPE_SESSION",
      signatureIntent: "Technician confirms work performed as recorded.",
      reasonCode: null,
    });
  }
  const review = getInspectorReviewForWorkOrder(w.id);
  if (review && review.reviewedAt) {
    records.push({
      id: `sig-review-${review.id}`,
      userId: review.inspectorId,
      action: "INSPECTOR_REVIEW",
      recordType: "WorkOrder",
      recordId: w.id,
      timestamp: review.reviewedAt,
      authenticationMethod: "PROTOTYPE_SESSION",
      signatureIntent: `Inspector ${review.status.toLowerCase().replace(/_/g, " ")}.`,
      reasonCode: review.comments || null,
    });
  }
  return records;
}

export interface MaintenanceTaskChainStep {
  label: string;
  detail: string;
  href?: string;
}

/** Aircraft → Discrepancy → Maintenance Task → Work Order chain for display,
 * reading only fields/records that already exist (Defect.workOrderId is the
 * existing reverse link used to find a discrepancy for a work order — no new
 * stored field). Steps with no source-backed value say so explicitly. */
/** Parts currently held out of service pending disposition — reuses the
 * same Part.serviceability field the material readiness/part pages already
 * read, no second quarantine list. */
export function getQuarantinedParts(): { partId: string; partNumber: string; description: string; reason: string }[] {
  return parts.filter((p) => p.serviceability === "QUARANTINED").map((p) => ({ partId: p.id, partNumber: p.partNumber, description: p.description, reason: p.quarantineReason ?? "Insufficient source data." }));
}

/** Deferred items (MEL foundation) for a named aircraft — reads
 * lib/mock/deferredItems.ts directly rather than a second calculation. */
export function getDeferredItemsForAircraft(aircraftId: string) {
  return deferredItems.filter((d) => d.aircraftId === aircraftId);
}

export function getOpenDeferredItems() {
  return deferredItems.filter((d) => d.status === "OPEN");
}

/** Cannibalization candidates targeting a named aircraft — reads
 * lib/mock/cannibalization.ts directly; never auto-authorizes anything. */
export function getCannibalizationCandidatesForAircraft(aircraftId: string) {
  return cannibalizationRequests.filter((c) => c.targetAircraftId === aircraftId);
}

// --- M14.1 AOG Recovery Intelligence ---
// Purely derived: every field below reads an existing analytics function or
// mock record (Control Tower AOG determination, Work Order Planning,
// Safety Gates, Material Readiness, Deferred Items, Cannibalization) — no
// new AOG algorithm, no new state, no persisted recovery record.

export type AogBlockerType = "MATERIAL" | "TECHNICIAN" | "SAFETY" | "INSPECTION" | "PROCUREMENT" | "REGULATORY" | "DEFERRED" | "EXECUTION" | "EVIDENCE" | "UNKNOWN";

export interface AogBlocker {
  type: AogBlockerType;
  description: string;
  source: string; // e.g. "WO-1054", "Part APU-410", "Safety Gate: MATERIAL"
}

export interface AogRecoveryOption {
  action: string;
  responsibleRole: string;
  requiresHumanApproval: true; // always — this system never auto-executes a recovery action
  href?: string;
}

export interface AogRecoveryAnalysis {
  aircraftId: string;
  registration: string;
  isAog: boolean;
  aogReason: string | null;
  criticalWorkOrders: { workOrderId: string; workOrderNumber: string; title: string }[];
  primaryBlocker: AogBlocker | null;
  secondaryBlockers: AogBlocker[];
  recoveryOptions: AogRecoveryOption[];
  dataCompleteness: "COMPLETE" | "PARTIAL" | "INSUFFICIENT";
}

/** The one AOG recovery analysis function — reused by the Control Center
 * link-out, the recovery detail page, and Lisa, so all three can never
 * disagree. AOG status itself is read straight from getControlTowerFleet()
 * (the existing, only AOG determination in the codebase). */
export function getAogRecoveryAnalysis(aircraftId: string): AogRecoveryAnalysis | null {
  const fleetRow = getControlTowerFleet().find((r) => r.aircraftId === aircraftId);
  if (!fleetRow) return null;
  const wos = workOrdersForAircraft(aircraftId).filter((w) => w.status !== "COMPLETED" && w.status !== "CANCELLED");
  const criticalWos = wos.filter((w) => w.priority === "CRITICAL" || w.priority === "HIGH");
  const deferred = deferredItems.filter((d) => d.aircraftId === aircraftId && d.status === "OPEN");
  const cannibalization = cannibalizationRequests.filter((c) => c.targetAircraftId === aircraftId);

  const blockers: AogBlocker[] = [];
  for (const w of criticalWos.length > 0 ? criticalWos : wos) {
    const gates = getSafetyGatesForWorkOrder(w.id);
    for (const g of gates) {
      if (g.state === "FAIL" || g.state === "UNKNOWN") {
        const type: AogBlockerType =
          g.type === "MATERIAL_GATE" ? "MATERIAL" :
          g.type === "QUALIFICATION_GATE" ? "TECHNICIAN" :
          g.type === "INSPECTION_GATE" ? "INSPECTION" :
          g.type === "EVIDENCE_GATE" ? "EVIDENCE" : "SAFETY";
        blockers.push({ type: g.state === "UNKNOWN" ? "UNKNOWN" : type, description: g.reason, source: `${w.workOrderNumber} — Safety Gate: ${g.type.replace(/_/g, " ")}` });
      }
    }
  }
  for (const d of deferred) {
    blockers.push({ type: "DEFERRED", description: d.dueAt === null ? "Deferred item with no authoritative MEL reference/due date on file." : `Deferred item due ${d.dueAt}.`, source: `Deferred Item ${d.id}` });
  }
  // M14.10 — regulatory compliance tracking: reuses the existing
  // ApplicabilityAssessment system (M0), never a second compliance engine.
  for (const asmt of assessmentsForAircraft(aircraftId).filter((a) => a.finalStatus === "NON_COMPLIANT" || a.finalStatus === "REVIEW_REQUIRED")) {
    blockers.push({ type: "REGULATORY", description: `Assessment ${asmt.id} is ${asmt.finalStatus.replace(/_/g, " ")}.`, source: `Assessment ${asmt.id}` });
  }

  const primaryBlocker = blockers[0] ?? null;
  const secondaryBlockers = blockers.slice(1);

  const recoveryOptions: AogRecoveryOption[] = [];
  if (blockers.some((b) => b.type === "MATERIAL")) {
    recoveryOptions.push({ action: "Investigate approved vendor sourcing", responsibleRole: "Procurement", requiresHumanApproval: true, href: "/maintenance/material-readiness" });
    if (cannibalization.length > 0) recoveryOptions.push({ action: "Review cannibalization candidate", responsibleRole: "Maintenance Manager", requiresHumanApproval: true, href: `/aircraft/${aircraftId}` });
  }
  if (blockers.some((b) => b.type === "TECHNICIAN")) {
    recoveryOptions.push({ action: "Assign a qualified technician", responsibleRole: "Maintenance Manager", requiresHumanApproval: true, href: wos[0] ? `/maintenance/planning/${wos[0].id}` : undefined });
  }
  if (blockers.some((b) => b.type === "INSPECTION")) {
    recoveryOptions.push({ action: "Assign an independent inspector", responsibleRole: "Maintenance Manager", requiresHumanApproval: true, href: wos[0] ? `/maintenance/planning/${wos[0].id}` : undefined });
  }
  if (blockers.some((b) => b.type === "EVIDENCE" || b.type === "UNKNOWN")) {
    recoveryOptions.push({ action: "Resolve missing evidence/reference before proceeding", responsibleRole: "Maintenance Manager", requiresHumanApproval: true });
  }
  if (blockers.some((b) => b.type === "DEFERRED")) {
    recoveryOptions.push({ action: "Review deferred item / MEL restriction", responsibleRole: "Maintenance Manager", requiresHumanApproval: true });
  }
  if (blockers.some((b) => b.type === "REGULATORY")) {
    recoveryOptions.push({ action: "Resolve non-compliant/review-required assessment", responsibleRole: "Compliance", requiresHumanApproval: true, href: "/compliance" });
  }
  recoveryOptions.push({ action: "Escalate blocker to maintenance manager", responsibleRole: "Maintenance Manager", requiresHumanApproval: true, href: wos[0] ? `/maintenance/planning/${wos[0].id}` : undefined });

  const dataCompleteness: AogRecoveryAnalysis["dataCompleteness"] =
    blockers.some((b) => b.type === "UNKNOWN") ? "PARTIAL" : blockers.length === 0 && fleetRow.operationalStatus === "AOG" ? "INSUFFICIENT" : "COMPLETE";

  return {
    aircraftId,
    registration: fleetRow.registration,
    isAog: fleetRow.operationalStatus === "AOG",
    aogReason: fleetRow.aogReason,
    criticalWorkOrders: criticalWos.map((w) => ({ workOrderId: w.id, workOrderNumber: w.workOrderNumber, title: w.title })),
    primaryBlocker,
    secondaryBlockers,
    recoveryOptions,
    dataCompleteness,
  };
}

// --- M14.2 Automation Queue ---
// A human-approval action queue, not an autonomous engine: every item is
// recomputed from existing analytics/records on each call (getMaterialShortages,
// getWorkOrdersAwaitingAssignment, getSafetyGatesForWorkOrder,
// getQuarantinedParts, deferredItems, cannibalizationRequests, Control Tower
// AOG rows), never a second calculation. Nothing here mutates data.

export function getAutomationQueue(): AutomationQueueItem[] {
  const items: AutomationQueueItem[] = [];

  for (const r of getMaterialShortages()) {
    items.push({
      id: `auto-material-${r.workOrderId}-${r.partId ?? r.partNumber}`,
      category: "MATERIAL_BLOCKER",
      title: `${r.partNumber} — material ${r.materialStatus}`,
      detection: `${r.workOrderNumber} (${r.aircraftRegistration}) requires ${r.partNumber}, currently ${r.materialStatus}.`,
      source: r.workOrderNumber,
      impact: r.priority === "CRITICAL" || r.priority === "HIGH" ? "Blocks a critical/high-priority work order." : "Blocks a work order.",
      recommendedAction: r.recommendation ? `Consider ${r.recommendation.vendorName} — ${r.recommendation.reasons[0]}` : "Investigate sourcing — insufficient source data for a specific vendor recommendation.",
      responsibleRole: "Procurement",
      approvalRequired: true,
      destinationHref: "/maintenance/material-readiness",
    });
  }

  for (const r of getWorkOrdersAwaitingAssignment()) {
    items.push({
      id: `auto-tech-${r.workOrderId}`,
      category: "TECHNICIAN_RECOMMENDATION",
      title: `${r.workOrderNumber} — needs technician assignment`,
      detection: `${r.workOrderNumber} (${r.aircraftRegistration}) has no technician assigned.`,
      source: r.workOrderNumber,
      impact: r.priority === "CRITICAL" || r.priority === "HIGH" ? "Critical/high-priority work cannot start." : "Work cannot start.",
      recommendedAction: "Review the ranked eligible-technician list on the Planning detail page.",
      responsibleRole: "Maintenance Manager",
      approvalRequired: true,
      destinationHref: `/maintenance/planning/${r.workOrderId}`,
    });
  }

  for (const row of getControlTowerFleet().filter((f) => f.operationalStatus === "AOG")) {
    items.push({
      id: `auto-aog-${row.aircraftId}`,
      category: "AOG_ESCALATION",
      title: `${row.registration} — AOG`,
      detection: row.aogReason ?? "Insufficient source data.",
      source: row.registration,
      impact: "Aircraft unavailable for service.",
      recommendedAction: "Open AOG Recovery to review blockers and options.",
      responsibleRole: "Maintenance Manager",
      approvalRequired: true,
      destinationHref: `/maintenance/aog-recovery/${row.aircraftId}`,
    });
  }

  for (const w of workOrders.filter((x) => x.status !== "COMPLETED" && x.status !== "CANCELLED")) {
    const gates = getSafetyGatesForWorkOrder(w.id);
    const inspGate = gates.find((g) => g.type === "INSPECTION_GATE");
    if (inspGate && inspGate.state === "UNKNOWN") {
      items.push({
        id: `auto-rii-${w.id}`,
        category: "RII_INSPECTOR_RECOMMENDATION",
        title: `${w.workOrderNumber} — no eligible independent inspector`,
        detection: inspGate.reason,
        source: w.workOrderNumber,
        impact: "Cannot clear the inspection safety gate.",
        recommendedAction: "Identify or qualify an independent inspector other than the assigned technician.",
        responsibleRole: "Maintenance Manager",
        approvalRequired: true,
        destinationHref: `/maintenance/planning/${w.id}`,
      });
    }
    const evGate = gates.find((g) => g.type === "EVIDENCE_GATE");
    if (evGate && evGate.state === "UNKNOWN") {
      items.push({
        id: `auto-evidence-${w.id}`,
        category: "MISSING_EVIDENCE",
        title: `${w.workOrderNumber} — missing maintenance reference`,
        detection: evGate.reason,
        source: w.workOrderNumber,
        impact: "Evidence gate cannot be cleared without a reference on file.",
        recommendedAction: "Attach or confirm the authoritative maintenance reference for this task.",
        responsibleRole: "Maintenance Manager",
        approvalRequired: true,
        destinationHref: `/maintenance/planning/${w.id}`,
      });
    }
    const failedGates = gates.filter((g) => g.state === "FAIL" && g.type !== "MATERIAL_GATE" && g.type !== "QUALIFICATION_GATE" && g.type !== "INSPECTION_GATE");
    for (const g of failedGates) {
      items.push({
        id: `auto-gate-${w.id}-${g.type}`,
        category: "SAFETY_GATE_FAILURE",
        title: `${w.workOrderNumber} — ${g.type.replace(/_/g, " ")} open`,
        detection: g.reason,
        source: w.workOrderNumber,
        impact: "Blocks progress toward release.",
        recommendedAction: "Review and resolve on the Planning detail page.",
        responsibleRole: "Maintenance Manager",
        approvalRequired: true,
        destinationHref: `/maintenance/planning/${w.id}`,
      });
    }
  }

  for (const p of getQuarantinedParts()) {
    items.push({
      id: `auto-quarantine-${p.partId}`,
      category: "QUARANTINE_REVIEW",
      title: `${p.partNumber} — quarantined`,
      detection: p.reason,
      source: `Part ${p.partNumber}`,
      impact: "Part unavailable for installation until disposition is resolved.",
      recommendedAction: "Review receiving-inspection documentation and disposition the part.",
      responsibleRole: "Quality / Receiving",
      approvalRequired: true,
      destinationHref: "/maintenance/parts",
    });
  }

  for (const d of getOpenDeferredItems()) {
    items.push({
      id: `auto-deferred-${d.id}`,
      category: "DEFERRED_ITEM_REVIEW",
      title: `Deferred item ${d.id} — ${d.category}`,
      detection: d.dueAt === null ? "No authoritative MEL reference or due date on file." : `Due ${d.dueAt}.`,
      source: `Deferred Item ${d.id}`,
      impact: "Operational limitation may apply.",
      recommendedAction: "Confirm MEL category/reference and monitor for the applicable time limit.",
      responsibleRole: "Maintenance Manager",
      approvalRequired: true,
      destinationHref: `/aircraft/${d.aircraftId}`,
    });
  }

  for (const c of cannibalizationRequests.filter((x) => x.authorizationStatus === "PENDING_HUMAN_REVIEW")) {
    items.push({
      id: `auto-cann-${c.id}`,
      category: "CANNIBALIZATION_REVIEW",
      title: `Cannibalization candidate — ${c.partId} → target aircraft`,
      detection: c.reason,
      source: `Cannibalization ${c.id}`,
      impact: "Potential AOG recovery path pending verification.",
      recommendedAction: "Verify donor part record and traceability before approving.",
      responsibleRole: "Maintenance Manager",
      approvalRequired: true,
      destinationHref: `/aircraft/${c.targetAircraftId}`,
    });
  }

  for (const r of getReleaseQueue()) {
    items.push({
      id: `auto-release-${r.workOrderId}`,
      category: "RELEASE_PACKAGE_INCOMPLETE",
      title: `${r.workOrderNumber} — release package incomplete`,
      detection: `Execution state is ${r.executionState.replace(/_/g, " ")}, not RELEASED.`,
      source: r.workOrderNumber,
      impact: "Aircraft/component cannot be considered released.",
      recommendedAction: "Complete remaining inspection/evidence steps on the Planning detail page.",
      responsibleRole: "Maintenance Manager",
      approvalRequired: true,
      destinationHref: `/maintenance/planning/${r.workOrderId}`,
    });
  }

  return items;
}

// M14.4 — Utilization-driven maintenance forecasting foundation. Uses
// Aircraft.flightHours/flightCycles (M12.9) and MaintenanceTask.fhThreshold/
// fcThreshold/calendarThresholdDays (above) when both a current value AND a
// threshold exist; otherwise honestly UNKNOWN. This dataset currently has
// no seeded threshold on any task, so this always returns UNKNOWN today —
// that is a correct reflection of source data, not a bug; it becomes
// meaningful the moment real threshold data is added.
export type MaintenanceDueStatus = "CURRENT" | "DUE_SOON" | "DUE" | "OVERDUE" | "UNKNOWN";

export interface MaintenanceForecastItem {
  workOrderId: string;
  taskDescription: string;
  dueStatus: MaintenanceDueStatus;
  reason: string;
}

export function getMaintenanceForecastForAircraft(aircraftId: string): MaintenanceForecastItem[] {
  const a = getAircraftById(aircraftId);
  if (!a) return [];
  const wos = workOrdersForAircraft(aircraftId).filter((w) => w.maintenanceTaskId);
  return wos.map((w) => {
    const task = getMaintenanceTaskById(w.maintenanceTaskId!);
    const hasThreshold = task && (task.fhThreshold != null || task.fcThreshold != null || task.calendarThresholdDays != null);

    let dueStatus: MaintenanceDueStatus = "UNKNOWN";
    let reason = "Insufficient source data — no maintenance-interval threshold is recorded for this task.";

    if (task?.calendarThresholdDays != null) {
      // M15/M16 — the one genuinely computable case in this dataset: a
      // calendar interval measured against the work order's own
      // plannedStartDate (the closest real "reference date" that exists),
      // compared to MOCK_TODAY. FH/FC intervals below stay UNKNOWN because
      // no last-accomplished FH/FC value is recorded anywhere — an
      // interval alone is not sufficient to forecast against.
      const daysSince = daysBetween(MOCK_TODAY, w.plannedStartDate);
      const daysRemaining = task.calendarThresholdDays - daysSince;
      if (daysRemaining < 0) { dueStatus = "OVERDUE"; reason = `Reference date ${w.plannedStartDate} + ${task.calendarThresholdDays}-day demo interval is ${Math.abs(daysRemaining)} day(s) in the past.`; }
      else if (daysRemaining === 0) { dueStatus = "DUE"; reason = `Due today per ${task.calendarThresholdDays}-day demo interval from ${w.plannedStartDate}.`; }
      else if (daysRemaining <= 7) { dueStatus = "DUE_SOON"; reason = `Due in ${daysRemaining} day(s) per ${task.calendarThresholdDays}-day demo interval from ${w.plannedStartDate}.`; }
      else { dueStatus = "CURRENT"; reason = `${daysRemaining} day(s) remaining per ${task.calendarThresholdDays}-day demo interval from ${w.plannedStartDate}.`; }
      reason += " Interval source: DEMO DATA (lib/mock/maintenanceProgram.ts) — not a real approved maintenance program.";
    } else if (!hasThreshold) {
      reason = "Insufficient source data — no maintenance-interval threshold is recorded for this task.";
    } else {
      reason = "Insufficient source data — an FH/FC interval is on file, but no last-accomplished FH/FC value is recorded anywhere in this dataset to forecast against.";
    }
    return { workOrderId: w.id, taskDescription: task?.description ?? w.title, dueStatus, reason };
  });
}

// M14.11 — inspection/release foundation clarity. Does not change how
// ExecutionState is derived (M12.9/M13, unchanged) — only labels it more
// explicitly so the four distinct concepts this milestone requires
// (TECHNICIAN COMPLETED / INSPECTED / RELEASE READY / RELEASED) are never
// blurred together in a response.
export function explainExecutionState(state: ExecutionState): string {
  switch (state) {
    case "NOT_STARTED": return "Work has not started.";
    case "BLOCKED": return "Work is blocked before starting (material or qualification gate open).";
    case "IN_PROGRESS": return "Technician work is in progress — not yet complete, not inspected, not released.";
    case "TECHNICIAN_COMPLETED": return "TECHNICIAN COMPLETED — the technician's step is done. This is NOT inspected and NOT released.";
    case "INSPECTION_REQUIRED": return "Awaiting independent inspection — technician step is done, inspection has not occurred.";
    case "INSPECTION_COMPLETED": return "INSPECTED — an inspection occurred but did not clear the work order for release (rejected/returned).";
    case "READY_FOR_RELEASE": return "RELEASE READY — all required steps are complete; a release action has not yet been recorded.";
    case "RELEASED": return "RELEASED — technician completion and (where required) inspection are both on record.";
    default: return "Insufficient source data.";
  }
}

/** Fleet-wide view of getMaintenanceForecastForAircraft — same function,
 * no second calculation, just applied across every aircraft. */
export function getFleetMaintenanceForecast(): { aircraftId: string; registration: string; items: MaintenanceForecastItem[] }[] {
  return aircraft.map((a) => ({ aircraftId: a.id, registration: currentRegistration(a), items: getMaintenanceForecastForAircraft(a.id) }));
}

// --- M16 Aircraft Utilization Intelligence ---
// Reads only Aircraft.flightHours/flightCycles/utilizationAsOfDate/
// utilizationSource (M12.9/M16) — no second utilization store, no
// fabricated historical values. "Stale" is a derived judgment call (>30
// days old), not a stored flag.

export type UtilizationDataQuality = "CURRENT" | "STALE" | "UNKNOWN_PROVENANCE" | "NO_DATA";

export interface AircraftUtilizationView {
  aircraftId: string;
  registration: string;
  flightHours: number | null;
  flightCycles: number | null;
  utilizationAsOfDate: string | null;
  utilizationSource: string | null;
  dataQuality: UtilizationDataQuality;
  daysSinceUpdate: number | null;
}

export function getAircraftUtilization(aircraftId: string): AircraftUtilizationView | null {
  const a = getAircraftById(aircraftId);
  if (!a) return null;
  const hasValue = a.flightHours != null || a.flightCycles != null;
  const daysSinceUpdate = a.utilizationAsOfDate != null ? daysBetween(MOCK_TODAY, a.utilizationAsOfDate) : null;

  let dataQuality: UtilizationDataQuality;
  if (!hasValue) dataQuality = "NO_DATA";
  else if (a.utilizationAsOfDate == null) dataQuality = "UNKNOWN_PROVENANCE";
  else if (daysSinceUpdate !== null && daysSinceUpdate > 30) dataQuality = "STALE";
  else dataQuality = "CURRENT";

  return {
    aircraftId,
    registration: currentRegistration(a),
    flightHours: a.flightHours ?? null,
    flightCycles: a.flightCycles ?? null,
    utilizationAsOfDate: a.utilizationAsOfDate ?? null,
    utilizationSource: a.utilizationSource ?? null,
    dataQuality,
    daysSinceUpdate,
  };
}

export function getFleetUtilization(): AircraftUtilizationView[] {
  return aircraft.map((a) => getAircraftUtilization(a.id)!);
}

export interface UtilizationDataQualitySummary {
  total: number;
  current: number;
  stale: number;
  unknownProvenance: number;
  noData: number;
}

export function getUtilizationDataQuality(): UtilizationDataQualitySummary {
  const fleet = getFleetUtilization();
  return {
    total: fleet.length,
    current: fleet.filter((f) => f.dataQuality === "CURRENT").length,
    stale: fleet.filter((f) => f.dataQuality === "STALE").length,
    unknownProvenance: fleet.filter((f) => f.dataQuality === "UNKNOWN_PROVENANCE").length,
    noData: fleet.filter((f) => f.dataQuality === "NO_DATA").length,
  };
}

export function getMaintenanceTaskChain(workOrderId: string): MaintenanceTaskChainStep[] {
  const w = workOrders.find((x) => x.id === workOrderId);
  if (!w) return [];
  const a = getAircraftById(w.aircraftId);
  const discrepancy = defectsForWorkOrder(w.id)[0];
  const task = w.maintenanceTaskId ? getMaintenanceTaskById(w.maintenanceTaskId) : undefined;

  return [
    { label: "Aircraft", detail: a ? currentRegistration(a) : "Insufficient source data.", href: a ? `/aircraft/${a.id}` : undefined },
    { label: "Discrepancy", detail: discrepancy ? `${discrepancy.description} (${discrepancy.severity})` : "No linked discrepancy record." },
    {
      label: "Maintenance Task",
      detail: task
        ? `${task.description} — ${task.referenceType === "OTHER" ? "Insufficient source data (no AD/SB/AMM reference on file)" : `${task.referenceType} ${requirementLabel(task.referenceId)}`}`
        : "No maintenance task linked to this work order.",
    },
    { label: "Work Order", detail: `${w.workOrderNumber} — ${w.title}`, href: `/maintenance/planning/${w.id}` },
  ];
}

/** M14.3 — Maintenance Task execution view: WHO performed the task and WHO
 * (if anyone yet) independently inspected it, plus the M12.9/M13
 * ExecutionState — reads the same WorkOrder.signOff/InspectorReview fields
 * getSignatureRecordsForWorkOrder already reads, no second data source. */
export interface MaintenanceTaskExecutionView {
  taskId: string | null;
  taskDescription: string;
  executionState: ExecutionState;
  performedBy: string; // technician name, or "Insufficient source data."
  performedAt: string | null;
  inspectedBy: string; // inspector name, or "Not yet inspected." / "Insufficient source data."
  inspectedAt: string | null;
}

export function getMaintenanceTaskExecutionView(workOrderId: string): MaintenanceTaskExecutionView | null {
  const w = workOrders.find((x) => x.id === workOrderId);
  if (!w) return null;
  const task = w.maintenanceTaskId ? getMaintenanceTaskById(w.maintenanceTaskId) : undefined;
  const review = getInspectorReviewForWorkOrder(w.id);
  const performer = w.signOff ? getTechnicianById(w.signOff.technicianId) : (w.assignedTechnicianId ? getTechnicianById(w.assignedTechnicianId) : undefined);
  const inspector = review ? getTechnicianById(review.inspectorId) : undefined;

  return {
    taskId: task?.id ?? null,
    taskDescription: task?.description ?? "No maintenance task linked to this work order.",
    executionState: getExecutionState(w),
    performedBy: w.signOff ? (performer?.name ?? "Insufficient source data.") : performer ? `${performer.name} (assigned, not yet signed off)` : "Insufficient source data.",
    performedAt: w.signOff?.timestamp ?? null,
    inspectedBy: review ? (review.reviewedAt ? inspector?.name ?? "Insufficient source data." : `Pending — ${inspector?.name ?? "inspector not yet reviewed"}`) : isInspectionRequired(w) ? "Not yet inspected." : "No inspection required for this task.",
    inspectedAt: review?.reviewedAt ?? null,
  };
}

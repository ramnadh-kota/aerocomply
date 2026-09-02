import type { WorkOrder } from "./types";

// MOCK DATA. Work orders connect to the compliance chain via
// relatedRequirementId/relatedAssessmentId wherever a real assessment already
// exists for that aircraft+requirement pair (verified against
// lib/mock/assessments.ts) — never a fabricated cross-reference.
//
// "Overdue" is deliberately NOT a status value (a real work order's status
// describes what stage of work it's in; overdue-ness is a derived fact about
// its due date). See isOverdue() below.
export const MOCK_TODAY = "2026-03-17";

export const workOrders: WorkOrder[] = [
  {
    id: "wo-1042",
    workOrderNumber: "WO-1042",
    projectId: "proj-1",
    workPackageId: "wp-1",
    aircraftId: "ac-1",
    title: "Engine Fan Inspection",
    ataChapter: "72",
    maintenanceType: "INSPECTION",
    priority: "HIGH",
    assignedTechnicianId: "tech-1",
    inspectorId: "tech-3",
    plannedStartDate: "2026-03-14",
    dueDate: "2026-03-16",
    completionDate: null,
    status: "WAITING_INSPECTION",
    requiredPartIds: ["part-2"],
    requiredTools: ["Borescope", "Torque Wrench"],
    relatedRequirementId: "req-ad-2026-001",
    relatedAssessmentId: "asmt-2",
    checklistId: "chk-1042",
    findingIds: ["finding-1"],
    signOff: { technicianId: "tech-1", timestamp: "2026-03-16T13:40:00Z", confirmed: true },
    inspectorReviewId: "ir-1",
  },
  {
    id: "wo-1043",
    workOrderNumber: "WO-1043",
    projectId: "proj-1",
    workPackageId: "wp-2",
    aircraftId: "ac-1",
    title: "Hydraulic Pump Seal Replacement",
    ataChapter: "29",
    maintenanceType: "REPLACEMENT",
    priority: "MEDIUM",
    assignedTechnicianId: "tech-4",
    inspectorId: "tech-5",
    plannedStartDate: "2026-03-07",
    dueDate: "2026-03-08",
    completionDate: "2026-03-08",
    status: "COMPLETED",
    requiredPartIds: ["part-1"],
    requiredTools: ["Seal Puller"],
    relatedRequirementId: "req-sb-2025-114",
    relatedAssessmentId: null,
    checklistId: "chk-1043",
    findingIds: ["finding-3"],
    signOff: { technicianId: "tech-4", timestamp: "2026-03-08T14:20:00Z", confirmed: true },
    inspectorReviewId: "ir-2",
  },
  {
    id: "wo-1044",
    workOrderNumber: "WO-1044",
    projectId: "proj-1",
    workPackageId: "wp-1",
    aircraftId: "ac-1",
    title: "Engine 1 Borescope Follow-up",
    ataChapter: "72",
    maintenanceType: "INSPECTION",
    priority: "HIGH",
    assignedTechnicianId: "tech-1",
    inspectorId: null,
    plannedStartDate: "2026-03-12",
    dueDate: "2026-03-13",
    completionDate: null,
    status: "IN_PROGRESS",
    requiredPartIds: [],
    requiredTools: ["Borescope"],
    relatedRequirementId: null,
    relatedAssessmentId: null,
    checklistId: "chk-1044",
    findingIds: [],
    signOff: null,
    inspectorReviewId: null,
  },
  {
    id: "wo-1045",
    workOrderNumber: "WO-1045",
    projectId: "proj-2",
    workPackageId: "wp-3",
    aircraftId: "ac-3",
    title: "Wing Spar Fatigue Inspection",
    ataChapter: "57",
    maintenanceType: "INSPECTION",
    priority: "CRITICAL",
    assignedTechnicianId: "tech-3",
    inspectorId: "tech-5",
    plannedStartDate: "2026-03-15",
    dueDate: "2026-03-19",
    completionDate: null,
    status: "WAITING_INSPECTION",
    requiredPartIds: [],
    requiredTools: ["NDT Kit"],
    relatedRequirementId: "req-ad-2026-004",
    relatedAssessmentId: null,
    checklistId: "chk-1045",
    findingIds: ["finding-2"],
    signOff: { technicianId: "tech-3", timestamp: "2026-03-16T17:00:00Z", confirmed: true },
    inspectorReviewId: "ir-5",
  },
  {
    id: "wo-1046",
    workOrderNumber: "WO-1046",
    projectId: "proj-3",
    workPackageId: "wp-4",
    aircraftId: "ac-7",
    title: "Cargo Door Latch Mechanism Inspection",
    ataChapter: "52",
    maintenanceType: "INSPECTION",
    priority: "HIGH",
    assignedTechnicianId: "tech-6",
    inspectorId: null,
    plannedStartDate: "2026-03-19",
    dueDate: "2026-03-22",
    completionDate: null,
    status: "ASSIGNED",
    requiredPartIds: ["part-6"],
    requiredTools: [],
    relatedRequirementId: "req-ad-2026-005",
    relatedAssessmentId: "asmt-bulk-3",
    checklistId: null,
    findingIds: [],
    signOff: null,
    inspectorReviewId: null,
  },
  {
    id: "wo-1047",
    workOrderNumber: "WO-1047",
    projectId: "proj-4",
    workPackageId: "wp-5",
    aircraftId: "ac-5",
    title: "Avionics Software Standard Update",
    ataChapter: "22",
    maintenanceType: "MODIFICATION",
    priority: "HIGH",
    assignedTechnicianId: "tech-2",
    inspectorId: "tech-5",
    plannedStartDate: "2026-01-24",
    dueDate: "2026-01-25",
    completionDate: "2026-01-25",
    status: "COMPLETED",
    requiredPartIds: [],
    requiredTools: [],
    relatedRequirementId: "req-ad-2026-003",
    relatedAssessmentId: "asmt-4",
    checklistId: null,
    findingIds: [],
    signOff: { technicianId: "tech-2", timestamp: "2026-01-25T09:00:00Z", confirmed: true },
    inspectorReviewId: "ir-3",
  },
  {
    id: "wo-1048",
    workOrderNumber: "WO-1048",
    projectId: null,
    workPackageId: null,
    aircraftId: "ac-9",
    title: "Fan Disk Ultrasonic Inspection Sign-off",
    ataChapter: "72",
    maintenanceType: "INSPECTION",
    priority: "HIGH",
    assignedTechnicianId: "tech-5",
    inspectorId: "tech-3",
    plannedStartDate: "2026-03-08",
    dueDate: "2026-03-10",
    completionDate: null,
    status: "WAITING_INSPECTION",
    requiredPartIds: [],
    requiredTools: ["Borescope"],
    relatedRequirementId: "req-ad-2026-001",
    relatedAssessmentId: "asmt-bulk-5",
    checklistId: "chk-1048",
    findingIds: [],
    signOff: { technicianId: "tech-5", timestamp: "2026-03-09T18:00:00Z", confirmed: true },
    inspectorReviewId: "ir-4",
  },
  {
    id: "wo-1049",
    workOrderNumber: "WO-1049",
    projectId: null,
    workPackageId: null,
    aircraftId: "ac-4",
    title: "Pitot Tube Heater Functional Check",
    ataChapter: "30",
    maintenanceType: "INSPECTION",
    priority: "LOW",
    assignedTechnicianId: "tech-2",
    inspectorId: null,
    plannedStartDate: "2026-02-18",
    dueDate: "2026-02-20",
    completionDate: null,
    status: "CANCELLED",
    requiredPartIds: [],
    requiredTools: [],
    relatedRequirementId: "req-ad-2026-006",
    relatedAssessmentId: "asmt-bulk-8",
    checklistId: null,
    findingIds: [],
    signOff: null,
    inspectorReviewId: null,
  },
  {
    id: "wo-1050",
    workOrderNumber: "WO-1050",
    projectId: null,
    workPackageId: null,
    aircraftId: "ac-1",
    title: "Hydraulic Pump Seal Condition Check",
    ataChapter: "29",
    maintenanceType: "INSPECTION",
    priority: "MEDIUM",
    assignedTechnicianId: "tech-4",
    inspectorId: null,
    plannedStartDate: "2026-03-17",
    dueDate: "2026-03-18",
    completionDate: null,
    status: "WAITING_PARTS",
    requiredPartIds: ["part-1"],
    requiredTools: [],
    relatedRequirementId: "req-sb-2025-114",
    relatedAssessmentId: null,
    checklistId: null,
    findingIds: [],
    signOff: null,
    inspectorReviewId: null,
  },
  {
    id: "wo-1051",
    workOrderNumber: "WO-1051",
    projectId: null,
    workPackageId: null,
    aircraftId: "ac-3",
    title: "IDG Seal Repair",
    ataChapter: "24",
    maintenanceType: "REPAIR",
    // M12.7.1 — escalated to CRITICAL as the seed anchor for the AOG +
    // material-blocker connected scenario (N412MX / GEN-305): this aircraft
    // already carries an open HIGH-severity defect (def-2), so this work
    // order being CRITICAL is consistent with, not independent of, that
    // existing record.
    priority: "CRITICAL",
    assignedTechnicianId: "tech-3",
    inspectorId: null,
    plannedStartDate: "2026-03-20",
    dueDate: "2026-03-21",
    completionDate: null,
    status: "ASSIGNED",
    requiredPartIds: ["part-5"],
    requiredTools: [],
    relatedRequirementId: null,
    relatedAssessmentId: null,
    checklistId: null,
    findingIds: [],
    signOff: null,
    inspectorReviewId: null,
  },
  // --- M12.7.1 operational data enrichment. Every new work order links to
  // an existing aircraft/technician; nothing here invents a new aircraft or
  // technician identity. Covers aircraft that previously had zero or only
  // cancelled work orders (VT-XYZ, N118ML, VT-JKL, N221ML), and adds
  // BLOCKED/CRITICAL/COMPLETED coverage the milestone asked for.
  {
    id: "wo-1052",
    workOrderNumber: "WO-1052",
    projectId: null,
    workPackageId: null,
    aircraftId: "ac-2",
    title: "Cabin Pressurization Check",
    ataChapter: "21",
    maintenanceType: "INSPECTION",
    priority: "MEDIUM",
    assignedTechnicianId: "tech-2",
    inspectorId: null,
    plannedStartDate: "2026-03-16",
    dueDate: "2026-03-19",
    completionDate: null,
    status: "IN_PROGRESS",
    requiredPartIds: [],
    requiredTools: [],
    relatedRequirementId: null,
    relatedAssessmentId: null,
    checklistId: null,
    findingIds: [],
    signOff: null,
    inspectorReviewId: null,
  },
  {
    id: "wo-1053",
    workOrderNumber: "WO-1053",
    projectId: null,
    workPackageId: null,
    aircraftId: "ac-6",
    title: "Brake Wear Inspection",
    ataChapter: "32",
    maintenanceType: "INSPECTION",
    priority: "HIGH",
    assignedTechnicianId: null,
    inspectorId: null,
    plannedStartDate: "2026-03-18",
    dueDate: "2026-03-20",
    completionDate: null,
    status: "DRAFT",
    requiredPartIds: ["part-4"],
    requiredTools: [],
    relatedRequirementId: null,
    relatedAssessmentId: null,
    checklistId: null,
    findingIds: [],
    signOff: null,
    inspectorReviewId: null,
  },
  {
    id: "wo-1054",
    workOrderNumber: "WO-1054",
    projectId: null,
    workPackageId: null,
    // ac-3 (N412MX) — matches the existing part-8/ci-apu301 installation
    // record already seeded on this aircraft, not a new inconsistent link.
    aircraftId: "ac-3",
    title: "APU Starter Motor Replacement",
    ataChapter: "49",
    maintenanceType: "REPLACEMENT",
    priority: "HIGH",
    assignedTechnicianId: "tech-5",
    inspectorId: null,
    plannedStartDate: "2026-03-10",
    dueDate: "2026-03-14",
    completionDate: null,
    status: "WAITING_PARTS",
    requiredPartIds: ["part-8"],
    requiredTools: [],
    relatedRequirementId: null,
    relatedAssessmentId: null,
    checklistId: null,
    findingIds: [],
    signOff: null,
    inspectorReviewId: null,
  },
  {
    id: "wo-1055",
    workOrderNumber: "WO-1055",
    projectId: null,
    workPackageId: null,
    aircraftId: "ac-10",
    title: "Fuel Control Unit Calibration",
    ataChapter: "73",
    maintenanceType: "REPAIR",
    priority: "CRITICAL",
    assignedTechnicianId: "tech-1",
    inspectorId: null,
    plannedStartDate: "2026-03-11",
    dueDate: "2026-03-15",
    completionDate: null,
    status: "WAITING_PARTS",
    requiredPartIds: ["part-3"],
    requiredTools: [],
    relatedRequirementId: null,
    relatedAssessmentId: null,
    checklistId: null,
    findingIds: [],
    signOff: null,
    inspectorReviewId: null,
  },
  {
    id: "wo-1056",
    workOrderNumber: "WO-1056",
    projectId: null,
    workPackageId: null,
    aircraftId: "ac-9",
    title: "Landing Gear Retraction Test",
    ataChapter: "32",
    maintenanceType: "INSPECTION",
    priority: "MEDIUM",
    assignedTechnicianId: "tech-6",
    inspectorId: null,
    plannedStartDate: "2026-02-25",
    dueDate: "2026-02-27",
    completionDate: "2026-02-27",
    status: "COMPLETED",
    requiredPartIds: [],
    requiredTools: [],
    relatedRequirementId: null,
    relatedAssessmentId: null,
    checklistId: null,
    findingIds: [],
    signOff: { technicianId: "tech-6", timestamp: "2026-02-27T15:10:00Z", confirmed: true },
    inspectorReviewId: null,
  },
  {
    id: "wo-1057",
    workOrderNumber: "WO-1057",
    projectId: null,
    workPackageId: null,
    aircraftId: "ac-5",
    title: "Seal Kit Replacement — Hydraulic Reservoir",
    ataChapter: "29",
    maintenanceType: "REPLACEMENT",
    priority: "LOW",
    assignedTechnicianId: "tech-4",
    inspectorId: null,
    plannedStartDate: "2026-03-19",
    dueDate: "2026-03-24",
    completionDate: null,
    status: "ASSIGNED",
    requiredPartIds: ["part-7"],
    requiredTools: [],
    relatedRequirementId: null,
    relatedAssessmentId: null,
    checklistId: null,
    findingIds: [],
    signOff: null,
    inspectorReviewId: null,
  },
  {
    id: "wo-1058",
    workOrderNumber: "WO-1058",
    projectId: null,
    workPackageId: null,
    aircraftId: "ac-4",
    title: "Pitot Heater Replacement",
    ataChapter: "30",
    maintenanceType: "REPLACEMENT",
    priority: "HIGH",
    assignedTechnicianId: null,
    inspectorId: null,
    plannedStartDate: "2026-03-13",
    dueDate: "2026-03-16",
    completionDate: null,
    status: "DRAFT",
    requiredPartIds: [],
    requiredTools: [],
    relatedRequirementId: null,
    relatedAssessmentId: null,
    checklistId: null,
    findingIds: [],
    signOff: null,
    inspectorReviewId: null,
  },
];

export function getWorkOrderById(id: string): WorkOrder | undefined {
  return workOrders.find((w) => w.id === id);
}

export function workOrdersForAircraft(aircraftId: string): WorkOrder[] {
  return workOrders.filter((w) => w.aircraftId === aircraftId);
}

export function workOrdersForProject(projectId: string): WorkOrder[] {
  return workOrders.filter((w) => w.projectId === projectId);
}

export function workOrdersForTechnician(technicianId: string): WorkOrder[] {
  return workOrders.filter((w) => w.assignedTechnicianId === technicianId);
}

export function isOverdue(w: WorkOrder, today = MOCK_TODAY): boolean {
  return w.dueDate < today && w.status !== "COMPLETED" && w.status !== "CANCELLED";
}

export function openWorkOrders(): WorkOrder[] {
  return workOrders.filter((w) => w.status !== "COMPLETED" && w.status !== "CANCELLED");
}

export function overdueWorkOrders(): WorkOrder[] {
  return workOrders.filter((w) => isOverdue(w));
}

export function awaitingPartsWorkOrders(): WorkOrder[] {
  return workOrders.filter((w) => w.status === "WAITING_PARTS");
}

export function awaitingReviewWorkOrders(): WorkOrder[] {
  return workOrders.filter((w) => w.status === "WAITING_INSPECTION");
}

// M12.4 — smallest mutations the Planning Center needs, following the same
// in-place-mutate-the-array pattern as roles/reports/procurement (see
// updateRole in lib/mock/roles.ts). Both return the updated WorkOrder (or
// null if the id/precondition doesn't hold) so the caller can emit an audit
// event with the real before/after state — no separate state store.

export function assignTechnician(workOrderId: string, technicianId: string): WorkOrder | null {
  const w = workOrders.find((x) => x.id === workOrderId);
  if (!w) return null;
  w.assignedTechnicianId = technicianId;
  if (w.status === "DRAFT") w.status = "ASSIGNED";
  return w;
}

export function startWorkOrder(workOrderId: string): WorkOrder | null {
  const w = workOrders.find((x) => x.id === workOrderId);
  if (!w || w.assignedTechnicianId === null) return null;
  // DRAFT/ASSIGNED are the normal pre-start statuses; WAITING_PARTS is also
  // allowed here because the planning layer (getWorkOrderPlanningRow) can
  // derive READY for a WAITING_PARTS work order whose linked part record
  // shows no actual shortage — see the dataInconsistencyNote comment in
  // lib/mock/ai/analytics.ts. WAITING_INSPECTION/IN_PROGRESS/COMPLETED/
  // CANCELLED are never valid states to "start" from.
  if (w.status !== "ASSIGNED" && w.status !== "DRAFT" && w.status !== "WAITING_PARTS") return null;
  w.status = "IN_PROGRESS";
  return w;
}

// M12.6 — smallest additional mutations the Execution & Action Center
// needs, following the exact same pattern as assignTechnician/
// startWorkOrder above (mutate in place, return the updated WorkOrder or
// null, let the caller emit the audit event with real before/after state).

/** Removing an assignment is real, supported domain behavior — the field
 * is nullable — never destructive to anything else on the record. */
export function unassignTechnician(workOrderId: string): WorkOrder | null {
  const w = workOrders.find((x) => x.id === workOrderId);
  if (!w) return null;
  w.assignedTechnicianId = null;
  return w;
}

export function completeWorkOrder(workOrderId: string, completionDate: string): WorkOrder | null {
  const w = workOrders.find((x) => x.id === workOrderId);
  if (!w || w.status !== "IN_PROGRESS") return null;
  w.status = "COMPLETED";
  w.completionDate = completionDate;
  return w;
}

/** "Escalate" has no dedicated WorkOrderStatus value in the domain model —
 * inventing one would be a fabricated workflow state. Priority is a real,
 * existing, mutable field, so escalation is implemented honestly as
 * raising priority to CRITICAL (the highest real value) rather than a fake
 * status transition. No-op (returns null) if already CRITICAL. */
export function escalateWorkOrder(workOrderId: string): WorkOrder | null {
  const w = workOrders.find((x) => x.id === workOrderId);
  if (!w || w.priority === "CRITICAL") return null;
  w.priority = "CRITICAL";
  return w;
}

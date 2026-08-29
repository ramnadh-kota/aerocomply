import type { WorkOrder } from "./types";

// MOCK DATA. Work orders connect to the compliance chain via
// relatedRequirementId/relatedAssessmentId wherever a real assessment already
// exists for that aircraft+requirement pair (verified against
// lib/mock/assessments.ts) — never a fabricated cross-reference.

export const workOrders: WorkOrder[] = [
  {
    id: "wo-1042",
    workOrderNumber: "WO-1042",
    projectId: "proj-1",
    workPackageId: "wp-1",
    aircraftId: "ac-1",
    title: "Engine Fan Inspection",
    priority: "HIGH",
    assignedTechnicianId: "tech-1",
    dueDate: "2026-03-16",
    status: "AWAITING_REVIEW",
    requiredPartIds: [],
    requiredTools: ["Borescope", "Torque Wrench"],
    relatedRequirementId: "req-ad-2026-001",
    relatedAssessmentId: "asmt-2",
    checklistId: "chk-1042",
  },
  {
    id: "wo-1043",
    workOrderNumber: "WO-1043",
    projectId: "proj-1",
    workPackageId: "wp-2",
    aircraftId: "ac-1",
    title: "Hydraulic Pump Seal Replacement",
    priority: "MEDIUM",
    assignedTechnicianId: "tech-4",
    dueDate: "2026-03-08",
    status: "COMPLETED",
    requiredPartIds: ["part-1"],
    requiredTools: ["Seal Puller"],
    relatedRequirementId: "req-sb-2025-114",
    relatedAssessmentId: null,
    checklistId: "chk-1043",
  },
  {
    id: "wo-1044",
    workOrderNumber: "WO-1044",
    projectId: "proj-1",
    workPackageId: "wp-1",
    aircraftId: "ac-1",
    title: "Engine 1 Borescope Follow-up",
    priority: "HIGH",
    assignedTechnicianId: "tech-1",
    dueDate: "2026-03-13",
    status: "OVERDUE",
    requiredPartIds: [],
    requiredTools: ["Borescope"],
    relatedRequirementId: null,
    relatedAssessmentId: null,
    checklistId: null,
  },
  {
    id: "wo-1045",
    workOrderNumber: "WO-1045",
    projectId: "proj-2",
    workPackageId: "wp-3",
    aircraftId: "ac-3",
    title: "Wing Spar Fatigue Inspection",
    priority: "CRITICAL",
    assignedTechnicianId: "tech-3",
    dueDate: "2026-03-19",
    status: "IN_PROGRESS",
    requiredPartIds: [],
    requiredTools: ["NDT Kit"],
    relatedRequirementId: "req-ad-2026-004",
    relatedAssessmentId: null,
    checklistId: null,
  },
  {
    id: "wo-1046",
    workOrderNumber: "WO-1046",
    projectId: "proj-3",
    workPackageId: "wp-4",
    aircraftId: "ac-7",
    title: "Cargo Door Latch Mechanism Inspection",
    priority: "HIGH",
    assignedTechnicianId: "tech-6",
    dueDate: "2026-03-22",
    status: "PLANNED",
    requiredPartIds: ["part-6"],
    requiredTools: [],
    relatedRequirementId: "req-ad-2026-005",
    relatedAssessmentId: "asmt-bulk-3",
    checklistId: null,
  },
  {
    id: "wo-1047",
    workOrderNumber: "WO-1047",
    projectId: "proj-4",
    workPackageId: "wp-5",
    aircraftId: "ac-5",
    title: "Avionics Software Standard Update",
    priority: "HIGH",
    assignedTechnicianId: "tech-2",
    dueDate: "2026-01-25",
    status: "COMPLETED",
    requiredPartIds: [],
    requiredTools: [],
    relatedRequirementId: "req-ad-2026-003",
    relatedAssessmentId: "asmt-4",
    checklistId: null,
  },
  {
    id: "wo-1048",
    workOrderNumber: "WO-1048",
    projectId: null,
    workPackageId: null,
    aircraftId: "ac-9",
    title: "Fan Disk Ultrasonic Inspection Sign-off",
    priority: "HIGH",
    assignedTechnicianId: "tech-5",
    dueDate: "2026-03-10",
    status: "AWAITING_REVIEW",
    requiredPartIds: [],
    requiredTools: ["Borescope"],
    relatedRequirementId: "req-ad-2026-001",
    relatedAssessmentId: "asmt-bulk-5",
    checklistId: null,
  },
  {
    id: "wo-1049",
    workOrderNumber: "WO-1049",
    projectId: null,
    workPackageId: null,
    aircraftId: "ac-4",
    title: "Pitot Tube Heater Functional Check",
    priority: "LOW",
    assignedTechnicianId: "tech-2",
    dueDate: "2026-02-20",
    status: "DEFERRED",
    requiredPartIds: [],
    requiredTools: [],
    relatedRequirementId: "req-ad-2026-006",
    relatedAssessmentId: "asmt-bulk-8",
    checklistId: null,
  },
  {
    id: "wo-1050",
    workOrderNumber: "WO-1050",
    projectId: null,
    workPackageId: null,
    aircraftId: "ac-1",
    title: "Hydraulic Pump Seal Condition Check",
    priority: "MEDIUM",
    assignedTechnicianId: "tech-4",
    dueDate: "2026-03-17",
    status: "AWAITING_PARTS",
    requiredPartIds: ["part-1"],
    requiredTools: [],
    relatedRequirementId: "req-sb-2025-114",
    relatedAssessmentId: null,
    checklistId: null,
  },
  {
    id: "wo-1051",
    workOrderNumber: "WO-1051",
    projectId: null,
    workPackageId: null,
    aircraftId: "ac-3",
    title: "IDG Seal Repair",
    priority: "MEDIUM",
    assignedTechnicianId: "tech-3",
    dueDate: "2026-03-20",
    status: "OPEN",
    requiredPartIds: ["part-5"],
    requiredTools: [],
    relatedRequirementId: null,
    relatedAssessmentId: null,
    checklistId: null,
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

export function openWorkOrders(): WorkOrder[] {
  return workOrders.filter((w) => !["COMPLETED", "DEFERRED"].includes(w.status));
}

export function overdueWorkOrders(): WorkOrder[] {
  return workOrders.filter((w) => w.status === "OVERDUE");
}

export function awaitingPartsWorkOrders(): WorkOrder[] {
  return workOrders.filter((w) => w.status === "AWAITING_PARTS");
}

export function awaitingReviewWorkOrders(): WorkOrder[] {
  return workOrders.filter((w) => w.status === "AWAITING_REVIEW");
}

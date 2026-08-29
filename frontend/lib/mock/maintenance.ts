import type { MaintenanceEvent } from "./types";

// MOCK DATA. Compliance-oriented maintenance events only — no work orders,
// task cards, costing, or scheduling engine (docs/ontology/M1_SCOPE.md).

export const maintenanceEvents: MaintenanceEvent[] = [
  { id: "mx-1", eventType: "INSPECTION", status: "COMPLETED", subjectType: "ENGINE", aircraftId: "ac-1", engineId: "eng-100781", componentInstanceId: null, description: "Fan disk ultrasonic inspection per AD-2026-001", date: "2026-03-14", relatedRequirementId: "req-ad-2026-001", relatedAssessmentId: "asmt-2" },
  { id: "mx-2", eventType: "INSTALLATION", status: "COMPLETED", subjectType: "ENGINE", aircraftId: "ac-1", engineId: "eng-100781", componentInstanceId: null, description: "Engine 1 (CFM56-7B SN 100781) installed", date: "2026-02-11", relatedRequirementId: null, relatedAssessmentId: null },
  { id: "mx-3", eventType: "REMOVAL", status: "COMPLETED", subjectType: "ENGINE", aircraftId: "ac-1", engineId: "eng-100234", componentInstanceId: null, description: "Engine 1 (CFM56-7B SN 100234) removed for scheduled overhaul", date: "2026-02-10", relatedRequirementId: null, relatedAssessmentId: null },
  { id: "mx-4", eventType: "INSPECTION", status: "AWAITING_REVIEW", subjectType: "COMPONENT_INSTANCE", aircraftId: "ac-1", engineId: null, componentInstanceId: "ci-hp001", description: "Hydraulic pump seal condition check per SB-2025-114", date: "2026-03-16", relatedRequirementId: "req-sb-2025-114", relatedAssessmentId: null },
  { id: "mx-5", eventType: "INSPECTION", status: "SCHEDULED", subjectType: "AIRCRAFT", aircraftId: "ac-3", engineId: null, componentInstanceId: null, description: "Fan disk ultrasonic inspection per AD-2026-001", date: "2026-03-25", relatedRequirementId: "req-ad-2026-001", relatedAssessmentId: "asmt-bulk-0" },
  { id: "mx-6", eventType: "INSPECTION", status: "OVERDUE", subjectType: "AIRCRAFT", aircraftId: "ac-7", engineId: null, componentInstanceId: null, description: "Cargo door latch mechanism inspection per AD-2026-005", date: "2026-03-05", relatedRequirementId: "req-ad-2026-005", relatedAssessmentId: "asmt-bulk-3" },
  { id: "mx-7", eventType: "REPAIR", status: "IN_PROGRESS", subjectType: "COMPONENT_INSTANCE", aircraftId: "ac-3", engineId: null, componentInstanceId: "ci-gen114", description: "Integrated drive generator seal repair", date: "2026-03-18", relatedRequirementId: null, relatedAssessmentId: null },
  { id: "mx-8", eventType: "OVERHAUL", status: "COMPLETED", subjectType: "COMPONENT_INSTANCE", aircraftId: "ac-3", engineId: null, componentInstanceId: "ci-apu301", description: "APU overhaul completed and returned to service", date: "2025-08-01", relatedRequirementId: null, relatedAssessmentId: null },
  { id: "mx-9", eventType: "REPLACEMENT", status: "AWAITING_EVIDENCE", subjectType: "COMPONENT_INSTANCE", aircraftId: "ac-7", engineId: null, componentInstanceId: "ci-apu301", description: "APU replacement — completion evidence not yet uploaded", date: "2026-01-20", relatedRequirementId: null, relatedAssessmentId: null },
  { id: "mx-10", eventType: "INSPECTION", status: "SCHEDULED", subjectType: "AIRCRAFT", aircraftId: "ac-9", engineId: null, componentInstanceId: null, description: "Fan disk ultrasonic inspection per AD-2026-001", date: "2026-03-28", relatedRequirementId: "req-ad-2026-001", relatedAssessmentId: "asmt-bulk-5" },
  { id: "mx-11", eventType: "INSPECTION", status: "SCHEDULED", subjectType: "AIRCRAFT", aircraftId: "ac-4", engineId: null, componentInstanceId: null, description: "Wing spar fatigue inspection per AD-2026-004", date: "2026-04-02", relatedRequirementId: "req-ad-2026-004", relatedAssessmentId: "asmt-bulk-1" },
  { id: "mx-12", eventType: "INSPECTION", status: "COMPLETED", subjectType: "AIRCRAFT", aircraftId: "ac-10", engineId: null, componentInstanceId: null, description: "Pitot tube heater functional check per AD/A320/112", date: "2026-02-16", relatedRequirementId: "req-ad-2026-006", relatedAssessmentId: "asmt-bulk-6" },
  { id: "mx-13", eventType: "INSPECTION", status: "OVERDUE", subjectType: "AIRCRAFT", aircraftId: "ac-8", engineId: null, componentInstanceId: null, description: "Cargo door latch mechanism inspection per AD-2026-005", date: "2026-02-28", relatedRequirementId: "req-ad-2026-005", relatedAssessmentId: "asmt-bulk-4" },
  { id: "mx-14", eventType: "INSTALLATION", status: "COMPLETED", subjectType: "COMPONENT_INSTANCE", aircraftId: "ac-1", engineId: null, componentInstanceId: "ci-hp001", description: "Hydraulic pump HP-442 (SN HP001) installed", date: "2025-11-03", relatedRequirementId: null, relatedAssessmentId: null },
  { id: "mx-15", eventType: "INSPECTION", status: "SCHEDULED", subjectType: "AIRCRAFT", aircraftId: "ac-6", engineId: null, componentInstanceId: null, description: "Wing spar fatigue inspection per AD-2026-004", date: "2026-04-05", relatedRequirementId: "req-ad-2026-004", relatedAssessmentId: "asmt-bulk-2" },
  { id: "mx-16", eventType: "INSPECTION", status: "AWAITING_REVIEW", subjectType: "ENGINE", aircraftId: "ac-9", engineId: "eng-200014", componentInstanceId: null, description: "Fan disk ultrasonic inspection completed, pending engineering sign-off", date: "2026-03-09", relatedRequirementId: "req-ad-2026-001", relatedAssessmentId: "asmt-bulk-5" },
];

export function maintenanceEventsForAircraft(aircraftId: string): MaintenanceEvent[] {
  return maintenanceEvents.filter((m) => m.aircraftId === aircraftId).sort((a, b) => b.date.localeCompare(a.date));
}

export function maintenanceEventsForEngine(engineId: string): MaintenanceEvent[] {
  return maintenanceEvents.filter((m) => m.engineId === engineId).sort((a, b) => b.date.localeCompare(a.date));
}

export function maintenanceEventsForComponentInstance(instanceId: string): MaintenanceEvent[] {
  return maintenanceEvents.filter((m) => m.componentInstanceId === instanceId).sort((a, b) => b.date.localeCompare(a.date));
}

export function overdueMaintenanceEvents(): MaintenanceEvent[] {
  return maintenanceEvents.filter((m) => m.status === "OVERDUE").sort((a, b) => a.date.localeCompare(b.date));
}

export function upcomingMaintenanceEvents(limit = 5): MaintenanceEvent[] {
  return maintenanceEvents
    .filter((m) => m.status === "SCHEDULED")
    .sort((a, b) => a.date.localeCompare(b.date))
    .slice(0, limit);
}

export function awaitingActionMaintenanceEvents(): MaintenanceEvent[] {
  return maintenanceEvents.filter((m) => m.status === "AWAITING_EVIDENCE" || m.status === "AWAITING_REVIEW");
}

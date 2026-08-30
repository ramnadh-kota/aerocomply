// M8.1 — Domain repository abstraction.
//
// Purpose: give the UI a stable, typed seam (Repository interface) between
// itself and the data source, instead of importing raw mock arrays and
// helper functions from lib/mock/* directly everywhere. Today every
// repository below is a thin wrapper around the SAME existing mock helpers
// (no new data, no new logic, no duplicate computation) — swapping the mock
// implementation for a real database-backed one later means changing only
// this file, not the pages or components that consume it.
//
// This is intentionally NOT a full migration of the application. Existing
// pages that already import lib/mock/* directly continue to work unchanged
// (see M7 CTO report — "do not rewrite the entire application"). New
// high-value work (e.g. the evidence detail page below) is written against
// these interfaces so future workflows accrue the abstraction instead of
// adding another direct mock-array dependency.

import { aircraft as aircraftRows, getAircraftById, getAircraftByRegistration, currentRegistration } from "../mock/aircraft";
import { workOrders as workOrderRows, getWorkOrderById, workOrdersForAircraft, workOrdersForProject, workOrdersForTechnician, isOverdue } from "../mock/workOrders";
import { defects as defectRows, defectsForAircraft, defectsForWorkOrder } from "../mock/defects";
import { getInspectorReviewById, getInspectorReviewForWorkOrder, inspectorReviews as inspectorReviewRows } from "../mock/inspectorReviews";
import { evidence as evidenceRows, getEvidenceById, evidenceForAssessment } from "../mock/evidence";
import { parts as partRows, getPartById, partsForWorkOrder, partsForAircraft } from "../mock/parts";
import { partCertificates as certificateRows, certificatesForPart } from "../mock/partTraceability";
import { regulatoryRequirements as requirementRows, getRequirementById } from "../mock/regulations";
import { auditEvents as auditEventRows, auditEventsForObjectLabelContains } from "../mock/audit";
import { organizations as organizationRows, getOrganizationById } from "../mock/organizations";
import { users as userRows, roles as roleRows, getUserById, getRoleById, type UserAccount, type Role } from "../mock/roles";
import {
  getWorkOrderCostSummary,
  getAircraftCostSummary,
  getFleetFinancialSummary,
  workOrderIdsWithCostData,
  type WorkOrderCostSummary,
  type AircraftCostSummary,
  type FleetFinancialSummary,
} from "../mock/finance";
import type { Aircraft, WorkOrder, Defect, InspectorReview, Evidence, Part, PartCertificate, RegulatoryRequirement, AuditEvent, Organization } from "../mock/types";

export interface AircraftRepository {
  list(): Aircraft[];
  getById(id: string): Aircraft | undefined;
  getByRegistration(mark: string): Aircraft | undefined;
  displayRegistration(a: Aircraft): string;
}

export interface WorkOrderRepository {
  list(): WorkOrder[];
  getById(id: string): WorkOrder | undefined;
  forAircraft(aircraftId: string): WorkOrder[];
  forProject(projectId: string): WorkOrder[];
  forTechnician(technicianId: string): WorkOrder[];
  isOverdue(w: WorkOrder): boolean;
}

export interface DefectRepository {
  list(): Defect[];
  forAircraft(aircraftId: string): Defect[];
  forWorkOrder(workOrderId: string): Defect[];
}

export interface InspectionRepository {
  list(): InspectorReview[];
  getById(id: string): InspectorReview | undefined;
  forWorkOrder(workOrderId: string): InspectorReview | undefined;
}

export interface EvidenceRepository {
  list(): Evidence[];
  getById(id: string): Evidence | undefined;
  forAssessment(assessmentId: string): Evidence[];
}

export interface PartRepository {
  list(): Part[];
  getById(id: string): Part | undefined;
  forWorkOrder(workOrderId: string): Part[];
  forAircraft(aircraftId: string): Part[];
}

export interface CertificateRepository {
  list(): PartCertificate[];
  forPart(partId: string): PartCertificate[];
}

export interface RegulationRepository {
  listRequirements(): RegulatoryRequirement[];
  getRequirementById(id: string): RegulatoryRequirement | undefined;
}

export interface AuditRepository {
  list(): AuditEvent[];
  forObjectLabelContains(fragment: string): AuditEvent[];
}

export interface OrganizationRepository {
  list(): Organization[];
  getById(id: string): Organization | undefined;
}

export interface UserRepository {
  list(): UserAccount[];
  getById(id: string): UserAccount | undefined;
  listRoles(): Role[];
  getRoleById(id: string): Role | undefined;
}

// --- Mock implementations — delegate to the existing lib/mock/* helpers.
// No mock data or logic is duplicated here.

export const aircraftRepository: AircraftRepository = {
  list: () => aircraftRows,
  getById: getAircraftById,
  getByRegistration: getAircraftByRegistration,
  displayRegistration: currentRegistration,
};

export const workOrderRepository: WorkOrderRepository = {
  list: () => workOrderRows,
  getById: getWorkOrderById,
  forAircraft: workOrdersForAircraft,
  forProject: workOrdersForProject,
  forTechnician: workOrdersForTechnician,
  isOverdue: (w) => isOverdue(w),
};

export const defectRepository: DefectRepository = {
  list: () => defectRows,
  forAircraft: defectsForAircraft,
  forWorkOrder: defectsForWorkOrder,
};

export const inspectionRepository: InspectionRepository = {
  list: () => inspectorReviewRows,
  getById: getInspectorReviewById,
  forWorkOrder: getInspectorReviewForWorkOrder,
};

export const evidenceRepository: EvidenceRepository = {
  list: () => evidenceRows,
  getById: getEvidenceById,
  forAssessment: evidenceForAssessment,
};

export const partRepository: PartRepository = {
  list: () => partRows,
  getById: getPartById,
  forWorkOrder: partsForWorkOrder,
  forAircraft: partsForAircraft,
};

export const certificateRepository: CertificateRepository = {
  list: () => certificateRows,
  forPart: certificatesForPart,
};

export const regulationRepository: RegulationRepository = {
  listRequirements: () => requirementRows,
  getRequirementById,
};

export const auditRepository: AuditRepository = {
  list: () => auditEventRows,
  forObjectLabelContains: auditEventsForObjectLabelContains,
};

export const organizationRepository: OrganizationRepository = {
  list: () => organizationRows,
  getById: getOrganizationById,
};

export const userRepository: UserRepository = {
  list: () => userRows,
  getById: getUserById,
  listRoles: () => roleRows,
  getRoleById,
};

// M10.1 — Finance repository seam, following the same pattern as every
// other repository above: thin delegation to lib/mock/finance.ts, no
// duplicated calculation logic.
export interface FinanceRepository {
  workOrderCostSummary(workOrderId: string): WorkOrderCostSummary | null;
  aircraftCostSummary(aircraftId: string, workOrderIds: string[]): AircraftCostSummary | null;
  fleetFinancialSummary(workOrderIds: string[]): FleetFinancialSummary;
  workOrderIdsWithCostData(): string[];
}

export const financeRepository: FinanceRepository = {
  workOrderCostSummary: getWorkOrderCostSummary,
  aircraftCostSummary: getAircraftCostSummary,
  fleetFinancialSummary: getFleetFinancialSummary,
  workOrderIdsWithCostData,
};

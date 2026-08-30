// AeroComply M0.5 prototype — mock domain types.
// Names and shapes are drawn directly from docs/ontology/*.md and FOUNDATION.md.
// This file is UI-facing mock data only — it is not a database schema and must
// not be treated as one (see docs/ontology/M1_SCOPE.md).

export type SystemResult = "APPLICABLE" | "NOT_APPLICABLE" | "REVIEW_REQUIRED" | "INSUFFICIENT_DATA";

export type HumanDecision =
  | "PENDING"
  | "CONFIRMED_APPLICABLE"
  | "CONFIRMED_NOT_APPLICABLE"
  | "REQUEST_MORE_EVIDENCE"
  | "OVERRIDDEN";

export type FinalStatus = "COMPLIANT" | "NON_COMPLIANT" | "REVIEW_REQUIRED" | "INSUFFICIENT_DATA";

// Three-valued logic result for a single condition node — "unknown is not false"
// (docs/ontology/DOMAIN_INVARIANTS.md #23).
export type ConditionResult = "TRUE" | "FALSE" | "UNKNOWN";

export type OrgType = "OPERATOR" | "CAMO" | "MRO" | "LESSOR";

export interface Organization {
  id: string;
  name: string;
  orgType: OrgType;
}

export interface AircraftType {
  id: string;
  manufacturer: string;
  designation: string; // e.g. "737"
}

export interface AircraftVariant {
  id: string;
  aircraftTypeId: string;
  modelDesignation: string; // e.g. "737-800"
  tcdsNumber: string;
}

export type AircraftStatus = "ACTIVE" | "STORED" | "WRITTEN_OFF";

export interface RegistrationHistoryEntry {
  id: string;
  registrationMark: string;
  effectiveFrom: string; // ISO date
  effectiveTo: string | null; // null = current
}

export interface Aircraft {
  id: string;
  msn: string;
  aircraftVariantId: string;
  operatorOrgId: string;
  status: AircraftStatus;
  entryIntoServiceDate: string;
  registrationHistory: RegistrationHistoryEntry[];
}

export interface EngineType {
  id: string;
  manufacturer: string;
  modelDesignation: string; // e.g. "CFM56-7B"
}

export interface Engine {
  id: string;
  serialNumber: string;
  engineTypeId: string;
}

export type EnginePosition = "ENGINE_1" | "ENGINE_2" | "ENGINE_3" | "ENGINE_4";

export interface EngineInstallation {
  id: string;
  aircraftId: string;
  engineId: string;
  position: EnginePosition;
  installedAt: string;
  removedAt: string | null;
}

export interface Component {
  id: string;
  partNumber: string;
  description: string;
  manufacturer: string;
  requiresSerialization: boolean;
}

export interface ComponentInstance {
  id: string;
  componentId: string;
  serialNumber: string;
}

// Per ADR-008/CTO-review amendment: typed dual-column parent reference,
// never a single untyped polymorphic FK.
export type ParentAssetType = "AIRCRAFT" | "ENGINE";

export interface ComponentInstallation {
  id: string;
  componentInstanceId: string;
  parentAssetType: ParentAssetType;
  aircraftParentId: string | null;
  engineParentId: string | null;
  position: string;
  installedAt: string;
  removedAt: string | null;
}

export interface RegulatoryAuthority {
  id: string;
  code: string; // FAA, EASA, UK_CAA, DGCA, CASA
  name: string;
}

export type RequirementType = "AD" | "SB" | "REGULATION" | "RULE" | "AMC" | "GM" | "SIB" | "NOTICE" | "OTHER";

export interface RegulatoryDocument {
  id: string;
  regulatoryAuthorityId: string;
  docType: RequirementType;
  docNumber: string;
  title: string;
  revision: string;
  publicationDate: string;
  effectiveDate: string;
  sourceStatus: "DRAFT" | "PUBLISHED" | "SUPERSEDED" | "WITHDRAWN";
}

export interface RegulatoryRequirement {
  id: string;
  regulatoryDocumentId: string;
  requirementType: RequirementType;
  requirementNumber: string;
  description: string;
  effectiveDate: string;
  complianceTime: string;
}

export type ConditionType =
  | "AIRCRAFT_TYPE"
  | "AIRCRAFT_VARIANT"
  | "MSN_RANGE"
  | "ENGINE_TYPE"
  | "COMPONENT_PART"
  | "REGISTRATION"
  | "MODIFICATION_EXCLUSION"
  | "AND"
  | "OR"
  | "NOT";

export interface ApplicabilityCondition {
  id: string;
  conditionType: ConditionType;
  label: string; // human-readable summary, e.g. "Aircraft Type = Boeing 737-800"
  parameters?: Record<string, string | number>;
  children?: ApplicabilityCondition[]; // only for AND/OR/NOT combinators
}

export interface ApplicabilityRule {
  id: string;
  regulatoryRequirementId: string;
  ruleVersion: string;
  description: string;
  rootCondition: ApplicabilityCondition;
}

// One evaluated leaf/node result, used to render the decision visualizer.
export interface ConditionEvaluation {
  conditionId: string;
  conditionType: ConditionType;
  label: string;
  expected: string;
  actual: string | null;
  result: ConditionResult;
  evidenceIds: string[];
  note?: string;
}

export type EvidenceType =
  | "MAINTENANCE_RECORD"
  | "OEM_DOCUMENT"
  | "INSPECTION_RECORD"
  | "UPLOADED_DOCUMENT"
  | "STRUCTURED_RECORD_REFERENCE"
  | "REGULATORY_DOCUMENT";

export interface Evidence {
  id: string;
  applicabilityAssessmentId: string;
  evidenceType: EvidenceType;
  description: string;
  sourceLabel: string; // e.g. filename, or "Maintenance Record MR-2026-00481"
  structuredRecordId: string | null;
  uploadedOrReferencedAt: string;
  verificationStatus: "VERIFIED" | "UNVERIFIED";
  relatedConditionIds: string[];
  // M8.4 — optional cross-links into the broader traceability chain, added
  // without changing the meaning of the fields above (every existing
  // consumer of Evidence keeps working unchanged). Only present when a
  // record actually links there; absent/null means "not linked", not
  // "linked to nothing" and never "compliant by default".
  uploadedBy?: string | null; // user id
  linkedWorkOrderId?: string | null;
  linkedPartId?: string | null;
}

// M8.4 — richer evidence lifecycle vocabulary for future ingestion
// workflows (upload -> processing -> verified/rejected). Deliberately kept
// separate from Evidence.verificationStatus above rather than replacing it,
// since verificationStatus is already load-bearing across the compliance,
// pre-audit, and report surfaces — this is additive, not a breaking rename.
export type EvidenceLifecycleState = "UPLOADED" | "PROCESSING" | "VERIFIED" | "REJECTED" | "UNKNOWN";

export function evidenceLifecycleStateFor(e: Evidence): EvidenceLifecycleState {
  return e.verificationStatus === "VERIFIED" ? "VERIFIED" : "UNKNOWN";
}

export type AssessmentSubjectType = "AIRCRAFT" | "ENGINE";

export interface ConfigurationSnapshot {
  capturedAt: string;
  aircraftVariant: string;
  msn: string;
  registration: string;
  engines: { position: string; engineType: string; serialNumber: string }[];
  components: { position: string; partNumber: string; serialNumber: string }[];
  dataVersion: string;
}

export interface ApplicabilityAssessment {
  id: string;
  regulatoryRequirementId: string;
  applicabilityRuleId: string;
  subjectType: AssessmentSubjectType;
  subjectId: string; // aircraft id or engine id, per subjectType
  previousAssessmentId: string | null;
  systemResult: SystemResult;
  confidence: number;
  conditionEvaluations: ConditionEvaluation[];
  ruleVersion: string;
  regulatoryDocumentVersion: string;
  configurationSnapshot: ConfigurationSnapshot;
  evaluatedAt: string;
  humanDecision: HumanDecision;
  humanDecisionBy: string | null;
  humanDecisionByRole: string | null;
  humanDecisionAt: string | null;
  overrideReason: string | null;
  finalStatus: FinalStatus;
  changeReason:
    | "REGULATORY_REVISION"
    | "CONFIG_CHANGE"
    | "COMPONENT_CHANGE"
    | "RULE_CHANGE"
    | "NEW_EVIDENCE"
    | "DATA_CORRECTION"
    | null;
  evidenceIds: string[];
}

// Compliance-oriented maintenance event — deliberately NOT a work-order/CMMS
// entity (no costing, scheduling engine, task cards, or sign-off workflow;
// see docs/ontology/M1_SCOPE.md's explicit MaintenanceRecord scope boundary).
export type MaintenanceEventType = "INSPECTION" | "REMOVAL" | "INSTALLATION" | "REPAIR" | "OVERHAUL" | "REPLACEMENT";
export type MaintenanceEventStatus = "SCHEDULED" | "IN_PROGRESS" | "COMPLETED" | "OVERDUE" | "AWAITING_EVIDENCE" | "AWAITING_REVIEW";
export type MaintenanceSubjectType = "AIRCRAFT" | "ENGINE" | "COMPONENT_INSTANCE";

export interface MaintenanceEvent {
  id: string;
  eventType: MaintenanceEventType;
  status: MaintenanceEventStatus;
  subjectType: MaintenanceSubjectType;
  aircraftId: string; // the aircraft this event is ultimately about, even if subjectType is ENGINE/COMPONENT_INSTANCE
  engineId: string | null;
  componentInstanceId: string | null;
  description: string;
  date: string; // scheduled or completed date, depending on status
  relatedRequirementId: string | null;
  relatedAssessmentId: string | null;
}

// --- MRO operations layer (compliance-connected, not a disconnected module) ---

export type MaintenanceProjectType = "C_CHECK" | "A_CHECK" | "D_CHECK" | "UNSCHEDULED" | "MODIFICATION";
export type MaintenanceProjectStatus = "PLANNED" | "IN_PROGRESS" | "ON_HOLD" | "COMPLETED" | "CANCELLED";
export type Priority = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export type WorkPackageStatus = "NOT_STARTED" | "IN_PROGRESS" | "BLOCKED" | "READY_FOR_INSPECTION" | "COMPLETED";

export interface WorkPackage {
  id: string;
  projectId: string;
  aircraftId: string;
  title: string;
  description: string;
  ataChapter: string; // e.g. "72" (Engine)
  status: WorkPackageStatus;
  completionPercent: number;
  dueDate: string;
  assignedTechnicianId: string | null;
  inspectorId: string | null;
  requiredPartIds: string[];
  requiredTools: string[];
  complianceReference: string | null; // free-text reference, e.g. an AD/SB number
}

export interface MaintenanceProject {
  id: string;
  projectNumber: string; // e.g. "PRJ-2026-001"
  title: string; // e.g. "VT-ABC — C-Check"
  aircraftId: string;
  projectType: MaintenanceProjectType;
  status: MaintenanceProjectStatus;
  priority: Priority;
  projectManager: string;
  leadTechnicianId: string | null;
  startDate: string; // planned start
  targetCompletionDate: string; // planned completion
  actualStartDate: string | null;
  actualCompletionDate: string | null;
  progressPercent: number;
  workPackageIds: string[];
  riskNotes: string[];
}

// DRAFT -> ASSIGNED -> IN_PROGRESS -> (WAITING_PARTS / WAITING_INSPECTION) -> COMPLETED, or CANCELLED at any point.
export type WorkOrderStatus = "DRAFT" | "ASSIGNED" | "IN_PROGRESS" | "WAITING_PARTS" | "WAITING_INSPECTION" | "COMPLETED" | "CANCELLED";
export type MaintenanceType = "INSPECTION" | "REPAIR" | "REPLACEMENT" | "MODIFICATION" | "SCHEDULED";

export interface Technician {
  id: string;
  name: string;
  role: string;
  shiftStart: string; // "06:00"
  shiftEnd: string; // "14:00"
  certifications: string[];
  isInspector?: boolean;
}

export type PartStatus = "IN_STOCK" | "ORDERED" | "AWAITING_RECEIPT";
export type PartClassification = "BATCH" | "SERIALIZED";

export interface Part {
  id: string;
  partNumber: string;
  serialNumber: string | null; // null for batch-tracked parts — see ADR-009
  description: string;
  classification: PartClassification;
  status: PartStatus;
  quantity: number;
  location: string; // e.g. "Stores — Bay 3"
  installedAircraftId: string | null;
  installedComponentInstanceId: string | null; // -> ComponentInstance, when this part IS an installed component
  workOrderId: string | null; // work order this part is reserved/required for
  lifeLimitInfo: string | null; // e.g. "12,000 cycles life limit — not applicable to this part"
  manufacturer: string | null; // UNKNOWN when not recorded — see ADR-009
  batchOrLot: string | null; // batch/lot number for BATCH-classified parts; null when not applicable or unrecorded
}

// M7.1 — Aviation Parts Traceability Model. These entities extend (not
// replace) the existing Part record above. Every record here references a
// real Part/Aircraft/WorkOrder id already present in the mock dataset — no
// fabricated aircraft, work orders, or certificate numbers. Where source
// data would not exist for a given part in real operation (e.g. a part
// still on order has not been received), NO record is seeded rather than
// inventing one — see lib/mock/partTraceability.ts helper functions for how
// callers must treat an absent record (as "Insufficient source data.", not
// as a negative/failing determination).

export type CertificateType = "FAA_8130_3" | "EASA_FORM_1" | "OTHER" | "UNKNOWN";

// Distinguishes "no certificate record was ever produced or is required"
// from "a certificate should exist but has not been confirmed present" —
// these are NOT interchangeable and must never be collapsed into a single
// compliant/non-compliant flag.
export type CertificateVerificationStatus =
  | "PRESENT" // certificate reference recorded and on file
  | "MISSING" // certificate expected/required but not on file
  | "REFERENCE_UNKNOWN" // a certificate is believed to exist but its reference/details are not recorded
  | "NOT_VERIFIED"; // a certificate reference is on file but has not been checked against the issuing authority

export type TraceabilityStatus = "TRACEABLE" | "PARTIAL" | "UNKNOWN";

export interface PartReceivingRecord {
  id: string;
  partId: string;
  receivedDate: string; // ISO date
  receivedBy: string; // technician/user id
  source: string; // supplier/vendor name (demo data)
  quantityReceived: number;
}

export interface PartCertificate {
  id: string;
  partId: string;
  certificateType: CertificateType;
  certificateReference: string | null; // clearly-marked demo reference, e.g. "8130-3-DEMO-0042"; null when unrecorded
  certificateIssuer: string | null;
  certificateDate: string | null; // ISO date
  verificationStatus: CertificateVerificationStatus;
}

export interface PartInstallation {
  id: string;
  partId: string;
  aircraftId: string;
  componentInstanceId: string | null; // -> ComponentInstance, when applicable
  workOrderId: string | null;
  installationDate: string; // ISO date
  installedBy: string; // technician id
}

export interface PartRemoval {
  id: string;
  partId: string;
  aircraftId: string;
  workOrderId: string | null;
  removalDate: string; // ISO date
  removedBy: string; // technician id
  reason: string;
}

export interface Finding {
  id: string;
  workOrderId: string;
  checklistItemId: string | null;
  description: string;
  severity: Priority;
  requiresDefect: boolean;
}

export interface TechnicianSignOff {
  technicianId: string;
  timestamp: string;
  confirmed: boolean;
}

export type InspectorReviewStatus = "PENDING_INSPECTION" | "APPROVED" | "REJECTED" | "RETURNED_FOR_CORRECTION";

export interface InspectorReview {
  id: string;
  workOrderId: string;
  inspectorId: string;
  status: InspectorReviewStatus;
  comments: string;
  reviewedAt: string | null;
}

export interface WorkOrder {
  id: string;
  workOrderNumber: string; // "WO-1042"
  projectId: string | null;
  workPackageId: string | null;
  aircraftId: string;
  title: string;
  ataChapter: string;
  maintenanceType: MaintenanceType;
  priority: Priority;
  assignedTechnicianId: string | null;
  inspectorId: string | null;
  plannedStartDate: string;
  dueDate: string;
  completionDate: string | null;
  status: WorkOrderStatus;
  requiredPartIds: string[];
  requiredTools: string[];
  relatedRequirementId: string | null; // -> RegulatoryRequirement
  relatedAssessmentId: string | null; // -> ApplicabilityAssessment
  checklistId: string | null;
  findingIds: string[];
  signOff: TechnicianSignOff | null;
  inspectorReviewId: string | null; // -> InspectorReview
}

// Checklist item DEFINITION (static template data). Runtime completion state
// (result/actualValue/note/evidenceAttached) lives in ChecklistPanel's local
// React state only — never persisted, per the M0.5 prototype's Human Review
// pattern (see docs/adr/ADR-005).
export interface ChecklistItem {
  id: string;
  label: string;
  instruction: string;
  acceptanceCriteria: string;
  requiresMeasurement: boolean;
  unit: string | null;
  minLimit: number | null;
  maxLimit: number | null;
  findingRequiredOnFail: boolean;
  evidenceRequired: boolean;
}

// Three-valued-plus-NA result for one checklist item at runtime. Mirrors the
// ConditionResult pattern used for applicability conditions: UNKNOWN is a
// distinct, first-class outcome, never silently coerced to PASS or FAIL.
export type ChecklistItemResult = "PASS" | "FAIL" | "NOT_APPLICABLE" | "UNKNOWN";

export interface Checklist {
  id: string;
  workOrderId: string;
  title: string;
  requiredReference: string;
  requiredTools: string[];
  requiredParts: string[];
  requiredEvidence: string;
  acceptanceCriteria: string;
  items: ChecklistItem[];
}

export type DefectSeverity = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type DefectStatus = "OPEN" | "DEFERRED" | "RESOLVED";

export interface Defect {
  id: string;
  aircraftId: string;
  workOrderId: string | null;
  componentInstanceId: string | null;
  ataChapter: string;
  description: string;
  severity: DefectSeverity;
  status: DefectStatus;
  discoveredBy: string;
  reportedDate: string;
  correctiveAction: string | null;
  inspectorDecision: string | null;
}

export interface AuditEvent {
  id: string;
  timestamp: string;
  actor: string;
  actorRole: string;
  action: string;
  objectType: string;
  objectLabel: string;
  previousState: string | null;
  newState: string | null;
  reason?: string;
  relatedAssessmentId?: string;
  // M8.8 — optional, additive: not every seeded event has these, and
  // existing events remain valid without them.
  actorType?: "USER" | "AI" | "SYSTEM";
  organizationId?: string;
}

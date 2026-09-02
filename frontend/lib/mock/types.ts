// KOTA Aerospace OS M0.5 prototype — mock domain types.
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
  // M12.9 — aviation-native aircraft foundation. Optional/nullable because
  // this prototype has no flight-data ingestion (ACMS, etc.): most aircraft
  // legitimately have no recorded value here. Absent/null must render
  // "Insufficient source data.", never 0 or an inferred number.
  flightHours?: number | null;
  flightCycles?: number | null;
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

// M10.1 — MRO Financial Intelligence domain model. Additive only; nothing
// here changes an existing type. No Vendor, Customer, or rate-card entity
// exists elsewhere in the domain model, so these are the first cost-facing
// types in the repository. Every record is either "DEMO_SEED" (a small,
// clearly-marked set of illustrative values on real, existing work orders —
// see lib/mock/finance.ts for exactly which ones and why) or absent
// entirely; there is no "SYSTEM_CALCULATED" cost ingestion pipeline in this
// prototype; the arithmetic in finance.ts is calculated fresh from these
// seed records rather than a third status implying a live feed that
// doesn't exist.
export type CostSource = "DEMO_SEED";

export interface LaborCost {
  id: string;
  workOrderId: string;
  taskId: string | null; // checklist item id, when the labor is scoped to one
  technicianId: string;
  hours: number;
  hourlyRate: number;
  currency: string;
  amount: number; // hours * hourlyRate, stored explicitly rather than re-derived silently
  source: CostSource;
}

export interface PartCost {
  id: string;
  workOrderId: string;
  partId: string;
  quantity: number;
  unitCost: number;
  currency: string;
  amount: number;
  vendorName: string | null; // no Vendor entity exists yet (see M11 procurement) — inline label only
  source: CostSource;
}

export interface VendorCost {
  id: string;
  workOrderId: string;
  vendorName: string;
  description: string;
  amount: number;
  currency: string;
  date: string;
  source: CostSource;
}

export interface CustomerCharge {
  id: string;
  workOrderId: string;
  customerOrgId: string; // -> Organization (the aircraft's operatorOrgId)
  laborCharge: number;
  partsCharge: number;
  otherCharge: number;
  totalCharge: number;
  currency: string;
  source: CostSource;
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
  // M12.9 — authorization-aware assignment foundation. `licenseType` reuses
  // the same B1.1/B2 category labels already present as plain strings inside
  // `certifications` above (never a second, disagreeing source); it is a
  // structured pointer to that existing signal, not new fabricated data.
  // `aircraftTypeQualifications` is null/absent, never guessed, because this
  // dataset has no type-rating record for any technician — the system must
  // say "system qualification data indicates a match" (keyword-derived),
  // never "technician is legally authorized" (see lib/mock/ai/engine.ts).
  licenseType?: string | null;
  aircraftTypeQualifications?: string[] | null;
}

export type PartStatus = "IN_STOCK" | "ORDERED" | "AWAITING_RECEIPT";
export type PartClassification = "BATCH" | "SERIALIZED";

// M12.9 — aviation parts foundation. Additive to, not a replacement for, the
// existing BATCH/SERIALIZED `classification` above (that field already drives
// UI/logic elsewhere and stays exactly as-is). These describe two different
// things: `classification` = how the part is tracked; `aviationClassification`
// = its real-world rotable/consumable nature; `serviceability` = its current
// condition state. All optional — this is a foundation, not a rebuilt part
// record, and unrecorded is UNKNOWN, never a guessed default.
export type PartAviationClassification = "CONSUMABLE" | "EXPENDABLE" | "ROTABLE" | "REPAIRABLE";
export type PartServiceability = "SERVICEABLE" | "UNSERVICEABLE" | "QUARANTINED" | "RECEIVING_INSPECTION" | "UNKNOWN";

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
  aviationClassification?: PartAviationClassification | null;
  serviceability?: PartServiceability;
  // M13 — only meaningful when serviceability is QUARANTINED; null otherwise.
  quarantineReason?: string | null;
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
  // M12.9 — optional link to a MaintenanceTask (lib/mock/maintenanceTasks.ts),
  // the aviation-native "what procedure/reference is this work order actually
  // performing" layer. Additive/optional: most existing work orders predate
  // this concept and legitimately have no linked task (null, not fabricated).
  maintenanceTaskId?: string | null;
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
  // M12.9 — structured reason code alongside the existing free-text `reason`
  // above (kept, not replaced), preparing for future tamper-evident records
  // without implementing any cryptographic/ledger mechanism here.
  reasonCode?: string;
}

// M12.9 — ASAL (Aviation Safety & Airworthiness Layer) foundation types.
// Additive only: nothing existing is renamed or removed. See
// lib/mock/maintenanceTasks.ts for seed data and lib/mock/ai/analytics.ts
// for the derivation functions that use these.

export type MaintenanceTaskReferenceType = "AMM" | "SB" | "AD" | "MPD" | "OTHER";

// Distinguishes "a source reference is recorded" from "no authoritative
// source is available in this dataset" — the latter must render as
// "Insufficient source data.", never as a fabricated AMM/IPC procedure.
export type MaintenanceTaskEvidenceStatus = "SOURCE_AVAILABLE" | "SOURCE_UNKNOWN";

export interface MaintenanceTask {
  id: string;
  description: string;
  ataChapter: string;
  referenceType: MaintenanceTaskReferenceType;
  referenceId: string | null; // -> RegulatoryRequirement id when referenceType is AD/SB and one genuinely exists; otherwise null
  requiredSkill: string | null; // free-text skill label, matched the same keyword-overlap way as WorkOrder.title already is — not a certification database
  inspectionRequired: boolean;
  evidenceStatus: MaintenanceTaskEvidenceStatus;
}

// Execution/release state — deliberately separate from WorkOrderStatus.
// COMPLETED (an existing WorkOrderStatus value) means "the technician's
// work step is done"; it must never be read as "the aircraft is released."
// This type exists purely to make that distinction explicit and derivable;
// it does not replace or remove WorkOrderStatus.
export type ExecutionState =
  | "NOT_STARTED"
  | "IN_PROGRESS"
  | "TECHNICIAN_COMPLETED"
  | "INSPECTION_REQUIRED"
  | "INSPECTION_COMPLETED"
  | "READY_FOR_RELEASE"
  | "RELEASED"
  // M13 — a work order can be blocked before/without ever starting (material
  // or qualification gate open while status is DRAFT/ASSIGNED/WAITING_PARTS)
  // — distinct from NOT_STARTED, which implies "could start, just hasn't".
  | "BLOCKED";

export type SafetyGateType = "MATERIAL_GATE" | "QUALIFICATION_GATE" | "INSPECTION_GATE" | "EVIDENCE_GATE" | "RELEASE_GATE";

// M13 — four-valued gate state, additive alongside the existing `open`
// boolean (unchanged, still what the M12.9 UI/Lisa branches read). PASS/FAIL
// are true opposites; UNKNOWN is a THIRD, distinct outcome for "no source
// record exists to evaluate this gate at all" — it must never be treated as
// PASS. NOT_REQUIRED is for a gate that structurally doesn't apply (e.g. no
// inspection required for this task).
export type SafetyGateState = "PASS" | "FAIL" | "UNKNOWN" | "NOT_REQUIRED";

export interface SafetyGate {
  type: SafetyGateType;
  open: boolean; // true = this gate is currently blocking release/progress
  reason: string;
  state: SafetyGateState;
}

// M13 — MEL/deferred-item foundation. Category A-D is the real ATA/MEL
// vocabulary; UNKNOWN is used, never a fabricated category or countdown,
// when this dataset has no authoritative MEL reference for a deferred
// defect (see lib/mock/deferredItems.ts).
export type DeferredItemCategory = "A" | "B" | "C" | "D" | "UNKNOWN";
export type DeferredItemStatus = "OPEN" | "CLOSED";

export interface DeferredItem {
  id: string;
  aircraftId: string;
  defectId: string;
  melReference: string | null;
  category: DeferredItemCategory;
  openedAt: string;
  dueAt: string | null; // null = UNKNOWN, never a guessed deadline
  status: DeferredItemStatus;
}

// M13 — cannibalization foundation. A candidate only; Lisa/the system may
// surface one for human review but never authorizes it (authorizationStatus
// starts and stays PENDING_HUMAN_REVIEW in this prototype — there is no
// approval mutation).
export type CannibalizationAuthorizationStatus = "PENDING_HUMAN_REVIEW" | "AUTHORIZED" | "REJECTED";
export type CannibalizationTraceabilityStatus = "TRACEABLE" | "UNKNOWN";

export interface CannibalizationRequest {
  id: string;
  sourceAircraftId: string | null; // null = no candidate donor identified
  targetAircraftId: string;
  partId: string;
  reason: string;
  authorizationStatus: CannibalizationAuthorizationStatus;
  removalStatus: "NOT_STARTED" | "REMOVED";
  installationStatus: "NOT_STARTED" | "INSTALLED";
  traceabilityStatus: CannibalizationTraceabilityStatus;
  createdAt: string;
}

// M13 — signature-record shape, DERIVED (never a second stored record) from
// the existing TechnicianSignOff/InspectorReview fields that already carry
// this information (see getSignatureRecordsForWorkOrder in
// lib/mock/ai/analytics.ts). This is a prototype compliance-ready
// foundation only — it is NOT a claim of FAA/EASA/Part 11 electronic
// signature compliance.
// M14.2 — Automation Queue foundation. Every item is DERIVED (recomputed
// from existing analytics on each read, never persisted) — this is a
// human-approval action queue, not an autonomous automation engine. There
// is no mutation anywhere that changes `AutomationQueueCategory` state on
// its own; `approvalRequired` is always true.
export type AutomationQueueCategory =
  | "MATERIAL_BLOCKER"
  | "TECHNICIAN_RECOMMENDATION"
  | "AOG_ESCALATION"
  | "RII_INSPECTOR_RECOMMENDATION"
  | "QUARANTINE_REVIEW"
  | "DEFERRED_ITEM_REVIEW"
  | "CANNIBALIZATION_REVIEW"
  | "SAFETY_GATE_FAILURE"
  | "MISSING_EVIDENCE"
  | "RELEASE_PACKAGE_INCOMPLETE";

export interface AutomationQueueItem {
  id: string;
  category: AutomationQueueCategory;
  title: string;
  detection: string; // what triggered this item
  source: string; // e.g. "WO-1055", "Part FCU-220"
  impact: string;
  recommendedAction: string;
  responsibleRole: string;
  approvalRequired: true;
  destinationHref: string; // existing workflow this item routes to
}

export interface SignatureRecord {
  id: string;
  userId: string;
  action: "TECHNICIAN_SIGN_OFF" | "INSPECTOR_REVIEW";
  recordType: "WorkOrder";
  recordId: string;
  timestamp: string;
  authenticationMethod: "PROTOTYPE_SESSION"; // no real auth/identity provider exists in this prototype
  signatureIntent: string;
  reasonCode: string | null;
}

// M11.0 — Procurement / Vendor domain model. Additive only. Before this,
// "vendor" existed only as a bare string (VendorCost.vendorName in
// finance.ts, PartReceivingRecord.source in partTraceability.ts) — this is
// the first real Vendor entity. Every optional field below is genuinely
// optional: most vendors will NOT have every field populated, and callers
// must render "Insufficient source data." rather than assuming NONE/UNKNOWN
// defaults mean anything negative.

export type VendorApprovalStatus = "APPROVED" | "PENDING" | "SUSPENDED" | "NOT_APPROVED" | "UNKNOWN";
export type VendorQualityStatus = "VERIFIED" | "UNDER_REVIEW" | "ISSUES_OPEN" | "UNKNOWN";
export type VendorRelationshipStatus = "PREFERRED" | "APPROVED" | "NEW" | "UNKNOWN";

export interface Vendor {
  id: string;
  name: string;
  legalName: string | null;
  vendorCode: string | null;
  country: string | null;
  city: string | null;
  contactName: string | null;
  email: string | null;
  phone: string | null;
  website: string | null;
  status: "ACTIVE" | "INACTIVE";
  approvalStatus: VendorApprovalStatus;
  qualityStatus: VendorQualityStatus;
  approvedForAircraftTypes: string[] | null; // null = not recorded, [] = recorded as none
  suppliedPartCategories: string[] | null;
  capabilities: string[] | null;
  certifications: string[] | null; // e.g. "AS9120", "ISO 9001" — demo-labeled, not verified against a real registry
  paymentTerms: string | null;
  currency: string | null;
  shippingRegions: string[] | null;
  aogSupport: boolean | null; // null = not recorded
  leadTimeDays: number | null; // typical/quoted lead time, when known
  reliabilityScore: number | null; // 0-100, only when a scoring basis exists
  qualityScore: number | null;
  deliveryScore: number | null;
  relationshipStatus: VendorRelationshipStatus;
  source: CostSource; // reuses the M10 DEMO_SEED marker — see finance.ts
}

export type PartAvailabilityStatus = "IN_STOCK" | "LIMITED" | "OUT_OF_STOCK" | "ON_ORDER" | "UNKNOWN";
export type PartCertificationStatus = "VERIFIED" | "REFERENCE_UNKNOWN" | "NOT_VERIFIED" | "UNKNOWN";

export interface VendorPartAvailability {
  id: string;
  vendorId: string;
  partId: string | null; // -> Part, when the vendor's line maps to an existing part record
  partNumber: string;
  description: string;
  availabilityStatus: PartAvailabilityStatus;
  quantityAvailable: number | null;
  quantityOnOrder: number | null;
  leadTimeDays: number | null;
  unitPrice: number | null;
  currency: string | null;
  moq: number | null;
  aogAvailability: boolean | null;
  certificationStatus: PartCertificationStatus;
  lastUpdated: string | null;
  source: CostSource;
}

export type PartRequestStatus =
  | "DRAFT"
  | "SUBMITTED"
  | "UNDER_REVIEW"
  | "APPROVED"
  | "REJECTED"
  | "CLARIFICATION_REQUIRED"
  | "ORDERED"
  | "RECEIVED"
  | "CLOSED";

export type PartRequestPriority = "ROUTINE" | "HIGH" | "AOG";

export interface PartRequest {
  id: string;
  aircraftId: string;
  workOrderId: string | null;
  taskId: string | null;
  requestedBy: string; // -> UserAccount/Technician id
  requestedAt: string;
  partNumber: string;
  partId: string | null;
  description: string;
  quantity: number;
  priority: PartRequestPriority;
  reason: string;
  requiredBy: string | null;
  preferredVendorId: string | null;
  alternateVendorIds: string[];
  evidenceIds: string[];
  status: PartRequestStatus;
  estimatedCost: number | null;
  selectedVendorId: string | null;
  approvedBy: string | null;
  approvedAt: string | null;
  rejectionReason: string | null;
  clarificationNote: string | null; // M11.5 — set when status is CLARIFICATION_REQUIRED
  source: CostSource;
}

export interface ProcurementCartItem {
  id: string;
  partNumber: string;
  partId: string | null;
  description: string;
  quantity: number;
  aircraftId: string;
  workOrderId: string | null;
  priority: PartRequestPriority;
  justification: string;
  requestedBy: string;
  preferredVendorId: string | null;
  notes: string | null;
}

export type PurchaseOrderStatus = "DRAFT" | "PENDING_APPROVAL" | "APPROVED" | "SENT" | "ACKNOWLEDGED" | "PARTIALLY_RECEIVED" | "RECEIVED" | "CANCELLED";

export interface PurchaseOrderLineItem {
  requestId: string;
  partNumber: string;
  description: string;
  manufacturer: string | null;
  quantity: number;
  unitPrice: number | null;
  currency: string | null;
}

export interface PurchaseOrder {
  id: string;
  poNumber: string;
  vendorId: string;
  requestIds: string[];
  items: PurchaseOrderLineItem[];
  aircraftId: string | null;
  workOrderIds: string[];
  createdBy: string;
  approvedBy: string | null;
  createdAt: string;
  status: PurchaseOrderStatus;
  currency: string;
  subtotal: number;
  tax: number | null;
  shipping: number | null;
  total: number;
  requiredBy: string | null;
  expectedDelivery: string | null; // never fabricated — null unless a vendor has actually committed one
  notes: string | null;
  vendorAcknowledgedAt: string | null;
  sentAt: string | null;
  source: CostSource;
}

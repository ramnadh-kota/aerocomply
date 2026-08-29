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
}

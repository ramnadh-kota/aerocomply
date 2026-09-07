import type { Evidence } from "./types";
import { assessments } from "./assessments";

// MOCK DATA. Evidence is always scoped to exactly one ApplicabilityAssessment
// and has exactly two shapes: an uploaded file, or a reference to an existing
// structured record — never a standalone document library (see
// docs/ontology/AVIATION_ONTOLOGY.md §8).

export const heroEvidence: Evidence[] = [
  {
    id: "ev-1",
    applicabilityAssessmentId: "asmt-1",
    evidenceType: "STRUCTURED_RECORD_REFERENCE",
    description: "Engine installation record confirms CFM56-7B SN 100781 installed at Engine 1 position on VT-ABC.",
    sourceLabel: "Engine Installation Record EI-2026-0211",
    structuredRecordId: "einst-3",
    uploadedOrReferencedAt: "2026-03-12T10:42:00Z",
    verificationStatus: "VERIFIED",
    relatedConditionIds: ["cond-engine-cfm567b"],
  },
  {
    id: "ev-2",
    applicabilityAssessmentId: "asmt-1",
    evidenceType: "UPLOADED_DOCUMENT",
    description: "General maintenance record reviewed during initial assessment.",
    sourceLabel: "maintenance_record_2026_03_10.pdf",
    structuredRecordId: null,
    uploadedOrReferencedAt: "2026-03-12T10:40:00Z",
    verificationStatus: "VERIFIED",
    relatedConditionIds: [],
  },
  {
    id: "ev-3",
    applicabilityAssessmentId: "asmt-2",
    evidenceType: "STRUCTURED_RECORD_REFERENCE",
    description: "Inspection record confirms Fan Disk Assembly ABC-123 (SN ABC902) installed on VT-ABC's Engine 1.",
    sourceLabel: "Maintenance Record MR-2026-00481",
    structuredRecordId: "mr-2026-00481",
    uploadedOrReferencedAt: "2026-03-14T09:10:00Z",
    verificationStatus: "VERIFIED",
    relatedConditionIds: ["cond-component-abc123"],
  },
  {
    id: "ev-4",
    applicabilityAssessmentId: "asmt-2",
    evidenceType: "UPLOADED_DOCUMENT",
    description: "Engineering records review confirms Modification MOD-778 was never embodied on this airframe.",
    sourceLabel: "mod_status_confirmation_2026_03_13.pdf",
    structuredRecordId: null,
    uploadedOrReferencedAt: "2026-03-13T16:20:00Z",
    verificationStatus: "VERIFIED",
    relatedConditionIds: ["cond-mod-778"],
  },
  {
    id: "ev-5",
    applicabilityAssessmentId: "asmt-3",
    evidenceType: "STRUCTURED_RECORD_REFERENCE",
    description: "Aircraft variant record confirms A320-200, outside AD-2026-002's A330-family applicability.",
    sourceLabel: "Aircraft Variant Record — VT-XYZ",
    structuredRecordId: "ac-2",
    uploadedOrReferencedAt: "2026-03-11T08:10:00Z",
    verificationStatus: "VERIFIED",
    relatedConditionIds: ["cond-variant-a330"],
  },
  {
    id: "ev-6",
    applicabilityAssessmentId: "asmt-4",
    evidenceType: "UPLOADED_DOCUMENT",
    description: "Completion record for the avionics software standard update mandated by AD-2026-003.",
    sourceLabel: "avionics_update_completion_2026_01_25.pdf",
    structuredRecordId: null,
    uploadedOrReferencedAt: "2026-01-26T07:50:00Z",
    verificationStatus: "VERIFIED",
    relatedConditionIds: ["cond-variant-738-r3", "cond-msn-35500-36500"],
  },
  {
    id: "ev-7",
    applicabilityAssessmentId: "asmt-1",
    evidenceType: "STRUCTURED_RECORD_REFERENCE",
    description: "Aircraft record confirms MSN 35124 falls within the AD's affected serial range.",
    sourceLabel: "Aircraft Master Record — VT-ABC",
    structuredRecordId: "ac-1",
    uploadedOrReferencedAt: "2026-03-12T10:42:00Z",
    verificationStatus: "VERIFIED",
    relatedConditionIds: ["cond-msn-35000-37000"],
  },
  {
    id: "ev-8",
    applicabilityAssessmentId: "asmt-3",
    evidenceType: "UPLOADED_DOCUMENT",
    description: "CAMO engineer sign-off confirming the not-applicable determination.",
    sourceLabel: "camo_review_ad_2026_002_vt_xyz.pdf",
    structuredRecordId: null,
    uploadedOrReferencedAt: "2026-03-11T08:55:00Z",
    verificationStatus: "VERIFIED",
    relatedConditionIds: [],
  },
  {
    id: "ev-9",
    applicabilityAssessmentId: "asmt-4",
    evidenceType: "STRUCTURED_RECORD_REFERENCE",
    description: "Aircraft record confirms MSN 35980 falls within the affected serial range.",
    sourceLabel: "Aircraft Master Record — VT-DEF",
    structuredRecordId: "ac-5",
    uploadedOrReferencedAt: "2026-01-26T08:00:00Z",
    verificationStatus: "VERIFIED",
    relatedConditionIds: ["cond-msn-35500-36500"],
  },
];

const bulkEvidence: Evidence[] = assessments
  .filter((a) => a.id.startsWith("asmt-bulk-"))
  .map((a) => ({
    id: a.evidenceIds[0],
    applicabilityAssessmentId: a.id,
    evidenceType: "STRUCTURED_RECORD_REFERENCE" as const,
    description: `Aircraft configuration record supporting the ${a.systemResult === "APPLICABLE" ? "applicability" : "non-applicability"} determination.`,
    sourceLabel: `Aircraft Master Record — ${a.subjectId}`,
    structuredRecordId: a.subjectId,
    uploadedOrReferencedAt: a.evaluatedAt,
    verificationStatus: "VERIFIED" as const,
    relatedConditionIds: a.conditionEvaluations.map((c) => c.conditionId),
  }));

export const evidence: Evidence[] = [...heroEvidence, ...bulkEvidence];

export function getEvidenceById(id: string): Evidence | undefined {
  return evidence.find((e) => e.id === id);
}

export function evidenceForAssessment(assessmentId: string): Evidence[] {
  return evidence.filter((e) => e.applicabilityAssessmentId === assessmentId);
}

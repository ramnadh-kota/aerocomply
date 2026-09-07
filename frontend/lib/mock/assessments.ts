import type { ApplicabilityAssessment, ConditionEvaluation, ConfigurationSnapshot } from "./types";
import { aircraft, getAircraftVariant, registrationAsOf } from "./aircraft";
import { engineInstallations, getEngineById, getEngineType } from "./engines";
import { componentForInstance, componentInstallationsForAircraft } from "./components";

// MOCK DATA — hand-authored "hero" assessments demonstrate the four required
// demo scenarios (docs section 30): A compliant, B not-applicable, C unknown,
// D reassessment. Remaining assessments are generated for volume/realism.

function buildSnapshot(aircraftId: string, isoDate: string, dataVersion: string): ConfigurationSnapshot {
  const a = aircraft.find((x) => x.id === aircraftId)!;
  const variant = getAircraftVariant(a.aircraftVariantId)!;
  const registration = registrationAsOf(a, isoDate) ?? "UNKNOWN";
  // As-of lookup (not "current") — a configuration snapshot must reflect the
  // installed engine at the evaluation timestamp, not today's engine, per
  // docs/ontology/TEMPORAL_MODEL.md.
  const engineInstalls = engineInstallations.filter(
    (i) => i.aircraftId === aircraftId && i.installedAt <= isoDate && (i.removedAt === null || i.removedAt > isoDate)
  );
  const componentInstalls = componentInstallationsForAircraft(aircraftId).filter(
    (i) => i.installedAt <= isoDate && (i.removedAt === null || i.removedAt > isoDate)
  );
  return {
    capturedAt: isoDate,
    aircraftVariant: variant.modelDesignation,
    msn: a.msn,
    registration,
    engines: engineInstalls.map((ei) => {
      const engine = getEngineById(ei.engineId)!;
      const type = getEngineType(engine.engineTypeId)!;
      return { position: ei.position, engineType: type.modelDesignation, serialNumber: engine.serialNumber };
    }),
    components: componentInstalls.map((ci) => {
      const component = componentForInstance(ci.componentInstanceId);
      const instance = component ? { partNumber: component.partNumber } : { partNumber: "UNKNOWN" };
      return { position: ci.position, partNumber: instance.partNumber, serialNumber: ci.componentInstanceId };
    }),
    dataVersion,
  };
}

// --- Assessment #1: VT-ABC / AD-2026-001 — initial evaluation, INSUFFICIENT_DATA (Scenario C) ---
const asmt1Evaluations: ConditionEvaluation[] = [
  { conditionId: "cond-variant-738", conditionType: "AIRCRAFT_VARIANT", label: "Aircraft Variant = Boeing 737-800", expected: "737-800", actual: "737-800", result: "TRUE", evidenceIds: [] },
  { conditionId: "cond-msn-35000-37000", conditionType: "MSN_RANGE", label: "MSN between 35000–37000", expected: "35000–37000", actual: "35124", result: "TRUE", evidenceIds: [] },
  { conditionId: "cond-engine-cfm567b", conditionType: "ENGINE_TYPE", label: "Engine Type = CFM56-7B", expected: "CFM56-7B", actual: "CFM56-7B (SN 100781, Engine 1)", result: "TRUE", evidenceIds: ["ev-1"] },
  { conditionId: "cond-component-abc123", conditionType: "COMPONENT_PART", label: "Component P/N = ABC-123 installed", expected: "Installed", actual: null, result: "UNKNOWN", evidenceIds: [], note: "No installation record found for ABC-123 on VT-ABC. Absence is not confirmed — evidence has simply not been provided yet." },
  { conditionId: "cond-mod-778", conditionType: "MODIFICATION_EXCLUSION", label: "Modification MOD-778 embodied?", expected: "Not embodied", actual: null, result: "UNKNOWN", evidenceIds: [], note: "Modification/STC tracking is not yet a structured M1 capability (see docs/ontology/M1_SCOPE.md) — absence cannot be assumed." },
];

// --- Assessment #2: VT-ABC / AD-2026-001 — reassessment after new evidence, APPLICABLE (Scenario D) ---
const asmt2Evaluations: ConditionEvaluation[] = [
  { conditionId: "cond-variant-738", conditionType: "AIRCRAFT_VARIANT", label: "Aircraft Variant = Boeing 737-800", expected: "737-800", actual: "737-800", result: "TRUE", evidenceIds: [] },
  { conditionId: "cond-msn-35000-37000", conditionType: "MSN_RANGE", label: "MSN between 35000–37000", expected: "35000–37000", actual: "35124", result: "TRUE", evidenceIds: [] },
  { conditionId: "cond-engine-cfm567b", conditionType: "ENGINE_TYPE", label: "Engine Type = CFM56-7B", expected: "CFM56-7B", actual: "CFM56-7B (SN 100781, Engine 1)", result: "TRUE", evidenceIds: ["ev-1"] },
  { conditionId: "cond-component-abc123", conditionType: "COMPONENT_PART", label: "Component P/N = ABC-123 installed", expected: "Installed", actual: "ABC-123 (SN ABC902) confirmed installed", result: "TRUE", evidenceIds: ["ev-3"] },
  { conditionId: "cond-mod-778", conditionType: "MODIFICATION_EXCLUSION", label: "Modification MOD-778 embodied?", expected: "Not embodied", actual: "Confirmed not embodied", result: "FALSE", evidenceIds: ["ev-4"] },
];

const asmt3Evaluations: ConditionEvaluation[] = [
  { conditionId: "cond-variant-a330", conditionType: "AIRCRAFT_VARIANT", label: "Aircraft Variant = Airbus A330-200/300", expected: "A330", actual: "A320-200", result: "FALSE", evidenceIds: [] },
];

const asmt4Evaluations: ConditionEvaluation[] = [
  { conditionId: "cond-variant-738-r3", conditionType: "AIRCRAFT_VARIANT", label: "Aircraft Variant = Boeing 737-800", expected: "737-800", actual: "737-800", result: "TRUE", evidenceIds: [] },
  { conditionId: "cond-msn-35500-36500", conditionType: "MSN_RANGE", label: "MSN between 35500–36500", expected: "35500–36500", actual: "35980", result: "TRUE", evidenceIds: [] },
];

export const heroAssessments: ApplicabilityAssessment[] = [
  {
    id: "asmt-1",
    regulatoryRequirementId: "req-ad-2026-001",
    applicabilityRuleId: "rule-ad-2026-001",
    subjectType: "AIRCRAFT",
    subjectId: "ac-1",
    previousAssessmentId: null,
    systemResult: "INSUFFICIENT_DATA",
    confidence: 0.4,
    conditionEvaluations: asmt1Evaluations,
    ruleVersion: "v1.0",
    regulatoryDocumentVersion: "rev. 1",
    configurationSnapshot: buildSnapshot("ac-1", "2026-03-12", "DV-7F31A2"),
    evaluatedAt: "2026-03-12T10:42:00Z",
    humanDecision: "REQUEST_MORE_EVIDENCE",
    humanDecisionBy: "Priya Nair",
    humanDecisionByRole: "Compliance Engineer",
    humanDecisionAt: "2026-03-12T11:05:00Z",
    overrideReason: null,
    finalStatus: "REVIEW_REQUIRED",
    changeReason: null,
    evidenceIds: ["ev-1", "ev-2"],
  },
  {
    id: "asmt-2",
    regulatoryRequirementId: "req-ad-2026-001",
    applicabilityRuleId: "rule-ad-2026-001",
    subjectType: "AIRCRAFT",
    subjectId: "ac-1",
    previousAssessmentId: "asmt-1",
    systemResult: "APPLICABLE",
    confidence: 0.97,
    conditionEvaluations: asmt2Evaluations,
    ruleVersion: "v1.0",
    regulatoryDocumentVersion: "rev. 1",
    configurationSnapshot: buildSnapshot("ac-1", "2026-03-14", "DV-9C42E7"),
    evaluatedAt: "2026-03-14T09:20:00Z",
    humanDecision: "CONFIRMED_APPLICABLE",
    humanDecisionBy: "Priya Nair",
    humanDecisionByRole: "Compliance Engineer",
    humanDecisionAt: "2026-03-14T09:35:00Z",
    overrideReason: null,
    finalStatus: "NON_COMPLIANT",
    changeReason: "NEW_EVIDENCE",
    evidenceIds: ["ev-1", "ev-3", "ev-4"],
  },
  {
    id: "asmt-3",
    regulatoryRequirementId: "req-ad-2026-002",
    applicabilityRuleId: "rule-ad-2026-002",
    subjectType: "AIRCRAFT",
    subjectId: "ac-2",
    previousAssessmentId: null,
    systemResult: "NOT_APPLICABLE",
    confidence: 0.99,
    conditionEvaluations: asmt3Evaluations,
    ruleVersion: "v1.0",
    regulatoryDocumentVersion: "rev. 0",
    configurationSnapshot: buildSnapshot("ac-2", "2026-03-11", "DV-2A88B1"),
    evaluatedAt: "2026-03-11T08:15:00Z",
    humanDecision: "CONFIRMED_NOT_APPLICABLE",
    humanDecisionBy: "Rohan Verma",
    humanDecisionByRole: "CAMO Engineer",
    humanDecisionAt: "2026-03-11T09:00:00Z",
    overrideReason: null,
    finalStatus: "COMPLIANT",
    changeReason: null,
    evidenceIds: ["ev-5"],
  },
  {
    id: "asmt-4",
    regulatoryRequirementId: "req-ad-2026-003",
    applicabilityRuleId: "rule-ad-2026-003",
    subjectType: "AIRCRAFT",
    subjectId: "ac-5",
    previousAssessmentId: null,
    systemResult: "APPLICABLE",
    confidence: 0.98,
    conditionEvaluations: asmt4Evaluations,
    ruleVersion: "v1.0",
    regulatoryDocumentVersion: "rev. 2",
    configurationSnapshot: buildSnapshot("ac-5", "2026-01-26", "DV-11F09D"),
    evaluatedAt: "2026-01-26T08:00:00Z",
    humanDecision: "CONFIRMED_APPLICABLE",
    humanDecisionBy: "Priya Nair",
    humanDecisionByRole: "Compliance Engineer",
    humanDecisionAt: "2026-01-26T08:30:00Z",
    overrideReason: null,
    finalStatus: "COMPLIANT",
    changeReason: null,
    evidenceIds: ["ev-6"],
  },
];

// --- Bulk-generated assessments for fleet-wide volume/realism ---
const bulkPlan: { aircraftId: string; requirementId: string; ruleId: string; result: "APPLICABLE" | "NOT_APPLICABLE"; date: string }[] = [
  { aircraftId: "ac-3", requirementId: "req-ad-2026-001", ruleId: "rule-ad-2026-001", result: "APPLICABLE", date: "2026-03-08" },
  { aircraftId: "ac-4", requirementId: "req-ad-2026-004", ruleId: "rule-ad-2026-003", result: "APPLICABLE", date: "2026-02-02" },
  { aircraftId: "ac-6", requirementId: "req-ad-2026-004", ruleId: "rule-ad-2026-003", result: "NOT_APPLICABLE", date: "2026-02-03" },
  { aircraftId: "ac-7", requirementId: "req-ad-2026-005", ruleId: "rule-ad-2026-003", result: "APPLICABLE", date: "2025-12-21" },
  { aircraftId: "ac-8", requirementId: "req-ad-2026-005", ruleId: "rule-ad-2026-003", result: "NOT_APPLICABLE", date: "2025-12-22" },
  { aircraftId: "ac-9", requirementId: "req-ad-2026-001", ruleId: "rule-ad-2026-001", result: "APPLICABLE", date: "2026-03-09" },
  { aircraftId: "ac-10", requirementId: "req-ad-2026-006", ruleId: "rule-ad-2026-003", result: "APPLICABLE", date: "2026-02-16" },
  { aircraftId: "ac-3", requirementId: "req-ad-2026-005", ruleId: "rule-ad-2026-003", result: "APPLICABLE", date: "2025-12-23" },
  { aircraftId: "ac-4", requirementId: "req-ad-2026-006", ruleId: "rule-ad-2026-003", result: "NOT_APPLICABLE", date: "2026-02-17" },
  { aircraftId: "ac-6", requirementId: "req-ad-2026-002", ruleId: "rule-ad-2026-002", result: "NOT_APPLICABLE", date: "2026-03-07" },
  { aircraftId: "ac-9", requirementId: "req-ad-2026-004", ruleId: "rule-ad-2026-003", result: "APPLICABLE", date: "2026-02-04" },
];

const bulkAssessments: ApplicabilityAssessment[] = bulkPlan.map((p, idx) => {
  const evaluation: ConditionEvaluation = {
    conditionId: `cond-bulk-${idx}`,
    conditionType: "AIRCRAFT_VARIANT",
    label: "Aircraft Variant match",
    expected: "matched variant",
    actual: p.result === "APPLICABLE" ? "matched variant" : "different variant",
    result: p.result === "APPLICABLE" ? "TRUE" : "FALSE",
    evidenceIds: [],
  };
  const evidenceId = `ev-bulk-${idx}`;
  return {
    id: `asmt-bulk-${idx}`,
    regulatoryRequirementId: p.requirementId,
    applicabilityRuleId: p.ruleId,
    subjectType: "AIRCRAFT",
    subjectId: p.aircraftId,
    previousAssessmentId: null,
    systemResult: p.result,
    confidence: p.result === "APPLICABLE" ? 0.95 : 0.97,
    conditionEvaluations: [evaluation],
    ruleVersion: "v1.0",
    regulatoryDocumentVersion: "rev. 0",
    configurationSnapshot: buildSnapshot(p.aircraftId, p.date, `DV-${(1000 + idx).toString(16).toUpperCase()}`),
    evaluatedAt: `${p.date}T08:00:00Z`,
    humanDecision: p.result === "APPLICABLE" ? "CONFIRMED_APPLICABLE" : "CONFIRMED_NOT_APPLICABLE",
    humanDecisionBy: "Rohan Verma",
    humanDecisionByRole: "CAMO Engineer",
    humanDecisionAt: `${p.date}T08:30:00Z`,
    overrideReason: null,
    finalStatus: p.result === "APPLICABLE" ? "NON_COMPLIANT" : "COMPLIANT",
    changeReason: null,
    evidenceIds: [evidenceId],
  };
});

export const assessments: ApplicabilityAssessment[] = [...heroAssessments, ...bulkAssessments];

export function getAssessmentById(id: string): ApplicabilityAssessment | undefined {
  return assessments.find((a) => a.id === id);
}

export function assessmentsForAircraft(aircraftId: string): ApplicabilityAssessment[] {
  return assessments
    .filter((a) => a.subjectType === "AIRCRAFT" && a.subjectId === aircraftId)
    .sort((a, b) => b.evaluatedAt.localeCompare(a.evaluatedAt));
}

export function assessmentsForEngine(engineId: string): ApplicabilityAssessment[] {
  return assessments.filter((a) => a.subjectType === "ENGINE" && a.subjectId === engineId);
}

export function assessmentsForRequirement(requirementId: string): ApplicabilityAssessment[] {
  return assessments.filter((a) => a.regulatoryRequirementId === requirementId);
}

/** Full lineage for an assessment, oldest first, walking previousAssessmentId. */
export function lineageFor(assessmentId: string): ApplicabilityAssessment[] {
  const chain: ApplicabilityAssessment[] = [];
  let current = getAssessmentById(assessmentId);
  while (current) {
    chain.unshift(current);
    current = current.previousAssessmentId ? getAssessmentById(current.previousAssessmentId) : undefined;
  }
  // also include any assessment that supersedes this one
  const next = assessments.find((a) => a.previousAssessmentId === assessmentId);
  if (next) chain.push(next);
  return chain;
}

/** Most recent assessment for an aircraft across ALL requirements (for fleet-list summaries). */
export function latestAssessmentForAircraft(aircraftId: string): ApplicabilityAssessment | undefined {
  return assessmentsForAircraft(aircraftId)[0];
}

export function latestAssessmentForAircraftRequirement(aircraftId: string, requirementId: string): ApplicabilityAssessment | undefined {
  const candidates = assessments.filter((a) => a.subjectId === aircraftId && a.regulatoryRequirementId === requirementId);
  return candidates.sort((a, b) => b.evaluatedAt.localeCompare(a.evaluatedAt))[0];
}

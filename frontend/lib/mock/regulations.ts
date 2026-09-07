import type {
  ApplicabilityCondition,
  ApplicabilityRule,
  RegulatoryAuthority,
  RegulatoryDocument,
  RegulatoryRequirement,
} from "./types";

// MOCK DATA — these are FICTIONAL, DEMO-ONLY regulatory records. They are not
// real, current, or legally binding requirements from any authority. See
// docs/ontology/DOMAIN_GLOSSARY.md for the real-world meaning of AD/SB/AMC/etc.

export const regulatoryAuthorities: RegulatoryAuthority[] = [
  { id: "auth-faa", code: "FAA", name: "Federal Aviation Administration" },
  { id: "auth-easa", code: "EASA", name: "European Union Aviation Safety Agency" },
  { id: "auth-ukcaa", code: "UK_CAA", name: "UK Civil Aviation Authority" },
  { id: "auth-dgca", code: "DGCA", name: "Directorate General of Civil Aviation (India)" },
  { id: "auth-casa", code: "CASA", name: "Civil Aviation Safety Authority (Australia)" },
];

export const regulatoryDocuments: RegulatoryDocument[] = [
  { id: "doc-ad-2026-001", regulatoryAuthorityId: "auth-faa", docType: "AD", docNumber: "AD 2026-001", title: "Engine Fan Disk Inspection", revision: "1", publicationDate: "2026-02-20", effectiveDate: "2026-03-01", sourceStatus: "PUBLISHED" },
  { id: "doc-ad-2026-002", regulatoryAuthorityId: "auth-easa", docType: "AD", docNumber: "AD 2026-002", title: "Fuel System Inspection", revision: "0", publicationDate: "2026-02-25", effectiveDate: "2026-03-05", sourceStatus: "PUBLISHED" },
  { id: "doc-ad-2026-003", regulatoryAuthorityId: "auth-faa", docType: "AD", docNumber: "AD 2026-003", title: "Avionics Software Standard Update", revision: "2", publicationDate: "2026-01-10", effectiveDate: "2026-01-25", sourceStatus: "PUBLISHED" },
  { id: "doc-ad-2026-004", regulatoryAuthorityId: "auth-easa", docType: "AD", docNumber: "AD 2026-004", title: "Wing Spar Fatigue Inspection", revision: "0", publicationDate: "2026-01-18", effectiveDate: "2026-02-01", sourceStatus: "PUBLISHED" },
  { id: "doc-ad-2026-005", regulatoryAuthorityId: "auth-faa", docType: "AD", docNumber: "AD 2026-005", title: "Cargo Door Latch Mechanism Inspection", revision: "1", publicationDate: "2025-12-05", effectiveDate: "2025-12-20", sourceStatus: "PUBLISHED" },
  { id: "doc-ad-2026-006", regulatoryAuthorityId: "auth-casa", docType: "AD", docNumber: "AD/A320/112", title: "Pitot Tube Heater Functional Check", revision: "0", publicationDate: "2026-02-01", effectiveDate: "2026-02-15", sourceStatus: "PUBLISHED" },
  { id: "doc-ad-2026-007", regulatoryAuthorityId: "auth-ukcaa", docType: "AD", docNumber: "G-AD-2026-014", title: "Adoption of FAA AD 2026-001 — Engine Fan Disk Inspection", revision: "0", publicationDate: "2026-03-02", effectiveDate: "2026-03-10", sourceStatus: "PUBLISHED" },
  { id: "doc-sb-2025-114", regulatoryAuthorityId: "auth-faa", docType: "SB", docNumber: "SB-2025-114", title: "Hydraulic Pump Seal Replacement", revision: "2", publicationDate: "2025-09-12", effectiveDate: "2025-09-12", sourceStatus: "PUBLISHED" },
  { id: "doc-amc-2025-02", regulatoryAuthorityId: "auth-easa", docType: "AMC", docNumber: "AMC 20-2025-02", title: "Acceptable Means of Compliance — Fan Disk Inspection Intervals", revision: "0", publicationDate: "2025-11-01", effectiveDate: "2025-11-01", sourceStatus: "PUBLISHED" },
  { id: "doc-notice-2025-30", regulatoryAuthorityId: "auth-dgca", docType: "NOTICE", docNumber: "CAR-M-NOTICE-30", title: "Mandatory Adoption of FAA AD 2026-001 for Indian Register", revision: "0", publicationDate: "2026-03-05", effectiveDate: "2026-03-10", sourceStatus: "PUBLISHED" },
];

export const regulatoryRequirements: RegulatoryRequirement[] = [
  { id: "req-ad-2026-001", regulatoryDocumentId: "doc-ad-2026-001", requirementType: "AD", requirementNumber: "AD-2026-001", description: "Fictional demo AD requiring one-time ultrasonic inspection of the engine fan disk on affected 737-800 aircraft equipped with CFM56-7B engines within the specified serial range, unless Modification MOD-778 has been embodied.", effectiveDate: "2026-03-01", complianceTime: "Within 90 days of effective date" },
  { id: "req-ad-2026-002", regulatoryDocumentId: "doc-ad-2026-002", requirementType: "AD", requirementNumber: "AD-2026-002", description: "Fictional demo AD requiring inspection of the fuel system boost pump wiring on affected Airbus aircraft. Applicability is limited to Airbus A330-family aircraft and does not extend to A320-family aircraft.", effectiveDate: "2026-03-05", complianceTime: "Before next flight cycle exceeding 500 hours" },
  { id: "req-ad-2026-003", regulatoryDocumentId: "doc-ad-2026-003", requirementType: "AD", requirementNumber: "AD-2026-003", description: "Fictional demo AD mandating an avionics software standard update for affected 737-800 aircraft to correct a flight management computer anomaly.", effectiveDate: "2026-01-25", complianceTime: "Before further flight" },
  { id: "req-ad-2026-004", regulatoryDocumentId: "doc-ad-2026-004", requirementType: "AD", requirementNumber: "AD-2026-004", description: "Fictional demo AD requiring a one-time fatigue inspection of the wing spar on affected A320-200 aircraft beyond a specified cycle threshold.", effectiveDate: "2026-02-01", complianceTime: "Within 1,000 flight cycles" },
  { id: "req-ad-2026-005", regulatoryDocumentId: "doc-ad-2026-005", requirementType: "AD", requirementNumber: "AD-2026-005", description: "Fictional demo AD requiring inspection of the cargo door latch mechanism on affected 737-800 aircraft following field reports of latch wear.", effectiveDate: "2025-12-20", complianceTime: "Within 180 days of effective date" },
  { id: "req-ad-2026-006", regulatoryDocumentId: "doc-ad-2026-006", requirementType: "AD", requirementNumber: "AD/A320/112", description: "Fictional demo AD requiring a functional check of the pitot tube heating element on affected A320-200 aircraft.", effectiveDate: "2026-02-15", complianceTime: "Within 30 days of effective date" },
  { id: "req-ad-2026-007", regulatoryDocumentId: "doc-ad-2026-007", requirementType: "AD", requirementNumber: "G-AD-2026-014", description: "UK CAA adoption of FAA AD 2026-001 for aircraft on the UK register, incorporating the originating AD's applicability and compliance time by reference.", effectiveDate: "2026-03-10", complianceTime: "As specified in FAA AD 2026-001" },
  { id: "req-sb-2025-114", regulatoryDocumentId: "doc-sb-2025-114", requirementType: "SB", requirementNumber: "SB-2025-114", description: "Manufacturer service bulletin recommending hydraulic pump seal replacement at next scheduled maintenance. Not independently mandatory; referenced by AD-2026-001 as an acceptable means of compliance for certain configurations.", effectiveDate: "2025-09-12", complianceTime: "At operator discretion unless mandated by an AD" },
  { id: "req-amc-2025-02", regulatoryDocumentId: "doc-amc-2025-02", requirementType: "AMC", requirementNumber: "AMC 20-2025-02", description: "Non-binding acceptable means of compliance describing one way (not the only way) to satisfy fan disk inspection interval requirements. Operators may use an alternative means of compliance instead.", effectiveDate: "2025-11-01", complianceTime: "Not applicable — non-mandatory guidance material" },
  { id: "req-notice-2025-30", regulatoryDocumentId: "doc-notice-2025-30", requirementType: "NOTICE", requirementNumber: "CAR-M-NOTICE-30", description: "DGCA mandatory notice adopting FAA AD 2026-001 for aircraft on the Indian register, per standard State-of-Registry adoption practice for foreign type-certificated aircraft.", effectiveDate: "2026-03-10", complianceTime: "As specified in FAA AD 2026-001" },
];

// --- AD-2026-001 condition tree — the walkthrough's primary example ---
const modificationExclusion: ApplicabilityCondition = {
  id: "cond-mod-778",
  conditionType: "MODIFICATION_EXCLUSION",
  label: "Modification MOD-778 embodied",
  parameters: { modification: "MOD-778" },
};

const componentCondition: ApplicabilityCondition = {
  id: "cond-component-abc123",
  conditionType: "COMPONENT_PART",
  label: "Component P/N = ABC-123 installed",
  parameters: { partNumber: "ABC-123" },
};

const engineCondition: ApplicabilityCondition = {
  id: "cond-engine-cfm567b",
  conditionType: "ENGINE_TYPE",
  label: "Engine Type = CFM56-7B",
  parameters: { engineType: "CFM56-7B" },
};

const msnRangeCondition: ApplicabilityCondition = {
  id: "cond-msn-35000-37000",
  conditionType: "MSN_RANGE",
  label: "MSN between 35000–37000",
  parameters: { min: 35000, max: 37000 },
};

const variantCondition: ApplicabilityCondition = {
  id: "cond-variant-738",
  conditionType: "AIRCRAFT_VARIANT",
  label: "Aircraft Variant = Boeing 737-800",
  parameters: { variant: "737-800" },
};

const ad2026001Root: ApplicabilityCondition = {
  id: "cond-root-ad-2026-001",
  conditionType: "AND",
  label: "ALL",
  children: [
    variantCondition,
    {
      id: "cond-and-msn-engine-component",
      conditionType: "AND",
      label: "AND",
      children: [msnRangeCondition, engineCondition, componentCondition],
    },
    {
      id: "cond-not-mod-778",
      conditionType: "NOT",
      label: "NOT",
      children: [modificationExclusion],
    },
  ],
};

// --- AD-2026-002 condition tree — a straightforward NOT_APPLICABLE example ---
const ad2026002Root: ApplicabilityCondition = {
  id: "cond-root-ad-2026-002",
  conditionType: "AND",
  label: "ALL",
  children: [
    { id: "cond-variant-a330", conditionType: "AIRCRAFT_VARIANT", label: "Aircraft Variant = Airbus A330-200/300", parameters: { variant: "A330" } },
  ],
};

// --- AD-2026-003 condition tree — a straightforward APPLICABLE/COMPLIANT example ---
const ad2026003Root: ApplicabilityCondition = {
  id: "cond-root-ad-2026-003",
  conditionType: "AND",
  label: "ALL",
  children: [
    { id: "cond-variant-738-r3", conditionType: "AIRCRAFT_VARIANT", label: "Aircraft Variant = Boeing 737-800", parameters: { variant: "737-800" } },
    { id: "cond-msn-35500-36500", conditionType: "MSN_RANGE", label: "MSN between 35500–36500", parameters: { min: 35500, max: 36500 } },
  ],
};

export const applicabilityRules: ApplicabilityRule[] = [
  { id: "rule-ad-2026-001", regulatoryRequirementId: "req-ad-2026-001", ruleVersion: "v1.0", description: "Structured applicability for AD-2026-001.", rootCondition: ad2026001Root },
  { id: "rule-ad-2026-002", regulatoryRequirementId: "req-ad-2026-002", ruleVersion: "v1.0", description: "Structured applicability for AD-2026-002.", rootCondition: ad2026002Root },
  { id: "rule-ad-2026-003", regulatoryRequirementId: "req-ad-2026-003", ruleVersion: "v1.0", description: "Structured applicability for AD-2026-003.", rootCondition: ad2026003Root },
];

export function getRequirementById(id: string): RegulatoryRequirement | undefined {
  return regulatoryRequirements.find((r) => r.id === id);
}

export function getDocumentById(id: string): RegulatoryDocument | undefined {
  return regulatoryDocuments.find((d) => d.id === id);
}

export function getAuthorityById(id: string): RegulatoryAuthority | undefined {
  return regulatoryAuthorities.find((a) => a.id === id);
}

export function getRuleForRequirement(requirementId: string): ApplicabilityRule | undefined {
  return applicabilityRules.find((r) => r.regulatoryRequirementId === requirementId);
}

export function flattenConditions(node: ApplicabilityCondition): ApplicabilityCondition[] {
  const result: ApplicabilityCondition[] = [node];
  for (const child of node.children ?? []) {
    result.push(...flattenConditions(child));
  }
  return result;
}

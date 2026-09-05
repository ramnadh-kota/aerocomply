import type { Checklist } from "./types";

// MOCK DATA. Checklist item DEFINITIONS only (instruction, acceptance
// criteria, measurement bounds). Runtime completion state (result per item,
// actual values, notes, evidence-attached, sign-off, inspector decision) is
// held in the shared MroStateContext (lib/mro-state/), NOT here and NOT in
// any single page's local state — this is what makes the technician's
// submission the same submission the inspector reviews. Still a prototype:
// nothing here or in the context is persisted to a backend.

export const checklists: Checklist[] = [
  {
    id: "chk-1042",
    workOrderId: "wo-1042",
    title: "Inspect Engine Fan Blades",
    requiredReference: "AD-2026-001 rev. 1 / AMC 20-2025-02",
    requiredTools: ["Borescope", "Torque Wrench"],
    requiredParts: [],
    requiredEvidence: "Inspection photographs and blade-root clearance measurements",
    acceptanceCriteria: "No visible cracks on any fan blade; blade-root clearance within CFM56-7B maintenance manual tolerance.",
    items: [
      { id: "i1", label: "Aircraft identified", instruction: "Confirm registration and MSN match the work order.", acceptanceCriteria: "Registration and MSN match VT-ABC / MSN 35124.", requiresMeasurement: false, unit: null, minLimit: null, maxLimit: null, findingRequiredOnFail: false, evidenceRequired: false },
      { id: "i2", label: "Correct maintenance data verified", instruction: "Confirm AD-2026-001 rev. 1 and AMC 20-2025-02 are the current applicable revisions.", acceptanceCriteria: "Revision matches the work order reference.", requiresMeasurement: false, unit: null, minLimit: null, maxLimit: null, findingRequiredOnFail: true, evidenceRequired: false },
      { id: "i3", label: "Required tooling available", instruction: "Confirm borescope and torque wrench are calibrated and available.", acceptanceCriteria: "Calibration sticker current.", requiresMeasurement: false, unit: null, minLimit: null, maxLimit: null, findingRequiredOnFail: false, evidenceRequired: false },
      { id: "i4", label: "PPE confirmed", instruction: "Confirm required personal protective equipment is worn.", acceptanceCriteria: "PPE per task card.", requiresMeasurement: false, unit: null, minLimit: null, maxLimit: null, findingRequiredOnFail: false, evidenceRequired: false },
      { id: "i5", label: "Engine isolated", instruction: "Confirm engine is isolated and tagged out per safety procedure.", acceptanceCriteria: "Isolation tag in place.", requiresMeasurement: false, unit: null, minLimit: null, maxLimit: null, findingRequiredOnFail: true, evidenceRequired: false },
      { id: "i6", label: "Fan blades inspected", instruction: "Perform borescope inspection of all fan blades for cracks or damage.", acceptanceCriteria: "No visible cracks on any blade.", requiresMeasurement: false, unit: null, minLimit: null, maxLimit: null, findingRequiredOnFail: true, evidenceRequired: true },
      { id: "i7", label: "Blade-root clearance measured", instruction: "Measure blade-root clearance per CFM56-7B maintenance manual.", acceptanceCriteria: "Within manual tolerance.", requiresMeasurement: true, unit: "mm", minLimit: 0.2, maxLimit: 0.8, findingRequiredOnFail: true, evidenceRequired: true },
      { id: "i8", label: "Photos attached", instruction: "Attach borescope inspection photographs.", acceptanceCriteria: "At least one photo per blade position inspected.", requiresMeasurement: false, unit: null, minLimit: null, maxLimit: null, findingRequiredOnFail: false, evidenceRequired: true },
      { id: "i9", label: "Findings recorded", instruction: "Record any findings, even if within acceptable limits.", acceptanceCriteria: "Findings field completed or explicitly marked none.", requiresMeasurement: false, unit: null, minLimit: null, maxLimit: null, findingRequiredOnFail: false, evidenceRequired: false },
      { id: "i10", label: "Task completed", instruction: "Confirm all prior steps are complete before sign-off.", acceptanceCriteria: "All items resolved (Pass, Fail, or N/A).", requiresMeasurement: false, unit: null, minLimit: null, maxLimit: null, findingRequiredOnFail: false, evidenceRequired: false },
    ],
  },
  {
    id: "chk-1043",
    workOrderId: "wo-1043",
    title: "Replace Hydraulic Pump Seal",
    requiredReference: "SB-2025-114 rev. 2",
    requiredTools: ["Seal Puller", "Torque Wrench"],
    requiredParts: ["HP-442 Seal Kit"],
    requiredEvidence: "Post-replacement leak check record",
    acceptanceCriteria: "No hydraulic leakage observed after a 10-minute pressurized leak check.",
    items: [
      { id: "i1", label: "Aircraft identified", instruction: "Confirm registration and MSN match the work order.", acceptanceCriteria: "Registration and MSN match VT-ABC / MSN 35124.", requiresMeasurement: false, unit: null, minLimit: null, maxLimit: null, findingRequiredOnFail: false, evidenceRequired: false },
      { id: "i2", label: "Correct maintenance data verified", instruction: "Confirm SB-2025-114 rev. 2 is the current applicable revision.", acceptanceCriteria: "Revision matches the work order reference.", requiresMeasurement: false, unit: null, minLimit: null, maxLimit: null, findingRequiredOnFail: true, evidenceRequired: false },
      { id: "i3", label: "Required parts available", instruction: "Confirm HP-442 seal kit is on hand.", acceptanceCriteria: "Part number and quantity match requirement.", requiresMeasurement: false, unit: null, minLimit: null, maxLimit: null, findingRequiredOnFail: false, evidenceRequired: false },
      { id: "i4", label: "PPE confirmed", instruction: "Confirm required personal protective equipment is worn.", acceptanceCriteria: "PPE per task card.", requiresMeasurement: false, unit: null, minLimit: null, maxLimit: null, findingRequiredOnFail: false, evidenceRequired: false },
      { id: "i5", label: "Hydraulic system depressurized", instruction: "Confirm system is depressurized before opening.", acceptanceCriteria: "Pressure gauge reads zero.", requiresMeasurement: false, unit: null, minLimit: null, maxLimit: null, findingRequiredOnFail: true, evidenceRequired: false },
      { id: "i6", label: "Seal replaced", instruction: "Remove old seal and install new seal kit.", acceptanceCriteria: "New seal correctly seated.", requiresMeasurement: false, unit: null, minLimit: null, maxLimit: null, findingRequiredOnFail: true, evidenceRequired: false },
      { id: "i7", label: "Leak check performed", instruction: "Pressurize system and hold for 10 minutes, observe for leakage.", acceptanceCriteria: "No visible leakage after 10 minutes.", requiresMeasurement: true, unit: "min", minLimit: 10, maxLimit: null, findingRequiredOnFail: true, evidenceRequired: true },
      { id: "i8", label: "Photos attached", instruction: "Attach photos of the completed installation.", acceptanceCriteria: "At least one photo attached.", requiresMeasurement: false, unit: null, minLimit: null, maxLimit: null, findingRequiredOnFail: false, evidenceRequired: true },
      { id: "i9", label: "Findings recorded", instruction: "Record any findings, even if within acceptable limits.", acceptanceCriteria: "Findings field completed or explicitly marked none.", requiresMeasurement: false, unit: null, minLimit: null, maxLimit: null, findingRequiredOnFail: false, evidenceRequired: false },
      { id: "i10", label: "Task completed", instruction: "Confirm all prior steps are complete before sign-off.", acceptanceCriteria: "All items resolved (Pass, Fail, or N/A).", requiresMeasurement: false, unit: null, minLimit: null, maxLimit: null, findingRequiredOnFail: false, evidenceRequired: false },
    ],
  },
  {
    id: "chk-1045",
    workOrderId: "wo-1045",
    title: "Wing Spar Structural Inspection",
    requiredReference: "AD-2026-004 rev. 0",
    requiredTools: ["NDT Kit"],
    requiredParts: [],
    requiredEvidence: "NDT scan images and inspection log",
    acceptanceCriteria: "No fatigue indications exceeding AD-2026-004's structural repair manual limits at any inspected station.",
    items: [
      { id: "s1", label: "Aircraft identified", instruction: "Confirm registration and MSN match the work order.", acceptanceCriteria: "Registration and MSN match N412MX.", requiresMeasurement: false, unit: null, minLimit: null, maxLimit: null, findingRequiredOnFail: false, evidenceRequired: false },
      { id: "s2", label: "NDT equipment calibrated", instruction: "Confirm NDT kit calibration is current.", acceptanceCriteria: "Calibration sticker current.", requiresMeasurement: false, unit: null, minLimit: null, maxLimit: null, findingRequiredOnFail: false, evidenceRequired: false },
      { id: "s3", label: "Wing spar station 340 inspected", instruction: "Perform NDT scan of wing spar at station 340 per AD-2026-004.", acceptanceCriteria: "No fatigue indications exceeding structural repair manual limits.", requiresMeasurement: false, unit: null, minLimit: null, maxLimit: null, findingRequiredOnFail: true, evidenceRequired: true },
      { id: "s4", label: "Findings recorded", instruction: "Record any indications found, even if within limits.", acceptanceCriteria: "Findings field completed or explicitly marked none.", requiresMeasurement: false, unit: null, minLimit: null, maxLimit: null, findingRequiredOnFail: false, evidenceRequired: false },
      { id: "s5", label: "Photos/scans attached", instruction: "Attach NDT scan images.", acceptanceCriteria: "At least one scan image per inspected station.", requiresMeasurement: false, unit: null, minLimit: null, maxLimit: null, findingRequiredOnFail: false, evidenceRequired: true },
      { id: "s6", label: "Task completed", instruction: "Confirm all prior steps are complete before sign-off.", acceptanceCriteria: "All items resolved (Pass, Fail, or N/A).", requiresMeasurement: false, unit: null, minLimit: null, maxLimit: null, findingRequiredOnFail: false, evidenceRequired: false },
    ],
  },
  {
    id: "chk-1048",
    workOrderId: "wo-1048",
    title: "Fan Disk Ultrasonic Inspection Sign-off",
    requiredReference: "AD-2026-001 rev. 1",
    requiredTools: ["Borescope"],
    requiredParts: [],
    requiredEvidence: "Ultrasonic scan record",
    acceptanceCriteria: "No indications exceeding AD-2026-001's acceptance criteria.",
    items: [
      { id: "a1", label: "Aircraft identified", instruction: "Confirm registration and MSN match the work order.", acceptanceCriteria: "Registration and MSN match N305ML.", requiresMeasurement: false, unit: null, minLimit: null, maxLimit: null, findingRequiredOnFail: false, evidenceRequired: false },
      { id: "a2", label: "AD-2026-001 revision verified", instruction: "Confirm AD-2026-001 rev. 1 is the current applicable revision.", acceptanceCriteria: "Revision matches the work order reference.", requiresMeasurement: false, unit: null, minLimit: null, maxLimit: null, findingRequiredOnFail: true, evidenceRequired: false },
      { id: "a3", label: "Fan disk ultrasonic scan performed", instruction: "Perform ultrasonic inspection of the fan disk per AD-2026-001.", acceptanceCriteria: "No indications exceeding acceptance criteria.", requiresMeasurement: false, unit: null, minLimit: null, maxLimit: null, findingRequiredOnFail: true, evidenceRequired: true },
      { id: "a4", label: "Scan results recorded", instruction: "Record scan results in the inspection log.", acceptanceCriteria: "Log entry completed.", requiresMeasurement: false, unit: null, minLimit: null, maxLimit: null, findingRequiredOnFail: false, evidenceRequired: false },
      { id: "a5", label: "Task completed", instruction: "Confirm all prior steps are complete before sign-off.", acceptanceCriteria: "All items resolved (Pass, Fail, or N/A).", requiresMeasurement: false, unit: null, minLimit: null, maxLimit: null, findingRequiredOnFail: false, evidenceRequired: false },
    ],
  },
  {
    id: "chk-1044",
    workOrderId: "wo-1044",
    title: "Engine 1 Borescope Follow-up (Defect Rectification)",
    requiredReference: "Internal follow-up — DEF-1",
    requiredTools: ["Borescope"],
    requiredParts: [],
    requiredEvidence: "Follow-up borescope images",
    acceptanceCriteria: "Scoring depth on the affected fan blade root remains within serviceable limits, or corrective action is identified.",
    items: [
      { id: "d1", label: "Aircraft identified", instruction: "Confirm registration and MSN match the work order.", acceptanceCriteria: "Registration and MSN match VT-ABC.", requiresMeasurement: false, unit: null, minLimit: null, maxLimit: null, findingRequiredOnFail: false, evidenceRequired: false },
      { id: "d2", label: "Defect DEF-1 reviewed", instruction: "Review the original DEF-1 finding and prior borescope images.", acceptanceCriteria: "Prior finding reviewed and understood.", requiresMeasurement: false, unit: null, minLimit: null, maxLimit: null, findingRequiredOnFail: false, evidenceRequired: false },
      { id: "d3", label: "Borescope follow-up inspection performed", instruction: "Re-inspect the scoring identified in DEF-1 for progression.", acceptanceCriteria: "Scoring depth within serviceable limits.", requiresMeasurement: false, unit: null, minLimit: null, maxLimit: null, findingRequiredOnFail: true, evidenceRequired: true },
      { id: "d4", label: "Corrective action assessed", instruction: "Determine whether corrective action beyond monitoring is required.", acceptanceCriteria: "Assessment recorded.", requiresMeasurement: false, unit: null, minLimit: null, maxLimit: null, findingRequiredOnFail: false, evidenceRequired: false },
      { id: "d5", label: "Task completed", instruction: "Confirm all prior steps are complete before sign-off.", acceptanceCriteria: "All items resolved (Pass, Fail, or N/A).", requiresMeasurement: false, unit: null, minLimit: null, maxLimit: null, findingRequiredOnFail: false, evidenceRequired: false },
    ],
  },
];

export function getChecklistByWorkOrderId(workOrderId: string): Checklist | undefined {
  return checklists.find((c) => c.workOrderId === workOrderId);
}

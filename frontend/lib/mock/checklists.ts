import type { Checklist } from "./types";

// MOCK DATA. Checklist item DEFINITIONS only (instruction, acceptance
// criteria, measurement bounds). Runtime completion state (result per item,
// actual values, notes, evidence-attached) lives only in ChecklistPanel's
// local React state — this is a prototype, not persisted to a backend.

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
];

export function getChecklistByWorkOrderId(workOrderId: string): Checklist | undefined {
  return checklists.find((c) => c.workOrderId === workOrderId);
}

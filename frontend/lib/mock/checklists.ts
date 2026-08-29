import type { Checklist } from "./types";

// MOCK DATA. Checklist completion state itself is NOT stored here — it lives
// only in the reviewing page's local React state (this is a prototype; see
// docs on the Human Review pattern). This file defines the static checklist
// definition (items, required references) that gets loaded into that state.

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
      { id: "i1", label: "Aircraft identified" },
      { id: "i2", label: "Correct maintenance data verified" },
      { id: "i3", label: "Required tooling available" },
      { id: "i4", label: "PPE confirmed" },
      { id: "i5", label: "Engine isolated" },
      { id: "i6", label: "Fan blades inspected" },
      { id: "i7", label: "Measurements recorded" },
      { id: "i8", label: "Photos attached" },
      { id: "i9", label: "Findings recorded" },
      { id: "i10", label: "Task completed" },
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
      { id: "i1", label: "Aircraft identified" },
      { id: "i2", label: "Correct maintenance data verified" },
      { id: "i3", label: "Required parts available" },
      { id: "i4", label: "PPE confirmed" },
      { id: "i5", label: "Hydraulic system depressurized" },
      { id: "i6", label: "Seal replaced" },
      { id: "i7", label: "Leak check performed" },
      { id: "i8", label: "Photos attached" },
      { id: "i9", label: "Findings recorded" },
      { id: "i10", label: "Task completed" },
    ],
  },
];

export function getChecklistByWorkOrderId(workOrderId: string): Checklist | undefined {
  return checklists.find((c) => c.workOrderId === workOrderId);
}

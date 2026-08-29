import type { Finding } from "./types";

// MOCK DATA. A Finding is what a technician records during a task (often
// against a specific checklist item); some findings are severe enough to
// also be raised as a standalone Defect (see lib/mock/defects.ts) — the two
// are related but distinct records, matching real MRO practice.
export const findings: Finding[] = [
  { id: "finding-1", workOrderId: "wo-1042", checklistItemId: "i6", description: "Minor scoring observed on Engine 1 fan blade root during borescope inspection.", severity: "LOW", requiresDefect: true },
  { id: "finding-2", workOrderId: "wo-1045", checklistItemId: null, description: "Hairline fatigue indication at wing spar station 340, pending NDT confirmation.", severity: "HIGH", requiresDefect: true },
  { id: "finding-3", workOrderId: "wo-1043", checklistItemId: "i7", description: "No leakage observed after 10-minute pressurized leak check.", severity: "LOW", requiresDefect: false },
];

export function findingsForWorkOrder(workOrderId: string): Finding[] {
  return findings.filter((f) => f.workOrderId === workOrderId);
}

export function getFindingById(id: string): Finding | undefined {
  return findings.find((f) => f.id === id);
}

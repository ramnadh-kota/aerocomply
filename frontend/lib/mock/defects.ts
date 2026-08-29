import type { Defect } from "./types";

// MOCK DATA. A defect may originate from a Finding recorded during a work
// order (see lib/mock/findings.ts) — related by description/work order, not
// merged into one entity, matching real MRO practice where a finding and the
// defect it raises are tracked separately.
export const defects: Defect[] = [
  { id: "def-1", aircraftId: "ac-1", workOrderId: "wo-1044", componentInstanceId: "ci-abc901", ataChapter: "72", description: "Minor scoring observed on Engine 1 fan blade root during borescope inspection.", severity: "LOW", status: "OPEN", discoveredBy: "Rahul Menon", reportedDate: "2026-03-12", correctiveAction: null, inspectorDecision: null },
  { id: "def-2", aircraftId: "ac-3", workOrderId: "wo-1045", componentInstanceId: null, ataChapter: "57", description: "Hairline fatigue indication at wing spar station 340, pending NDT confirmation.", severity: "HIGH", status: "OPEN", discoveredBy: "Diego Alvarez", reportedDate: "2026-03-15", correctiveAction: null, inspectorDecision: null },
  { id: "def-3", aircraftId: "ac-7", workOrderId: null, componentInstanceId: null, ataChapter: "52", description: "Cargo door latch mechanism exhibits excess play beyond service limit.", severity: "HIGH", status: "OPEN", discoveredBy: "Arjun Nair", reportedDate: "2026-03-05", correctiveAction: "Replace latch mechanism (part-6) — awaiting receipt.", inspectorDecision: null },
  { id: "def-4", aircraftId: "ac-1", workOrderId: null, componentInstanceId: null, ataChapter: "33", description: "Cabin reading light intermittent — deferred per MEL.", severity: "LOW", status: "DEFERRED", discoveredBy: "Rahul Menon", reportedDate: "2026-02-20", correctiveAction: "Deferred per MEL item 33-1; monitor next check.", inspectorDecision: "Accepted for deferral" },
  { id: "def-5", aircraftId: "ac-3", workOrderId: "wo-1051", componentInstanceId: "ci-gen114", ataChapter: "24", description: "IDG seal weep observed during walk-around, within acceptable limit pending repair.", severity: "MEDIUM", status: "RESOLVED", discoveredBy: "Wei Zhang", reportedDate: "2026-03-01", correctiveAction: "IDG bearing/seal repair completed under WO-1051.", inspectorDecision: "Approved — resolved" },
];

export function defectsForAircraft(aircraftId: string): Defect[] {
  return defects.filter((d) => d.aircraftId === aircraftId);
}

export function openDefects(): Defect[] {
  return defects.filter((d) => d.status === "OPEN");
}

export function defectsForWorkOrder(workOrderId: string): Defect[] {
  return defects.filter((d) => d.workOrderId === workOrderId);
}

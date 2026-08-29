import type { Defect } from "./types";

// MOCK DATA.
export const defects: Defect[] = [
  { id: "def-1", aircraftId: "ac-1", workOrderId: "wo-1044", description: "Minor scoring observed on Engine 1 fan blade root during borescope inspection.", severity: "MINOR", status: "OPEN", reportedDate: "2026-03-12" },
  { id: "def-2", aircraftId: "ac-3", workOrderId: "wo-1045", description: "Hairline fatigue indication at wing spar station 340, pending NDT confirmation.", severity: "MAJOR", status: "OPEN", reportedDate: "2026-03-15" },
  { id: "def-3", aircraftId: "ac-7", workOrderId: null, description: "Cargo door latch mechanism exhibits excess play beyond service limit.", severity: "MAJOR", status: "OPEN", reportedDate: "2026-03-05" },
  { id: "def-4", aircraftId: "ac-1", workOrderId: null, description: "Cabin reading light intermittent — deferred per MEL.", severity: "MINOR", status: "DEFERRED", reportedDate: "2026-02-20" },
  { id: "def-5", aircraftId: "ac-3", workOrderId: "wo-1051", description: "IDG seal weep observed during walk-around, within acceptable limit pending repair.", severity: "MINOR", status: "RESOLVED", reportedDate: "2026-03-01" },
];

export function defectsForAircraft(aircraftId: string): Defect[] {
  return defects.filter((d) => d.aircraftId === aircraftId);
}

export function openDefects(): Defect[] {
  return defects.filter((d) => d.status === "OPEN");
}

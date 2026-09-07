import type { MaintenanceAccomplishment } from "./types";

// M17 — real accomplishment records, the ONLY source the due engine reads
// for "last accomplished" (see getMaintenanceDueForAircraft,
// lib/mock/ai/analytics.ts). A WorkOrder's plannedStartDate/status is
// deliberately NOT read here — scheduling a task is not proof it happened.
// All DEMO_SEED; chosen to exercise exactly the M17 test scenarios:
//
//   accm-1 (ac-1, mreq-1045): CURRENT    — Scenario A
//   accm-2 (ac-5, mreq-1045): DUE_SOON   — Scenario B
//   accm-3 (ac-3, mreq-1045): OVERDUE    — Scenario C
//   accm-4 (ac-1, mreq-1042): CURRENT FH — Scenario D
//   accm-5 (ac-1, mreq-fc-1): CURRENT FC — Scenario E
//   accm-6 (ac-5, mreq-1042): computed FH but with a STALE-data caution
//     (ac-5's utilization is 71 days old, M16) — Scenario G
//
// ac-3 has NO accomplishment record for mreq-1042 (FH) — Scenario F,
// deliberately absent, not zero-filled.
export const maintenanceAccomplishments: MaintenanceAccomplishment[] = [
  { id: "accm-1", requirementId: "mreq-1045", aircraftId: "ac-1", accomplishedDate: "2026-03-12", accomplishedFH: null, accomplishedFC: null, workOrderId: null, source: "DEMO_SEED" },
  { id: "accm-2", requirementId: "mreq-1045", aircraftId: "ac-5", accomplishedDate: "2026-02-20", accomplishedFH: null, accomplishedFC: null, workOrderId: null, source: "DEMO_SEED" },
  { id: "accm-3", requirementId: "mreq-1045", aircraftId: "ac-3", accomplishedDate: "2026-01-01", accomplishedFH: null, accomplishedFC: null, workOrderId: null, source: "DEMO_SEED" },
  { id: "accm-4", requirementId: "mreq-1042", aircraftId: "ac-1", accomplishedDate: "2026-02-01", accomplishedFH: 8000, accomplishedFC: null, workOrderId: null, source: "DEMO_SEED" },
  { id: "accm-5", requirementId: "mreq-fc-1", aircraftId: "ac-1", accomplishedDate: "2026-02-01", accomplishedFH: null, accomplishedFC: 2700, workOrderId: null, source: "DEMO_SEED" },
  { id: "accm-6", requirementId: "mreq-1042", aircraftId: "ac-5", accomplishedDate: "2025-11-01", accomplishedFH: 19500, accomplishedFC: null, workOrderId: null, source: "DEMO_SEED" },
];

export function accomplishmentsForRequirementAndAircraft(requirementId: string, aircraftId: string): MaintenanceAccomplishment[] {
  return maintenanceAccomplishments.filter((a) => a.requirementId === requirementId && a.aircraftId === aircraftId);
}

/** Most recent accomplishment for a (requirement, aircraft) pair, or
 * undefined if none exists — undefined is the honest "never accomplished
 * on file" state, never treated as "accomplished at time zero". */
export function latestAccomplishment(requirementId: string, aircraftId: string): MaintenanceAccomplishment | undefined {
  const list = accomplishmentsForRequirementAndAircraft(requirementId, aircraftId);
  if (list.length === 0) return undefined;
  return [...list].sort((a, b) => b.accomplishedDate.localeCompare(a.accomplishedDate))[0];
}

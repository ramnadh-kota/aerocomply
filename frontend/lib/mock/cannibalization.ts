import type { CannibalizationRequest } from "./types";

// M13 — cannibalization foundation. One seeded candidate, tied to a real
// shortage (part-8 / APU-410, blocking WO-1054 on N412MX — see
// lib/mock/workOrders.ts). ac-8 (VT-JKL) is a real STORED aircraft in the
// fleet and therefore a plausible donor, but there is no part record in
// lib/mock/parts.ts confirming an APU-410 is actually installed on it — so
// `traceabilityStatus` is honestly UNKNOWN rather than asserted TRACEABLE.
// `authorizationStatus` stays PENDING_HUMAN_REVIEW: nothing in this
// prototype ever authorizes a cannibalization automatically.
export const cannibalizationRequests: CannibalizationRequest[] = [
  {
    id: "cann-1",
    sourceAircraftId: "ac-8",
    targetAircraftId: "ac-3",
    partId: "part-8",
    reason: "WO-1054 (APU starter motor replacement, N412MX) is material-blocked on APU-410 with no vendor availability on file; ac-8 (VT-JKL) is STORED and a plausible donor candidate.",
    authorizationStatus: "PENDING_HUMAN_REVIEW",
    removalStatus: "NOT_STARTED",
    installationStatus: "NOT_STARTED",
    traceabilityStatus: "UNKNOWN",
    createdAt: "2026-03-17",
  },
];

export function getCannibalizationCandidatesForAircraft(aircraftId: string): CannibalizationRequest[] {
  return cannibalizationRequests.filter((c) => c.targetAircraftId === aircraftId);
}

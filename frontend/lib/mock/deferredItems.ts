import type { DeferredItem } from "./types";

// M13/M18 — MEL/deferred-item foundation. Every record here ties to a real
// existing Defect (lib/mock/defects.ts) — none is fabricated. This dataset
// has no authoritative MEL document/reference anywhere, so `melReference`
// stays null on every record; `category`/`dueAt`/`operationalLimitations`/
// `requiredActions` are UNKNOWN/empty unless explicitly marked DEMO below.
// Four records exercise the M18 operational-status spectrum:
//   defer-1 (ac-1/def-4): dueAt null            -> UNKNOWN
//   defer-2 (ac-7/def-3): dueAt 2026-03-22       -> DUE_SOON
//   defer-3 (ac-2/def-6): dueAt 2026-02-01       -> OVERDUE (past MOCK_TODAY)
//   defer-4 (ac-6/def-7): status CLOSED          -> CLOSED
export const deferredItems: DeferredItem[] = [
  {
    id: "defer-1",
    aircraftId: "ac-1",
    defectId: "def-4",
    melReference: null,
    category: "UNKNOWN",
    openedAt: "2026-02-20",
    dueAt: null,
    status: "OPEN",
    workOrderId: null,
    // def-4's own description says "deferred per MEL" — the only record in
    // this dataset with even that much basis on file; still no reference
    // number, so melReference stays null.
    deferralBasis: "MEL",
    operationalLimitations: null,
    requiredActions: [],
    evidenceReferences: [],
    approvalRequired: true,
    approvalStatus: "PENDING",
  },
  {
    id: "defer-2",
    aircraftId: "ac-7",
    defectId: "def-3",
    melReference: null,
    category: "UNKNOWN",
    openedAt: "2026-03-05",
    dueAt: "2026-03-22",
    status: "OPEN",
    workOrderId: null,
    deferralBasis: "UNKNOWN",
    // Explicitly DEMO — proves the field can carry real limitation text
    // without asserting this is an actual approved placard/limitation.
    operationalLimitations: "(DEMO) Dispatch permitted with cargo door latch mechanism inspected before each departure.",
    requiredActions: ["(DEMO) Replace latch mechanism (part-6) upon receipt."],
    evidenceReferences: [],
    approvalRequired: true,
    approvalStatus: "PENDING",
  },
  {
    id: "defer-3",
    aircraftId: "ac-2",
    defectId: "def-6",
    melReference: null,
    category: "UNKNOWN",
    openedAt: "2026-03-16",
    dueAt: "2026-02-01",
    status: "OPEN",
    workOrderId: "wo-1052",
    deferralBasis: "UNKNOWN",
    operationalLimitations: null,
    requiredActions: [],
    evidenceReferences: [],
    approvalRequired: true,
    approvalStatus: "PENDING",
  },
  {
    id: "defer-4",
    aircraftId: "ac-6",
    defectId: "def-7",
    melReference: null,
    category: "UNKNOWN",
    openedAt: "2026-03-17",
    dueAt: "2026-04-01",
    status: "CLOSED",
    workOrderId: "wo-1053",
    deferralBasis: "UNKNOWN",
    operationalLimitations: null,
    requiredActions: [],
    evidenceReferences: ["(DEMO) WO-1053 completion record"],
    approvalRequired: true,
    approvalStatus: "APPROVED",
  },
];

export function getDeferredItemsForAircraft(aircraftId: string): DeferredItem[] {
  return deferredItems.filter((d) => d.aircraftId === aircraftId);
}

export function getOpenDeferredItems(): DeferredItem[] {
  return deferredItems.filter((d) => d.status === "OPEN");
}

import type { DeferredItem } from "./types";

// M13 — MEL/deferred-item foundation. There is exactly one DEFERRED defect
// in the existing dataset (def-4, lib/mock/defects.ts) — this is that real
// record's deferred-item view, not a fabricated one. This dataset has no
// authoritative MEL document/reference anywhere, so `melReference` is null
// and `category`/`dueAt` are UNKNOWN — never guessed to make the record look
// more complete than the source data actually supports.
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
  },
];

export function getDeferredItemsForAircraft(aircraftId: string): DeferredItem[] {
  return deferredItems.filter((d) => d.aircraftId === aircraftId);
}

export function getOpenDeferredItems(): DeferredItem[] {
  return deferredItems.filter((d) => d.status === "OPEN");
}

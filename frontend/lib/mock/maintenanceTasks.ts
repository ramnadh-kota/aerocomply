import type { MaintenanceTask } from "./types";

// M12.9 — Maintenance Task foundation. Structured reference PLACEHOLDERS
// only: this is the aviation-native "what procedure is this work order
// actually performing" layer requested by the M12.9 architecture milestone,
// not an AMM/IPC document store. Every `referenceId` below points at a real,
// already-seeded RegulatoryRequirement (lib/mock/regulations.ts) — never a
// fabricated AD/SB/AMM reference. Where no such requirement exists for a
// work order's underlying task, `referenceType` is "OTHER", `referenceId` is
// null, and `evidenceStatus` is "SOURCE_UNKNOWN" — this is the honest,
// intentional case, not a bug to "fix" by inventing a reference.
export const maintenanceTasks: MaintenanceTask[] = [
  {
    id: "mtask-1042",
    description: "Engine 1 fan disk borescope inspection per applicable AD",
    ataChapter: "72",
    referenceType: "AD",
    referenceId: "req-ad-2026-001",
    requiredSkill: "Engine Runup",
    inspectionRequired: true,
    evidenceStatus: "SOURCE_AVAILABLE",
  },
  {
    id: "mtask-1045",
    description: "Wing spar fatigue inspection per applicable AD",
    ataChapter: "57",
    referenceType: "AD",
    referenceId: "req-ad-2026-004",
    requiredSkill: "Structures",
    inspectionRequired: true,
    evidenceStatus: "SOURCE_AVAILABLE",
  },
  {
    id: "mtask-1046",
    description: "Cargo door latch mechanism inspection per applicable AD",
    ataChapter: "52",
    referenceType: "AD",
    referenceId: "req-ad-2026-005",
    requiredSkill: null,
    inspectionRequired: false,
    evidenceStatus: "SOURCE_AVAILABLE",
  },
  {
    id: "mtask-1051",
    description: "IDG seal repair",
    ataChapter: "24",
    referenceType: "OTHER",
    referenceId: null,
    requiredSkill: "Engine Runup",
    inspectionRequired: false,
    evidenceStatus: "SOURCE_UNKNOWN",
  },
  {
    id: "mtask-1054",
    description: "APU starter motor replacement (serialized rotable)",
    ataChapter: "49",
    referenceType: "OTHER",
    referenceId: null,
    requiredSkill: "APU",
    // Replacing a serialized rotable component is treated as requiring
    // independent inspection before release — a structural inference from
    // the existing SERIALIZED/rotable part record (lib/mock/parts.ts,
    // part-8), not a fabricated regulatory requirement.
    inspectionRequired: true,
    evidenceStatus: "SOURCE_UNKNOWN",
  },
  {
    id: "mtask-1055",
    description: "Fuel control unit calibration",
    ataChapter: "73",
    referenceType: "OTHER",
    referenceId: null,
    requiredSkill: "Fuel Systems",
    inspectionRequired: true,
    evidenceStatus: "SOURCE_UNKNOWN",
  },
];

export function getMaintenanceTaskById(id: string): MaintenanceTask | undefined {
  return maintenanceTasks.find((t) => t.id === id);
}

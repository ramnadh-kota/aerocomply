import type { EvidenceRecord, EvidenceRecordType } from "./types";

// M28 — Technician execution evidence store. PROTOTYPE STORAGE ONLY: this
// is an in-memory array mutated in place, exactly like every other mock
// store in this codebase (workOrders, parts, etc.) — not a database, not
// object storage. `fileRef` on each record holds a browser object URL
// (or similar prototype reference), not a durable production asset.
//
// Demo seed data — every record ties to a real existing WorkOrder/
// MaintenanceTask/Technician, exercising the M28 test scenarios:
//   WO-1042 (mtask-1042, REQUIRED): 2 ACCEPTED records -> gate PASS,
//     but WO-1042 is still WAITING_INSPECTION, demonstrating evidence
//     PASS + inspection still pending (Scenario D).
//   WO-1054 (mtask-1054, REQUIRED): zero records -> gate FAIL (Scenario B).
//   WO-1055 (mtask-1055, REQUIRED): 1 REJECTED record -> gate FAIL,
//     rejection reason recorded (Scenario E).
//   WO-1045 (mtask-1045, OPTIONAL): zero records -> gate NOT_REQUIRED
//     (Scenario C).
//   WO-1051 (mtask-1051, no evidenceRequirement set): zero records ->
//     gate NOT_REQUIRED (default/baseline case).
export const evidenceRecords: EvidenceRecord[] = [
  {
    id: "ev-exec-1",
    workOrderId: "wo-1042",
    maintenanceTaskId: "mtask-1042",
    aircraftId: "ac-1",
    uploadedByTechnicianId: "tech-1",
    evidenceType: "BEFORE",
    fileRef: "DEMO_SEED_PLACEHOLDER",
    fileName: "engine1-fan-before.jpg",
    capturedAt: "2026-03-14T09:10:00Z",
    technicianNote: "Fan disk prior to borescope inspection, no visible damage.",
    status: "ACCEPTED",
    createdAt: "2026-03-14T09:10:00Z",
    reviewedBy: "tech-3",
    reviewedAt: "2026-03-14T09:20:00Z",
    reviewNote: null,
  },
  {
    id: "ev-exec-2",
    workOrderId: "wo-1042",
    maintenanceTaskId: "mtask-1042",
    aircraftId: "ac-1",
    uploadedByTechnicianId: "tech-1",
    evidenceType: "AFTER",
    fileRef: "DEMO_SEED_PLACEHOLDER",
    fileName: "engine1-fan-after.jpg",
    capturedAt: "2026-03-16T13:35:00Z",
    technicianNote: "Borescope inspection complete, findings per finding-1.",
    status: "ACCEPTED",
    createdAt: "2026-03-16T13:35:00Z",
    reviewedBy: "tech-3",
    reviewedAt: "2026-03-16T13:45:00Z",
    reviewNote: null,
  },
  {
    id: "ev-exec-3",
    workOrderId: "wo-1055",
    maintenanceTaskId: "mtask-1055",
    aircraftId: "ac-10",
    uploadedByTechnicianId: "tech-1",
    evidenceType: "INSPECTION",
    fileRef: "DEMO_SEED_PLACEHOLDER",
    fileName: "fcu-calibration-reading.jpg",
    capturedAt: "2026-03-11T08:00:00Z",
    technicianNote: "Calibration reading photo.",
    status: "REJECTED",
    createdAt: "2026-03-11T08:00:00Z",
    reviewedBy: "tech-5",
    reviewedAt: "2026-03-11T14:00:00Z",
    reviewNote: "Calibration display is out of focus and the reading is not legible — resubmit with a clear photo of the display.",
  },
];

export function getEvidenceRecordById(id: string): EvidenceRecord | undefined {
  return evidenceRecords.find((e) => e.id === id);
}

export function evidenceRecordsForWorkOrder(workOrderId: string): EvidenceRecord[] {
  return evidenceRecords.filter((e) => e.workOrderId === workOrderId).sort((a, b) => a.capturedAt.localeCompare(b.capturedAt));
}

export function evidenceRecordsForAircraft(aircraftId: string): EvidenceRecord[] {
  return evidenceRecords.filter((e) => e.aircraftId === aircraftId).sort((a, b) => b.capturedAt.localeCompare(a.capturedAt));
}

let counter = evidenceRecords.length;

/** The ONE mutation that creates execution evidence. `fileRef` is expected
 * to already be a browser object URL (or similar prototype reference) —
 * this function does not touch storage, it only records the domain fact
 * that a technician submitted something. */
export function addEvidenceRecord(input: {
  workOrderId: string;
  maintenanceTaskId: string | null;
  aircraftId: string;
  uploadedByTechnicianId: string;
  evidenceType: EvidenceRecordType;
  fileRef: string;
  fileName: string;
  technicianNote: string | null;
}): EvidenceRecord {
  counter += 1;
  const record: EvidenceRecord = {
    id: `ev-exec-live-${counter}`,
    ...input,
    capturedAt: new Date().toISOString(),
    status: "SUBMITTED",
    createdAt: new Date().toISOString(),
    reviewedBy: null,
    reviewedAt: null,
    reviewNote: null,
  };
  evidenceRecords.push(record);
  return record;
}

export function removeEvidenceRecord(id: string): boolean {
  const idx = evidenceRecords.findIndex((e) => e.id === id);
  if (idx === -1) return false;
  // Only an un-reviewed, technician-submitted record may be removed —
  // never silently delete something a reviewer has already acted on.
  if (evidenceRecords[idx].status !== "SUBMITTED") return false;
  evidenceRecords.splice(idx, 1);
  return true;
}

/** The ONE review mutation — covers both accept and reject. Rejection
 * requires a reason (enforced by the caller passing a non-empty reviewNote
 * when status is REJECTED); this function itself refuses a reject with no
 * note. */
export function reviewEvidenceRecord(id: string, reviewedBy: string, status: "ACCEPTED" | "REJECTED", reviewNote: string | null): EvidenceRecord | null {
  const record = evidenceRecords.find((e) => e.id === id);
  if (!record) return null;
  if (status === "REJECTED" && (!reviewNote || reviewNote.trim().length === 0)) return null;
  record.status = status;
  record.reviewedBy = reviewedBy;
  record.reviewedAt = new Date().toISOString();
  record.reviewNote = reviewNote;
  return record;
}

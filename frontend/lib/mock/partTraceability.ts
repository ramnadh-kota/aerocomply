import type {
  PartReceivingRecord,
  PartCertificate,
  PartInstallation,
  PartRemoval,
  TraceabilityStatus,
} from "./types";
import { getPartById } from "./parts";

// MOCK DATA — M7.1 Aviation Parts Traceability Model. All certificate
// references below are clearly-marked demo values ("-DEMO-"), not real FAA
// 8130-3 / EASA Form 1 records. Records exist ONLY for parts that would
// honestly have them at this point in their lifecycle: a part still on
// order (status ORDERED) or in transit (AWAITING_RECEIPT) has NOT been
// received, so no receiving/certificate/installation record is seeded for
// it — callers must render "Insufficient source data." for those gaps
// rather than treating an absent record as a failure or a pass.

export const partReceivingRecords: PartReceivingRecord[] = [
  { id: "prr-1", partId: "part-1", receivedDate: "2026-06-02", receivedBy: "user-5", source: "Parker Aerospace Distribution (demo)", quantityReceived: 4 },
  { id: "prr-2", partId: "part-2", receivedDate: "2026-05-18", receivedBy: "user-5", source: "CFM International Parts Logistics (demo)", quantityReceived: 1 },
  { id: "prr-3", partId: "part-4", receivedDate: "2026-04-27", receivedBy: "user-5", source: "Meggitt Direct (demo)", quantityReceived: 6 },
  { id: "prr-4", partId: "part-7", receivedDate: "2026-03-11", receivedBy: "user-5", source: "Parker Aerospace Distribution (demo)", quantityReceived: 10 },
];

export const partCertificates: PartCertificate[] = [
  // part-2: complete chain — serialized rotable with an on-file 8130-3.
  { id: "pc-1", partId: "part-2", certificateType: "FAA_8130_3", certificateReference: "8130-3-DEMO-0042", certificateIssuer: "CFM International (demo)", certificateDate: "2026-05-15", verificationStatus: "PRESENT" },
  // part-1: batch consumable received into stock — no certificate was ever
  // produced/required for this class of item, honestly reflected as MISSING
  // rather than fabricating a reference.
  { id: "pc-2", partId: "part-1", certificateType: "OTHER", certificateReference: null, certificateIssuer: null, certificateDate: null, verificationStatus: "MISSING" },
  // part-4: a certificate is understood to exist on paper from the vendor
  // but has not yet been logged into this system — reference unknown, not
  // "missing" and not "non-compliant".
  { id: "pc-3", partId: "part-4", certificateType: "UNKNOWN", certificateReference: null, certificateIssuer: "Meggitt (demo)", certificateDate: null, verificationStatus: "REFERENCE_UNKNOWN" },
];

export const partInstallations: PartInstallation[] = [
  { id: "pi-1", partId: "part-2", aircraftId: "ac-1", componentInstanceId: "ci-abc901", workOrderId: "wo-1042", installationDate: "2026-05-20", installedBy: "user-5" },
];

// No PartRemoval records are seeded — no part in the current dataset has
// been removed from an aircraft. Kept as an empty, honestly-typed array
// rather than omitted, so the entity and its helpers exist ahead of real
// removal events.
export const partRemovals: PartRemoval[] = [];

export function receivingRecordForPart(partId: string): PartReceivingRecord | undefined {
  return partReceivingRecords.find((r) => r.partId === partId);
}

export function certificatesForPart(partId: string): PartCertificate[] {
  return partCertificates.filter((c) => c.partId === partId);
}

export function installationsForPart(partId: string): PartInstallation[] {
  return partInstallations.filter((i) => i.partId === partId);
}

export function removalsForPart(partId: string): PartRemoval[] {
  return partRemovals.filter((r) => r.partId === partId);
}

export function currentInstallationForPart(partId: string): PartInstallation | undefined {
  // "Current" = the most recent installation for this part with no later
  // removal recorded. With no removals seeded yet, this is simply the
  // latest installation record, if any.
  const installs = installationsForPart(partId);
  if (installs.length === 0) return undefined;
  return [...installs].sort((a, b) => (a.installationDate < b.installationDate ? 1 : -1))[0];
}

// Traceability status is derived honestly from which links actually exist —
// never inferred from Part.status alone, and never defaulted to TRACEABLE.
export function traceabilityStatusForPart(partId: string): TraceabilityStatus {
  const part = getPartById(partId);
  if (!part) return "UNKNOWN";

  const receiving = receivingRecordForPart(partId);
  const certs = certificatesForPart(partId);
  const installs = installationsForPart(partId);

  // A part not yet received (still on order / in transit) has no chain to
  // evaluate yet — that is an honest UNKNOWN, not a partial failure.
  if (!receiving && certs.length === 0 && installs.length === 0) return "UNKNOWN";

  const hasVerifiedCertificate = certs.some((c) => c.verificationStatus === "PRESENT");
  const isInstalled = part.installedAircraftId !== null;

  if (receiving && hasVerifiedCertificate && (!isInstalled || installs.length > 0)) return "TRACEABLE";
  if (receiving || certs.length > 0 || installs.length > 0) return "PARTIAL";
  return "UNKNOWN";
}

// M8.7 — Parts lifecycle expansion. A single explainable stage, derived
// from the same real records above — never inferred from Part.status
// alone. RETURNED/SCRAPPED are part of the target lifecycle but have no
// supporting field in the current data model, so they are intentionally
// unreachable here rather than guessed at.
// M14.6/M14.7 — QUARANTINED is now reachable: M13 added Part.serviceability,
// which supersedes the "no supporting field" note above for that one stage.
export type PartLifecycleStage =
  | "ORDERED"
  | "RECEIVED"
  | "QUARANTINED"
  | "CERTIFICATE_VERIFIED"
  | "STORED"
  | "INSTALLED"
  | "REMOVED"
  | "UNKNOWN";

export function partLifecycleStage(partId: string): PartLifecycleStage {
  const part = getPartById(partId);
  if (!part) return "UNKNOWN";
  if (removalsForPart(partId).length > 0) return "REMOVED";
  if (currentInstallationForPart(partId)) return "INSTALLED";
  if (part.serviceability === "QUARANTINED") return "QUARANTINED";
  if (part.status === "IN_STOCK") {
    const verified = certificatesForPart(partId).some((c) => c.verificationStatus === "PRESENT");
    if (verified) return "CERTIFICATE_VERIFIED";
    if (receivingRecordForPart(partId)) return "STORED";
  }
  if (part.status === "ORDERED") return "ORDERED";
  if (receivingRecordForPart(partId)) return "RECEIVED";
  return "UNKNOWN";
}

/** M8.7 — answers the standard parts-traceability questions from real
 * records only. Every field is a string rather than a structured object so
 * callers can render it directly; "Insufficient source data." wherever the
 * underlying record is absent. */
export interface PartTraceabilityAnswer {
  origin: string;
  supportingCertificate: string;
  installedAircraft: string;
  installingWorkOrder: string;
  receivedBy: string;
  removalInfo: string;
}

export function partTraceabilityAnswers(partId: string): PartTraceabilityAnswer {
  const receiving = receivingRecordForPart(partId);
  const certs = certificatesForPart(partId);
  const installation = currentInstallationForPart(partId);
  const removals = removalsForPart(partId);
  const presentCert = certs.find((c) => c.verificationStatus === "PRESENT");

  return {
    origin: receiving ? `Received ${receiving.receivedDate} from ${receiving.source}.` : "Insufficient source data.",
    supportingCertificate: presentCert ? `${presentCert.certificateType.replace(/_/g, " ")} — ${presentCert.certificateReference ?? "Insufficient source data."}` : "Insufficient source data.",
    installedAircraft: installation ? installation.aircraftId : "Insufficient source data.",
    installingWorkOrder: installation?.workOrderId ?? "Insufficient source data.",
    receivedBy: receiving ? receiving.receivedBy : "Insufficient source data.",
    removalInfo: removals.length > 0 ? removals.map((r) => `${r.removalDate}: ${r.reason}`).join("; ") : "Not removed — still in current disposition, per available records.",
  };
}

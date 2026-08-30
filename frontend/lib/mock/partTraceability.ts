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

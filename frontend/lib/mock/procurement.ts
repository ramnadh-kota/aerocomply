// M11 — Procurement & Vendor Intelligence. MOCK DATA. Every vendor below
// upgrades a name that ALREADY existed as a bare string elsewhere in the
// repository (VendorCost.vendorName in finance.ts, PartReceivingRecord.
// source in partTraceability.ts) into a real Vendor record — no new vendor
// identity is invented. Every VendorPartAvailability line references a
// real, existing Part id. Fields with no seeded value are left null/UNKNOWN
// rather than guessed — this is deliberately an uneven, realistic dataset
// (some vendors well-documented, some barely known) so the UI's UNKNOWN
// handling has something real to exercise.

import type { Vendor, VendorPartAvailability, PartRequest, PurchaseOrder } from "./types";
import { getPartById } from "./parts";

export const vendors: Vendor[] = [
  {
    id: "vendor-1",
    name: "Parker Aerospace Distribution (demo)",
    legalName: "Parker Aerospace Distribution Inc. (demo)",
    vendorCode: "V-PAD-01",
    country: "United States",
    city: "Irvine, CA",
    contactName: "Demo Contact — Sales Desk",
    email: null,
    phone: null,
    website: null,
    status: "ACTIVE",
    approvalStatus: "APPROVED",
    qualityStatus: "VERIFIED",
    approvedForAircraftTypes: ["737-800", "A320-200"],
    suppliedPartCategories: ["Hydraulics", "Seals"],
    capabilities: ["Batch parts distribution", "AOG desk"],
    certifications: ["AS9120 (demo)"],
    paymentTerms: "Net 30 (demo)",
    currency: "USD",
    shippingRegions: ["North America", "Europe"],
    aogSupport: true,
    leadTimeDays: 2,
    reliabilityScore: 92,
    qualityScore: 95,
    deliveryScore: 90,
    relationshipStatus: "PREFERRED",
    source: "DEMO_SEED",
  },
  {
    id: "vendor-2",
    name: "CFM International Parts Logistics (demo)",
    legalName: null,
    vendorCode: "V-CFM-02",
    country: "France",
    city: null,
    contactName: null,
    email: null,
    phone: null,
    website: null,
    status: "ACTIVE",
    approvalStatus: "APPROVED",
    qualityStatus: "VERIFIED",
    approvedForAircraftTypes: ["737-800"],
    suppliedPartCategories: ["Engine components"],
    capabilities: null,
    certifications: null,
    paymentTerms: null,
    currency: "USD",
    shippingRegions: null,
    aogSupport: null,
    leadTimeDays: null,
    reliabilityScore: null,
    qualityScore: 88,
    deliveryScore: null,
    relationshipStatus: "APPROVED",
    source: "DEMO_SEED",
  },
  {
    id: "vendor-3",
    name: "Meggitt Direct (demo)",
    legalName: null,
    vendorCode: "V-MEG-03",
    country: null,
    city: null,
    contactName: null,
    email: null,
    phone: null,
    website: null,
    status: "ACTIVE",
    approvalStatus: "PENDING",
    qualityStatus: "UNDER_REVIEW",
    approvedForAircraftTypes: null,
    suppliedPartCategories: ["Brakes"],
    capabilities: null,
    certifications: null,
    paymentTerms: null,
    currency: null,
    shippingRegions: null,
    aogSupport: null,
    leadTimeDays: null,
    reliabilityScore: null,
    qualityScore: null,
    deliveryScore: null,
    relationshipStatus: "NEW",
    source: "DEMO_SEED",
  },
  {
    id: "vendor-4",
    name: "Borescope NDT Services (demo)",
    legalName: null,
    vendorCode: "V-BNS-04",
    country: null,
    city: null,
    contactName: null,
    email: null,
    phone: null,
    website: null,
    status: "ACTIVE",
    approvalStatus: "APPROVED",
    qualityStatus: "VERIFIED",
    approvedForAircraftTypes: null,
    suppliedPartCategories: null,
    capabilities: ["Outsourced borescope NDT inspection"],
    certifications: null,
    paymentTerms: null,
    currency: "USD",
    shippingRegions: null,
    aogSupport: null,
    leadTimeDays: null,
    reliabilityScore: null,
    qualityScore: null,
    deliveryScore: null,
    relationshipStatus: "APPROVED",
    source: "DEMO_SEED",
  },
  {
    id: "vendor-5",
    name: "Structures NDT Partners (demo)",
    legalName: null,
    vendorCode: null,
    country: null,
    city: null,
    contactName: null,
    email: null,
    phone: null,
    website: null,
    status: "ACTIVE",
    approvalStatus: "UNKNOWN",
    qualityStatus: "UNKNOWN",
    approvedForAircraftTypes: null,
    suppliedPartCategories: null,
    capabilities: null,
    certifications: null,
    paymentTerms: null,
    currency: null,
    shippingRegions: null,
    aogSupport: null,
    leadTimeDays: null,
    reliabilityScore: null,
    qualityScore: null,
    deliveryScore: null,
    relationshipStatus: "UNKNOWN",
    source: "DEMO_SEED",
  },
];

// Prices reconcile exactly with the PartCost records already seeded in
// lib/mock/finance.ts (part-1 @ 180/unit) so a viewer who checks both
// pages sees consistent numbers, not two disconnected guesses.
export const vendorPartAvailability: VendorPartAvailability[] = [
  { id: "vpa-1", vendorId: "vendor-1", partId: "part-1", partNumber: "HP-442", description: "Hydraulic Pump Seal Kit", availabilityStatus: "IN_STOCK", quantityAvailable: 12, quantityOnOrder: 0, leadTimeDays: 2, unitPrice: 180, currency: "USD", moq: 1, aogAvailability: true, certificationStatus: "NOT_VERIFIED", lastUpdated: "2026-03-15", source: "DEMO_SEED" },
  { id: "vpa-2", vendorId: "vendor-1", partId: "part-7", partNumber: "SEAL-014", description: "Hydraulic Seal Kit", availabilityStatus: "IN_STOCK", quantityAvailable: 20, quantityOnOrder: 0, leadTimeDays: 2, unitPrice: 72, currency: "USD", moq: 1, aogAvailability: true, certificationStatus: "UNKNOWN", lastUpdated: "2026-03-15", source: "DEMO_SEED" },
  { id: "vpa-3", vendorId: "vendor-2", partId: "part-2", partNumber: "ABC-123", description: "Fan Disk Assembly", availabilityStatus: "LIMITED", quantityAvailable: 1, quantityOnOrder: null, leadTimeDays: null, unitPrice: null, currency: null, moq: null, aogAvailability: null, certificationStatus: "VERIFIED", lastUpdated: "2026-05-18", source: "DEMO_SEED" },
  { id: "vpa-4", vendorId: "vendor-3", partId: "part-4", partNumber: "BRK-210", description: "Brake Lining Set", availabilityStatus: "UNKNOWN", quantityAvailable: null, quantityOnOrder: null, leadTimeDays: null, unitPrice: null, currency: null, moq: null, aogAvailability: null, certificationStatus: "REFERENCE_UNKNOWN", lastUpdated: null, source: "DEMO_SEED" },
];

// Two illustrative requests on real, existing work orders/parts/technicians.
// pr-1 traces directly to the PartCost already recorded for WO-1050 in
// finance.ts (4 x 180 = 720) — a real cross-milestone connection, not a
// coincidence. pr-2 deliberately has no known vendor/price, since no
// VendorPartAvailability exists for LATCH-778 (part-6).
export const partRequests: PartRequest[] = [
  {
    id: "pr-1",
    aircraftId: "ac-1",
    workOrderId: "wo-1050",
    taskId: null,
    requestedBy: "tech-4",
    requestedAt: "2026-03-15",
    partNumber: "HP-442",
    partId: "part-1",
    description: "Hydraulic Pump Seal Kit",
    quantity: 4,
    priority: "ROUTINE",
    reason: "Replacement seals required to close WO-1050 hydraulic pump condition check.",
    requiredBy: "2026-03-18",
    preferredVendorId: "vendor-1",
    alternateVendorIds: [],
    evidenceIds: [],
    status: "RECEIVED",
    estimatedCost: 720,
    selectedVendorId: "vendor-1",
    approvedBy: "user-3",
    approvedAt: "2026-03-15",
    rejectionReason: null,
    source: "DEMO_SEED",
  },
  {
    id: "pr-2",
    aircraftId: "ac-7",
    workOrderId: "wo-1046",
    taskId: null,
    requestedBy: "tech-6",
    requestedAt: "2026-03-17",
    partNumber: "LATCH-778",
    partId: "part-6",
    description: "Cargo Door Latch Mechanism",
    quantity: 1,
    priority: "HIGH",
    reason: "Required to close open WO-1046 cargo door latch inspection finding.",
    requiredBy: "2026-03-21",
    preferredVendorId: null,
    alternateVendorIds: [],
    evidenceIds: [],
    status: "SUBMITTED",
    estimatedCost: null,
    selectedVendorId: null,
    approvedBy: null,
    approvedAt: null,
    rejectionReason: null,
    source: "DEMO_SEED",
  },
];

// M11.8 foundation only — no PO has been generated yet in this dataset.
export const purchaseOrders: PurchaseOrder[] = [];

export function getVendorById(id: string): Vendor | undefined {
  return vendors.find((v) => v.id === id);
}

export function vendorPartAvailabilityForPart(partId: string): VendorPartAvailability[] {
  return vendorPartAvailability.filter((a) => a.partId === partId);
}

export function vendorPartAvailabilityForVendor(vendorId: string): VendorPartAvailability[] {
  return vendorPartAvailability.filter((a) => a.vendorId === vendorId);
}

export function partRequestsForVendor(vendorId: string): PartRequest[] {
  return partRequests.filter((r) => r.preferredVendorId === vendorId || r.selectedVendorId === vendorId);
}

export function partRequestsForAircraft(aircraftId: string): PartRequest[] {
  return partRequests.filter((r) => r.aircraftId === aircraftId);
}

export function getPartRequestById(id: string): PartRequest | undefined {
  return partRequests.find((r) => r.id === id);
}

/** Real part records that have NO vendor availability line at all — the
 * honest "we don't know where to source this" list, used by Vendor
 * Intelligence and the AI engine instead of a fabricated marketplace. */
export function partsWithoutVendorAvailability(allPartIds: string[]): string[] {
  const covered = new Set(vendorPartAvailability.map((a) => a.partId));
  return allPartIds.filter((id) => !covered.has(id) && getPartById(id));
}

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
    clarificationNote: null,
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
    clarificationNote: null,
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

// M11.3 — Deterministic procurement scoring. ONE scoring function, used by
// both /procurement/parts (vendor comparison UI) and the AI engine's
// "which vendor should we use" answer — no duplicate recommendation logic.
// Weights: Availability 30% / Certification 25% / Lead Time 20% /
// Price 15% / Vendor Reliability 10%. A factor with no source data
// contributes to neither the score nor the weight total (never defaulted
// to 0), and is listed in `missingFactors` so confidence can be judged
// honestly.
const WEIGHTS = { availability: 0.30, certification: 0.25, leadTime: 0.20, price: 0.15, reliability: 0.10 };

export interface VendorScoreResult {
  vendorId: string;
  vendorName: string;
  line: VendorPartAvailability;
  score: number | null; // 0-100, or null if no scoreable factor exists at all
  confidence: "HIGH" | "MEDIUM" | "LOW" | "UNKNOWN";
  missingFactors: string[];
  factors: string[];
}

export function scoreVendorOptionsForPart(partId: string): VendorScoreResult[] {
  const lines = vendorPartAvailabilityForPart(partId);
  const prices = lines.map((l) => l.unitPrice).filter((p): p is number => p !== null);
  const minPrice = prices.length > 0 ? Math.min(...prices) : null;

  return lines.map((line) => {
    const vendor = getVendorById(line.vendorId);
    const vendorName = vendor?.name ?? line.vendorId;
    const missingFactors: string[] = [];
    const factors: string[] = [];
    let weightedSum = 0;
    let weightTotal = 0;

    const AVAILABILITY_SCORE: Record<string, number> = { IN_STOCK: 100, LIMITED: 55, ON_ORDER: 30, OUT_OF_STOCK: 0 };
    if (line.availabilityStatus !== "UNKNOWN") {
      weightedSum += WEIGHTS.availability * AVAILABILITY_SCORE[line.availabilityStatus];
      weightTotal += WEIGHTS.availability;
      factors.push(`Availability: ${line.availabilityStatus.replace(/_/g, " ")}`);
    } else {
      missingFactors.push("live availability not confirmed");
    }

    const CERT_SCORE: Record<string, number> = { VERIFIED: 100, NOT_VERIFIED: 40, REFERENCE_UNKNOWN: 20 };
    if (line.certificationStatus !== "UNKNOWN") {
      weightedSum += WEIGHTS.certification * CERT_SCORE[line.certificationStatus];
      weightTotal += WEIGHTS.certification;
      factors.push(`Certification: ${line.certificationStatus.replace(/_/g, " ")}`);
    } else {
      missingFactors.push("certification status unknown");
    }

    if (line.leadTimeDays !== null) {
      const leadScore = line.leadTimeDays <= 2 ? 100 : line.leadTimeDays <= 5 ? 70 : line.leadTimeDays <= 10 ? 40 : 20;
      weightedSum += WEIGHTS.leadTime * leadScore;
      weightTotal += WEIGHTS.leadTime;
      factors.push(`${line.leadTimeDays}-day lead time`);
    } else {
      missingFactors.push("lead time not on file");
    }

    if (line.unitPrice !== null && minPrice !== null) {
      const priceScore = minPrice === 0 ? 100 : Math.max(0, 100 - ((line.unitPrice - minPrice) / minPrice) * 100);
      weightedSum += WEIGHTS.price * priceScore;
      weightTotal += WEIGHTS.price;
      factors.push(`Price: ${line.currency ?? ""} ${line.unitPrice}`);
    } else {
      missingFactors.push("price not on file");
    }

    if (vendor?.reliabilityScore !== null && vendor?.reliabilityScore !== undefined) {
      weightedSum += WEIGHTS.reliability * vendor.reliabilityScore;
      weightTotal += WEIGHTS.reliability;
      factors.push(`Reliability score ${vendor.reliabilityScore}`);
    } else {
      missingFactors.push("vendor reliability history unavailable");
    }

    const score = weightTotal > 0 ? Math.round(weightedSum / weightTotal) : null;
    const confidence: VendorScoreResult["confidence"] = score === null ? "UNKNOWN" : weightTotal >= 0.85 ? "HIGH" : weightTotal >= 0.5 ? "MEDIUM" : "LOW";

    return { vendorId: line.vendorId, vendorName, line, score, confidence, missingFactors, factors };
  }).sort((a, b) => (b.score ?? -1) - (a.score ?? -1));
}

// --- M11.4/M11.5/M11.8 mutations — session-only, in-memory, mirroring the
// exact pattern already established by updateRole()/recordGeneratedReport()
// elsewhere in this codebase: mutate the exported array directly. No second
// state-management system.

export const cartItems: import("./types").ProcurementCartItem[] = [];

let cartItemCounter = 0;
export function addCartItem(input: Omit<import("./types").ProcurementCartItem, "id">): import("./types").ProcurementCartItem {
  cartItemCounter += 1;
  const item: import("./types").ProcurementCartItem = { id: `cart-${cartItemCounter}`, ...input };
  cartItems.push(item);
  return item;
}

export function removeCartItem(id: string): boolean {
  const idx = cartItems.findIndex((c) => c.id === id);
  if (idx < 0) return false;
  cartItems.splice(idx, 1);
  return true;
}

export function updateCartItemQuantity(id: string, quantity: number): void {
  const item = cartItems.find((c) => c.id === id);
  if (item) item.quantity = quantity;
}

export function clearCart(): void {
  cartItems.length = 0;
}

let requestIdCounter = partRequests.length;
export function createPartRequestFromCartItem(item: import("./types").ProcurementCartItem, estimatedCost: number | null): PartRequest {
  requestIdCounter += 1;
  const request: PartRequest = {
    id: `pr-${requestIdCounter}`,
    aircraftId: item.aircraftId,
    workOrderId: item.workOrderId,
    taskId: null,
    requestedBy: item.requestedBy,
    requestedAt: new Date().toISOString().slice(0, 10),
    partNumber: item.partNumber,
    partId: item.partId,
    description: item.description,
    quantity: item.quantity,
    priority: item.priority,
    reason: item.justification,
    requiredBy: null,
    preferredVendorId: item.preferredVendorId,
    alternateVendorIds: [],
    evidenceIds: [],
    status: "SUBMITTED",
    estimatedCost,
    selectedVendorId: null,
    approvedBy: null,
    approvedAt: null,
    rejectionReason: null,
    clarificationNote: null,
    source: "DEMO_SEED",
  };
  partRequests.push(request);
  return request;
}

export function approvePartRequest(id: string, approvedBy: string, selectedVendorId: string | null): PartRequest | undefined {
  const request = getPartRequestById(id);
  if (!request) return undefined;
  request.status = "APPROVED";
  request.approvedBy = approvedBy;
  request.approvedAt = new Date().toISOString().slice(0, 10);
  request.selectedVendorId = selectedVendorId ?? request.preferredVendorId;
  return request;
}

export function rejectPartRequest(id: string, approvedBy: string, reason: string): PartRequest | undefined {
  const request = getPartRequestById(id);
  if (!request) return undefined;
  request.status = "REJECTED";
  request.approvedBy = approvedBy;
  request.approvedAt = new Date().toISOString().slice(0, 10);
  request.rejectionReason = reason;
  return request;
}

export function returnPartRequestForClarification(id: string, note: string): PartRequest | undefined {
  const request = getPartRequestById(id);
  if (!request) return undefined;
  request.status = "CLARIFICATION_REQUIRED";
  request.clarificationNote = note;
  return request;
}

let poIdCounter = 0;
export function createPurchaseOrderFromRequest(requestId: string, createdBy: string): PurchaseOrder | { error: string } {
  const request = getPartRequestById(requestId);
  if (!request) return { error: "Part request not found." };
  if (request.status !== "APPROVED") return { error: "A purchase order can only be generated from an APPROVED request." };
  const vendorId = request.selectedVendorId ?? request.preferredVendorId;
  if (!vendorId) return { error: "No vendor has been selected for this request — insufficient source data to generate a PO." };
  const vendor = getVendorById(vendorId);
  if (!vendor) return { error: "Selected vendor could not be found." };

  const line = vendorPartAvailabilityForPart(request.partId ?? "").find((l) => l.vendorId === vendorId);
  const part = request.partId ? getPartById(request.partId) : undefined;
  const unitPrice = line?.unitPrice ?? null;
  const subtotal = unitPrice !== null ? unitPrice * request.quantity : 0;

  poIdCounter += 1;
  const poNumber = `PO-2026-${String(1000 + poIdCounter)}`;
  const po: PurchaseOrder = {
    id: `po-${poIdCounter}`,
    poNumber,
    vendorId,
    requestIds: [request.id],
    items: [{
      requestId: request.id,
      partNumber: request.partNumber,
      description: request.description,
      manufacturer: part?.manufacturer ?? null,
      quantity: request.quantity,
      unitPrice,
      currency: line?.currency ?? null,
    }],
    aircraftId: request.aircraftId,
    workOrderIds: request.workOrderId ? [request.workOrderId] : [],
    createdBy,
    approvedBy: request.approvedBy,
    createdAt: new Date().toISOString().slice(0, 10),
    status: "DRAFT",
    currency: line?.currency ?? "USD",
    subtotal,
    tax: null,
    shipping: null,
    total: subtotal,
    requiredBy: request.requiredBy,
    expectedDelivery: null,
    notes: null,
    vendorAcknowledgedAt: null,
    sentAt: null,
    source: "DEMO_SEED",
  };
  purchaseOrders.push(po);
  request.status = "ORDERED";
  return po;
}

export function getPurchaseOrderById(id: string): PurchaseOrder | undefined {
  return purchaseOrders.find((po) => po.id === id);
}

export function sendPurchaseOrder(id: string): PurchaseOrder | undefined {
  const po = getPurchaseOrderById(id);
  if (!po) return undefined;
  po.status = "SENT";
  po.sentAt = new Date().toISOString().slice(0, 10);
  return po;
}

export function receivePurchaseOrder(id: string): PurchaseOrder | undefined {
  const po = getPurchaseOrderById(id);
  if (!po) return undefined;
  po.status = "RECEIVED";
  for (const requestId of po.requestIds) {
    const req = getPartRequestById(requestId);
    if (req) req.status = "RECEIVED";
  }
  return po;
}

/** M11.4 — line-cost lookup shared by the cart page and Lisa's cart
 * questions, so the two can never disagree. Returns null when the item has
 * no preferred vendor or that vendor has no recorded price for the part —
 * never a fabricated $0. */
export function cartItemLineTotal(item: import("./types").ProcurementCartItem): number | null {
  if (!item.preferredVendorId) return null;
  const line = vendorPartAvailabilityForPart(item.partId ?? "").find((l) => l.vendorId === item.preferredVendorId);
  return line?.unitPrice !== undefined && line?.unitPrice !== null ? line.unitPrice * item.quantity : null;
}

export interface CartSummary {
  itemCount: number;
  itemsWithKnownPrice: number;
  knownTotal: number;
  fullyCalculable: boolean; // true only if every item's line total is known
  currency: string | null; // the currency of the known lines, when consistent; null if mixed/unknown
}

export function cartSummary(): CartSummary {
  const items = cartItems;
  let itemsWithKnownPrice = 0;
  let knownTotal = 0;
  let currency: string | null = null;
  let mixedCurrency = false;
  for (const item of items) {
    const total = cartItemLineTotal(item);
    if (total !== null) {
      itemsWithKnownPrice += 1;
      knownTotal += total;
      const line = item.preferredVendorId ? vendorPartAvailabilityForPart(item.partId ?? "").find((l) => l.vendorId === item.preferredVendorId) : undefined;
      if (line?.currency) {
        if (currency === null) currency = line.currency;
        else if (currency !== line.currency) mixedCurrency = true;
      }
    }
  }
  return {
    itemCount: items.length,
    itemsWithKnownPrice,
    knownTotal,
    fullyCalculable: items.length > 0 && itemsWithKnownPrice === items.length,
    currency: mixedCurrency ? null : currency,
  };
}

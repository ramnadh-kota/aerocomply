// M10 — MRO Financial Intelligence. MOCK DATA + deterministic calculation
// engine (plain arithmetic, no AI). Cost records are seeded for exactly 3
// of the fleet's 10 work orders — WO-1042 and WO-1050 (both on VT-ABC) and
// WO-1045 (on N412MX) — clearly marked CostSource: "DEMO_SEED", using real
// existing work order / part / technician / aircraft / organization ids.
// No other work order has cost data: callers must treat that absence as
// "Insufficient source data.", never as zero cost. WO-1050 deliberately has
// no CustomerCharge record, to exercise the "partial data" path honestly.
//
// No estimated-cost field exists anywhere in the domain model (WorkOrder
// has no estimatedCost), so cost variance is ALWAYS "Insufficient source
// data." here — never fabricated.

import type { LaborCost, PartCost, VendorCost, CustomerCharge } from "./types";
import { getWorkOrderById } from "./workOrders";
import { getAircraftById, currentRegistration } from "./aircraft";

const CURRENCY = "USD";

export const laborCosts: LaborCost[] = [
  { id: "lc-1", workOrderId: "wo-1042", taskId: null, technicianId: "tech-1", hours: 6, hourlyRate: 85, currency: CURRENCY, amount: 510, source: "DEMO_SEED" },
  { id: "lc-2", workOrderId: "wo-1050", taskId: null, technicianId: "tech-4", hours: 3, hourlyRate: 80, currency: CURRENCY, amount: 240, source: "DEMO_SEED" },
  { id: "lc-3", workOrderId: "wo-1045", taskId: null, technicianId: "tech-3", hours: 8, hourlyRate: 95, currency: CURRENCY, amount: 760, source: "DEMO_SEED" },
];

export const partCosts: PartCost[] = [
  { id: "pc-1", workOrderId: "wo-1042", partId: "part-2", quantity: 1, unitCost: 18500, currency: CURRENCY, amount: 18500, vendorName: null, source: "DEMO_SEED" },
  { id: "pc-2", workOrderId: "wo-1050", partId: "part-1", quantity: 4, unitCost: 180, currency: CURRENCY, amount: 720, vendorName: "Parker Aerospace Distribution (demo)", source: "DEMO_SEED" },
];

export const vendorCosts: VendorCost[] = [
  { id: "vc-1", workOrderId: "wo-1042", vendorName: "Borescope NDT Services (demo)", description: "Outsourced borescope NDT inspection", amount: 1200, currency: CURRENCY, date: "2026-03-15", source: "DEMO_SEED" },
  { id: "vc-2", workOrderId: "wo-1045", vendorName: "Structures NDT Partners (demo)", description: "Outsourced wing spar fatigue NDT", amount: 3400, currency: CURRENCY, date: "2026-03-16", source: "DEMO_SEED" },
];

// WO-1050 intentionally has no CustomerCharge record — see file header.
export const customerCharges: CustomerCharge[] = [
  { id: "cc-1", workOrderId: "wo-1042", customerOrgId: "org-1", laborCharge: 765, partsCharge: 20350, otherCharge: 500, totalCharge: 21615, currency: CURRENCY, source: "DEMO_SEED" },
  { id: "cc-2", workOrderId: "wo-1045", customerOrgId: "org-2", laborCharge: 1140, partsCharge: 0, otherCharge: 3740, totalCharge: 4880, currency: CURRENCY, source: "DEMO_SEED" },
];

export function laborCostsForWorkOrder(workOrderId: string): LaborCost[] {
  return laborCosts.filter((c) => c.workOrderId === workOrderId);
}
export function partCostsForWorkOrder(workOrderId: string): PartCost[] {
  return partCosts.filter((c) => c.workOrderId === workOrderId);
}
export function vendorCostsForWorkOrder(workOrderId: string): VendorCost[] {
  return vendorCosts.filter((c) => c.workOrderId === workOrderId);
}
export function customerChargeForWorkOrder(workOrderId: string): CustomerCharge | undefined {
  return customerCharges.find((c) => c.workOrderId === workOrderId);
}

/** Every work order that has at least one cost record of any kind. */
export function workOrderIdsWithCostData(): string[] {
  return Array.from(new Set([...laborCosts, ...partCosts, ...vendorCosts].map((c) => c.workOrderId)));
}

export type CostCoverage = "CALCULATED" | "PARTIAL" | "INSUFFICIENT_DATA";

export interface WorkOrderCostSummary {
  workOrderId: string;
  workOrderNumber: string;
  aircraftId: string;
  registration: string;
  laborCost: number;
  partsCost: number;
  vendorCost: number;
  otherCost: number;
  totalCost: number;
  customerCharge: number | null;
  grossMargin: number | null;
  marginPercent: number | null;
  estimatedCost: null; // no estimate field exists anywhere in the domain model
  variance: null;
  variancePercent: null;
  coverage: CostCoverage;
  missing: string[];
  currency: string;
}

/** Deterministic arithmetic only — see file header. Total Cost = Labor +
 * Parts + Vendor + Other. Gross Margin = Customer Charge - Total Cost.
 * Margin % = Gross Margin / Customer Charge. Never defaults an unavailable
 * figure to zero — every field that cannot be computed is null and the
 * summary is marked PARTIAL or INSUFFICIENT_DATA with an explicit reason. */
export function getWorkOrderCostSummary(workOrderId: string): WorkOrderCostSummary | null {
  const wo = getWorkOrderById(workOrderId);
  if (!wo) return null;
  const aircraft = getAircraftById(wo.aircraftId);
  const labor = laborCostsForWorkOrder(workOrderId);
  const parts = partCostsForWorkOrder(workOrderId);
  const vendor = vendorCostsForWorkOrder(workOrderId);
  const charge = customerChargeForWorkOrder(workOrderId);

  const hasAnyCostRecord = labor.length > 0 || parts.length > 0 || vendor.length > 0;
  const missing: string[] = [];

  if (!hasAnyCostRecord) {
    missing.push("no labor, parts, or vendor cost records exist for this work order");
    return {
      workOrderId,
      workOrderNumber: wo.workOrderNumber,
      aircraftId: wo.aircraftId,
      registration: aircraft ? currentRegistration(aircraft) : wo.aircraftId,
      laborCost: 0,
      partsCost: 0,
      vendorCost: 0,
      otherCost: 0,
      totalCost: 0,
      customerCharge: null,
      grossMargin: null,
      marginPercent: null,
      estimatedCost: null,
      variance: null,
      variancePercent: null,
      coverage: "INSUFFICIENT_DATA",
      missing,
      currency: CURRENCY,
    };
  }

  const laborCost = labor.reduce((s, c) => s + c.amount, 0);
  const partsCost = parts.reduce((s, c) => s + c.amount, 0);
  const vendorCost = vendor.reduce((s, c) => s + c.amount, 0);
  const otherCost = 0; // no "other" cost category (tooling/consumables/subcontracting) is seeded anywhere
  const totalCost = laborCost + partsCost + vendorCost + otherCost;

  let customerCharge: number | null = null;
  let grossMargin: number | null = null;
  let marginPercent: number | null = null;
  if (charge) {
    customerCharge = charge.totalCharge;
    grossMargin = charge.totalCharge - totalCost;
    marginPercent = charge.totalCharge !== 0 ? Math.round((grossMargin / charge.totalCharge) * 1000) / 10 : null;
    if (charge.totalCharge === 0) missing.push("customer charge is recorded as zero — margin % cannot be meaningfully computed");
  } else {
    missing.push("no customer charge record exists for this work order — margin cannot be determined");
  }
  missing.push("no estimated-cost field exists in the domain model — cost variance cannot be determined");

  return {
    workOrderId,
    workOrderNumber: wo.workOrderNumber,
    aircraftId: wo.aircraftId,
    registration: aircraft ? currentRegistration(aircraft) : wo.aircraftId,
    laborCost,
    partsCost,
    vendorCost,
    otherCost,
    totalCost,
    customerCharge,
    grossMargin,
    marginPercent,
    estimatedCost: null,
    variance: null,
    variancePercent: null,
    coverage: charge ? "CALCULATED" : "PARTIAL",
    missing,
    currency: CURRENCY,
  };
}

export interface AircraftCostSummary {
  aircraftId: string;
  registration: string;
  workOrdersWithCostData: number;
  totalWorkOrders: number;
  laborCost: number;
  partsCost: number;
  vendorCost: number;
  totalCost: number;
  customerCharge: number | null;
  grossMargin: number | null;
  coverage: CostCoverage;
}

export function getAircraftCostSummary(aircraftId: string, allWorkOrderIdsForAircraft: string[]): AircraftCostSummary | null {
  const aircraft = getAircraftById(aircraftId);
  if (!aircraft) return null;
  const summaries = allWorkOrderIdsForAircraft.map((id) => getWorkOrderCostSummary(id)).filter((s): s is WorkOrderCostSummary => s !== null && s.coverage !== "INSUFFICIENT_DATA");
  const registration = currentRegistration(aircraft);

  if (summaries.length === 0) {
    return {
      aircraftId,
      registration,
      workOrdersWithCostData: 0,
      totalWorkOrders: allWorkOrderIdsForAircraft.length,
      laborCost: 0,
      partsCost: 0,
      vendorCost: 0,
      totalCost: 0,
      customerCharge: null,
      grossMargin: null,
      coverage: "INSUFFICIENT_DATA",
    };
  }

  const laborCost = summaries.reduce((s, w) => s + w.laborCost, 0);
  const partsCost = summaries.reduce((s, w) => s + w.partsCost, 0);
  const vendorCost = summaries.reduce((s, w) => s + w.vendorCost, 0);
  const totalCost = laborCost + partsCost + vendorCost;
  const chargesKnown = summaries.every((w) => w.customerCharge !== null);
  const customerCharge = chargesKnown ? summaries.reduce((s, w) => s + (w.customerCharge ?? 0), 0) : null;
  const grossMargin = customerCharge !== null ? customerCharge - totalCost : null;

  return {
    aircraftId,
    registration,
    workOrdersWithCostData: summaries.length,
    totalWorkOrders: allWorkOrderIdsForAircraft.length,
    laborCost,
    partsCost,
    vendorCost,
    totalCost,
    customerCharge,
    grossMargin,
    coverage: summaries.length === allWorkOrderIdsForAircraft.length && chargesKnown ? "CALCULATED" : "PARTIAL",
  };
}

/** Human-readable "which part/vendor is driving cost" — real records only. */
export function highestCostPartCost(): PartCost | null {
  if (partCosts.length === 0) return null;
  return [...partCosts].sort((a, b) => b.amount - a.amount)[0];
}

export function highestVendorSpend(): VendorCost | null {
  if (vendorCosts.length === 0) return null;
  return [...vendorCosts].sort((a, b) => b.amount - a.amount)[0];
}

export interface FleetFinancialSummary {
  totalWorkOrders: number;
  workOrdersWithCostData: number;
  laborCost: number;
  partsCost: number;
  vendorCost: number;
  totalCost: number;
  customerCharge: number; // sum of only the work orders that HAVE a charge record
  workOrdersWithCharge: number;
  grossMargin: number | null; // null only if zero work orders have a charge record
  coverage: CostCoverage;
}

/** Fleet-wide roll-up over every work order that has cost data — plain
 * summation, no estimation. `workOrdersWithCostData` / `totalWorkOrders`
 * makes the coverage gap visible instead of implying complete data. */
export function getFleetFinancialSummary(allWorkOrderIds: string[]): FleetFinancialSummary {
  const summaries = allWorkOrderIds.map((id) => getWorkOrderCostSummary(id)).filter((s): s is WorkOrderCostSummary => s !== null && s.coverage !== "INSUFFICIENT_DATA");
  const laborCost = summaries.reduce((s, w) => s + w.laborCost, 0);
  const partsCost = summaries.reduce((s, w) => s + w.partsCost, 0);
  const vendorCost = summaries.reduce((s, w) => s + w.vendorCost, 0);
  const totalCost = laborCost + partsCost + vendorCost;
  const withCharge = summaries.filter((w) => w.customerCharge !== null);
  const customerCharge = withCharge.reduce((s, w) => s + (w.customerCharge ?? 0), 0);
  const grossMargin = withCharge.length > 0 ? customerCharge - withCharge.reduce((s, w) => s + w.totalCost, 0) : null;

  return {
    totalWorkOrders: allWorkOrderIds.length,
    workOrdersWithCostData: summaries.length,
    laborCost,
    partsCost,
    vendorCost,
    totalCost,
    customerCharge,
    workOrdersWithCharge: withCharge.length,
    grossMargin,
    coverage: summaries.length === 0 ? "INSUFFICIENT_DATA" : summaries.length === allWorkOrderIds.length && withCharge.length === summaries.length ? "CALCULATED" : "PARTIAL",
  };
}

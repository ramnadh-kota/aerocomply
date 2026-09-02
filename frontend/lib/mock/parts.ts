import type { Part } from "./types";

// MOCK DATA. This is an operational prototype, not full inventory
// accounting — quantity/location are illustrative, not a real stock ledger.
// Serialized parts (classification "SERIALIZED") trace to a real
// ComponentInstance already in lib/mock/components.ts wherever one exists.
// M12.9 — aviationClassification/serviceability (see types.ts) are derived
// honestly from each part's existing classification/status: a rotable is a
// serialized, individually-tracked component; a part not yet received
// (AWAITING_RECEIPT/ORDERED — not yet in hand) has UNKNOWN serviceability,
// since serviceability cannot be determined before receiving inspection.
export const parts: Part[] = [
  { id: "part-1", partNumber: "HP-442", serialNumber: null, description: "Hydraulic Pump Seal Kit", classification: "BATCH", status: "IN_STOCK", quantity: 4, location: "Stores — Bay 3", installedAircraftId: null, installedComponentInstanceId: null, workOrderId: "wo-1050", lifeLimitInfo: null, manufacturer: "Parker Aerospace (demo)", batchOrLot: "LOT-8842", aviationClassification: "CONSUMABLE", serviceability: "SERVICEABLE" },
  { id: "part-2", partNumber: "ABC-123", serialNumber: "ABC902", description: "Fan Disk Assembly", classification: "SERIALIZED", status: "IN_STOCK", quantity: 1, location: "Stores — Bay 1", installedAircraftId: "ac-1", installedComponentInstanceId: "ci-abc901", workOrderId: "wo-1042", lifeLimitInfo: "20,000 cycles life limit — 6,200 cycles accumulated", manufacturer: "CFM International (demo)", batchOrLot: null, aviationClassification: "ROTABLE", serviceability: "SERVICEABLE" },
  { id: "part-3", partNumber: "FCU-220", serialNumber: "FCU088", description: "Fuel Control Unit Calibration Kit", classification: "SERIALIZED", status: "AWAITING_RECEIPT", quantity: 1, location: "In Transit", installedAircraftId: null, installedComponentInstanceId: null, workOrderId: "wo-1055", lifeLimitInfo: null, manufacturer: null, batchOrLot: null, aviationClassification: "REPAIRABLE", serviceability: "UNKNOWN" },
  { id: "part-4", partNumber: "BRK-210", serialNumber: null, description: "Brake Lining Set", classification: "BATCH", status: "IN_STOCK", quantity: 6, location: "Stores — Bay 2", installedAircraftId: null, installedComponentInstanceId: null, workOrderId: null, lifeLimitInfo: null, manufacturer: "Meggitt (demo)", batchOrLot: "LOT-2201", aviationClassification: "EXPENDABLE", serviceability: "SERVICEABLE" },
  { id: "part-5", partNumber: "GEN-305", serialNumber: "GEN114", description: "IDG Bearing", classification: "SERIALIZED", status: "ORDERED", quantity: 1, location: "On Order", installedAircraftId: "ac-3", installedComponentInstanceId: "ci-gen114", workOrderId: "wo-1051", lifeLimitInfo: null, manufacturer: null, batchOrLot: null, aviationClassification: "ROTABLE", serviceability: "UNKNOWN" },
  { id: "part-6", partNumber: "LATCH-778", serialNumber: null, description: "Cargo Door Latch Mechanism", classification: "BATCH", status: "AWAITING_RECEIPT", quantity: 1, location: "In Transit", installedAircraftId: null, installedComponentInstanceId: null, workOrderId: "wo-1046", lifeLimitInfo: null, manufacturer: null, batchOrLot: null, aviationClassification: "EXPENDABLE", serviceability: "UNKNOWN" },
  { id: "part-7", partNumber: "SEAL-014", serialNumber: null, description: "Hydraulic Seal Kit", classification: "BATCH", status: "IN_STOCK", quantity: 10, location: "Stores — Bay 3", installedAircraftId: null, installedComponentInstanceId: null, workOrderId: null, lifeLimitInfo: null, manufacturer: "Parker Aerospace (demo)", batchOrLot: "LOT-5510", aviationClassification: "CONSUMABLE", serviceability: "SERVICEABLE" },
  { id: "part-8", partNumber: "APU-410", serialNumber: "APU301", description: "APU Starter Motor", classification: "SERIALIZED", status: "ORDERED", quantity: 1, location: "On Order", installedAircraftId: "ac-3", installedComponentInstanceId: "ci-apu301", workOrderId: "wo-1054", lifeLimitInfo: null, manufacturer: null, batchOrLot: null, aviationClassification: "ROTABLE", serviceability: "UNKNOWN" },
];

export function getPartById(id: string): Part | undefined {
  return parts.find((p) => p.id === id);
}

export function partsForWorkOrder(workOrderId: string): Part[] {
  return parts.filter((p) => p.workOrderId === workOrderId);
}

export function partsForAircraft(aircraftId: string): Part[] {
  return parts.filter((p) => p.installedAircraftId === aircraftId);
}

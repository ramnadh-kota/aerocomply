import type { Part } from "./types";

// MOCK DATA. This is an operational prototype, not full inventory
// accounting — quantity/location are illustrative, not a real stock ledger.
// Serialized parts (classification "SERIALIZED") trace to a real
// ComponentInstance already in lib/mock/components.ts wherever one exists.
export const parts: Part[] = [
  { id: "part-1", partNumber: "HP-442", serialNumber: null, description: "Hydraulic Pump Seal Kit", classification: "BATCH", status: "IN_STOCK", quantity: 4, location: "Stores — Bay 3", installedAircraftId: null, installedComponentInstanceId: null, workOrderId: "wo-1050", lifeLimitInfo: null },
  { id: "part-2", partNumber: "ABC-123", serialNumber: "ABC902", description: "Fan Disk Assembly", classification: "SERIALIZED", status: "IN_STOCK", quantity: 1, location: "Stores — Bay 1", installedAircraftId: "ac-1", installedComponentInstanceId: "ci-abc901", workOrderId: "wo-1042", lifeLimitInfo: "20,000 cycles life limit — 6,200 cycles accumulated" },
  { id: "part-3", partNumber: "FCU-220", serialNumber: "FCU088", description: "Fuel Control Unit Calibration Kit", classification: "SERIALIZED", status: "AWAITING_RECEIPT", quantity: 1, location: "In Transit", installedAircraftId: null, installedComponentInstanceId: null, workOrderId: null, lifeLimitInfo: null },
  { id: "part-4", partNumber: "BRK-210", serialNumber: null, description: "Brake Lining Set", classification: "BATCH", status: "IN_STOCK", quantity: 6, location: "Stores — Bay 2", installedAircraftId: null, installedComponentInstanceId: null, workOrderId: null, lifeLimitInfo: null },
  { id: "part-5", partNumber: "GEN-305", serialNumber: "GEN114", description: "IDG Bearing", classification: "SERIALIZED", status: "ORDERED", quantity: 1, location: "On Order", installedAircraftId: "ac-3", installedComponentInstanceId: "ci-gen114", workOrderId: "wo-1051", lifeLimitInfo: null },
  { id: "part-6", partNumber: "LATCH-778", serialNumber: null, description: "Cargo Door Latch Mechanism", classification: "BATCH", status: "AWAITING_RECEIPT", quantity: 1, location: "In Transit", installedAircraftId: null, installedComponentInstanceId: null, workOrderId: "wo-1046", lifeLimitInfo: null },
  { id: "part-7", partNumber: "SEAL-014", serialNumber: null, description: "Hydraulic Seal Kit", classification: "BATCH", status: "IN_STOCK", quantity: 10, location: "Stores — Bay 3", installedAircraftId: null, installedComponentInstanceId: null, workOrderId: null, lifeLimitInfo: null },
  { id: "part-8", partNumber: "APU-410", serialNumber: "APU301", description: "APU Starter Motor", classification: "SERIALIZED", status: "ORDERED", quantity: 1, location: "On Order", installedAircraftId: "ac-3", installedComponentInstanceId: "ci-apu301", workOrderId: null, lifeLimitInfo: null },
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

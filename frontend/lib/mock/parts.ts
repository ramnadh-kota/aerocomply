import type { Part } from "./types";

// MOCK DATA.
export const parts: Part[] = [
  { id: "part-1", partNumber: "HP-442", description: "Hydraulic Pump Seal Kit", status: "IN_STOCK", quantity: 4 },
  { id: "part-2", partNumber: "ABC-123-BLD", description: "Fan Blade Assembly", status: "IN_STOCK", quantity: 2 },
  { id: "part-3", partNumber: "FCU-220-CAL", description: "Fuel Control Unit Calibration Kit", status: "AWAITING_RECEIPT", quantity: 1 },
  { id: "part-4", partNumber: "BRK-210-LN", description: "Brake Lining Set", status: "IN_STOCK", quantity: 6 },
  { id: "part-5", partNumber: "GEN-305-BRG", description: "IDG Bearing", status: "ORDERED", quantity: 2 },
  { id: "part-6", partNumber: "LATCH-778", description: "Cargo Door Latch Mechanism", status: "AWAITING_RECEIPT", quantity: 1 },
  { id: "part-7", partNumber: "SEAL-014", description: "Hydraulic Seal Kit", status: "IN_STOCK", quantity: 10 },
  { id: "part-8", partNumber: "APU-410-STR", description: "APU Starter Motor", status: "ORDERED", quantity: 1 },
];

export function getPartById(id: string): Part | undefined {
  return parts.find((p) => p.id === id);
}

import type { Technician } from "./types";

// MOCK DATA.
// M12.9 — `licenseType` is a structured pointer to the B1.1/B2 category
// label already present in `certifications` below (the only license-type
// signal that exists in this dataset) — never a second, independently-
// entered value that could drift from it. Technicians with no B-category
// string in their certifications get `licenseType: null` (UNKNOWN), not a
// guessed default.
export const technicians: Technician[] = [
  { id: "tech-1", name: "Rahul Menon", role: "Technician", shiftStart: "06:00", shiftEnd: "14:00", certifications: ["Engine Runup", "Borescope Inspection", "B1.1"], licenseType: "B1.1" },
  { id: "tech-2", name: "Fatima Al-Sayed", role: "Technician", shiftStart: "06:00", shiftEnd: "14:00", certifications: ["Avionics", "B2"], licenseType: "B2" },
  { id: "tech-3", name: "Diego Alvarez", role: "Senior Technician / Inspector", shiftStart: "14:00", shiftEnd: "22:00", certifications: ["Structures", "NDT", "B1.1"], isInspector: true, licenseType: "B1.1" },
  { id: "tech-4", name: "Wei Zhang", role: "Technician", shiftStart: "14:00", shiftEnd: "22:00", certifications: ["Hydraulics", "B1.1"], licenseType: "B1.1" },
  { id: "tech-5", name: "Sara Kavanagh", role: "Lead Technician / Inspector", shiftStart: "22:00", shiftEnd: "06:00", certifications: ["Engine Runup", "APU", "B1.1", "B2"], isInspector: true, licenseType: "B1.1/B2" },
  { id: "tech-6", name: "Arjun Nair", role: "Technician", shiftStart: "06:00", shiftEnd: "14:00", certifications: ["Landing Gear", "B1.1"], licenseType: "B1.1" },
  // M12.7.1 — added to give newly-added work orders (Brake, Fuel, Cabin
  // Pressurization) a genuine, non-fabricated certification-keyword match
  // against a technician, rather than leaving every new work order with no
  // possible recommendation signal.
  { id: "tech-7", name: "Priya Desai", role: "Technician", shiftStart: "06:00", shiftEnd: "14:00", certifications: ["Brake Systems", "Landing Gear", "B1.1"] },
  { id: "tech-8", name: "Marco Silva", role: "Technician", shiftStart: "14:00", shiftEnd: "22:00", certifications: ["Fuel Systems", "B1.1"] },
  { id: "tech-9", name: "Elena Petrova", role: "Senior Technician", shiftStart: "22:00", shiftEnd: "06:00", certifications: ["Cabin Systems", "Pressurization", "B2"] },
];

export function getTechnicianById(id: string): Technician | undefined {
  return technicians.find((t) => t.id === id);
}

export function isOnShiftNow(t: Technician, nowHHMM = "09:00"): boolean {
  if (t.shiftStart < t.shiftEnd) return nowHHMM >= t.shiftStart && nowHHMM < t.shiftEnd;
  return nowHHMM >= t.shiftStart || nowHHMM < t.shiftEnd; // overnight shift
}

export function techniciansOnShift(nowHHMM = "09:00"): Technician[] {
  return technicians.filter((t) => isOnShiftNow(t, nowHHMM));
}

export function inspectors(): Technician[] {
  return technicians.filter((t) => t.isInspector);
}

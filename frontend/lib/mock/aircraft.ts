import type { Aircraft, AircraftType, AircraftVariant } from "./types";

// MOCK DATA — fictional fleet for the KOTA Aerospace OS prototype (M0.5).
// Entity shapes follow docs/ontology/AVIATION_ONTOLOGY.md §2.

export const aircraftTypes: AircraftType[] = [
  { id: "type-737", manufacturer: "Boeing", designation: "737" },
  { id: "type-a320", manufacturer: "Airbus", designation: "A320" },
];

export const aircraftVariants: AircraftVariant[] = [
  { id: "variant-738", aircraftTypeId: "type-737", modelDesignation: "737-800", tcdsNumber: "A16WE" },
  { id: "variant-a320-200", aircraftTypeId: "type-a320", modelDesignation: "A320-200", tcdsNumber: "A28NM" },
];

// 10 aircraft. VT-ABC and VT-XYZ are the two "hero" aircraft used throughout
// the guided walkthrough (see the M0.5 CTO delivery report).
export const aircraft: Aircraft[] = [
  {
    id: "ac-1",
    msn: "35124",
    aircraftVariantId: "variant-738",
    operatorOrgId: "org-1",
    status: "ACTIVE",
    entryIntoServiceDate: "2024-01-01",
    registrationHistory: [{ id: "reg-1a", registrationMark: "VT-ABC", effectiveFrom: "2024-01-01", effectiveTo: null }],
    // M12.9 — demo-labeled synthetic FH/FC, not real operational data.
    flightHours: 8420,
    flightCycles: 3110,
  },
  {
    id: "ac-2",
    msn: "5231",
    aircraftVariantId: "variant-a320-200",
    operatorOrgId: "org-1",
    status: "ACTIVE",
    entryIntoServiceDate: "2023-06-15",
    registrationHistory: [{ id: "reg-2a", registrationMark: "VT-XYZ", effectiveFrom: "2023-06-15", effectiveTo: null }],
  },
  {
    id: "ac-3",
    msn: "36011",
    aircraftVariantId: "variant-738",
    operatorOrgId: "org-2",
    status: "ACTIVE",
    entryIntoServiceDate: "2022-09-10",
    registrationHistory: [
      { id: "reg-3a", registrationMark: "N412ML", effectiveFrom: "2022-09-10", effectiveTo: "2025-04-01" },
      { id: "reg-3b", registrationMark: "N412MX", effectiveFrom: "2025-04-01", effectiveTo: null },
    ],
    // M12.9 — demo-labeled synthetic FH/FC, not real operational data.
    flightHours: 14210,
    flightCycles: 6890,
  },
  {
    id: "ac-4",
    msn: "5488",
    aircraftVariantId: "variant-a320-200",
    operatorOrgId: "org-2",
    status: "ACTIVE",
    entryIntoServiceDate: "2021-03-22",
    registrationHistory: [{ id: "reg-4a", registrationMark: "N207ML", effectiveFrom: "2021-03-22", effectiveTo: null }],
  },
  {
    id: "ac-5",
    msn: "35980",
    aircraftVariantId: "variant-738",
    operatorOrgId: "org-1",
    status: "ACTIVE",
    entryIntoServiceDate: "2020-11-05",
    registrationHistory: [{ id: "reg-5a", registrationMark: "VT-DEF", effectiveFrom: "2020-11-05", effectiveTo: null }],
    // M12.9 — demo-labeled synthetic FH/FC, not real operational data.
    flightHours: 19875,
    flightCycles: 9420,
  },
  {
    id: "ac-6",
    msn: "5099",
    aircraftVariantId: "variant-a320-200",
    operatorOrgId: "org-2",
    status: "ACTIVE",
    entryIntoServiceDate: "2019-07-18",
    registrationHistory: [{ id: "reg-6a", registrationMark: "N118ML", effectiveFrom: "2019-07-18", effectiveTo: null }],
  },
  {
    id: "ac-7",
    msn: "36502",
    aircraftVariantId: "variant-738",
    operatorOrgId: "org-1",
    status: "ACTIVE",
    entryIntoServiceDate: "2023-02-14",
    registrationHistory: [{ id: "reg-7a", registrationMark: "VT-GHI", effectiveFrom: "2023-02-14", effectiveTo: null }],
  },
  {
    id: "ac-8",
    msn: "5622",
    aircraftVariantId: "variant-a320-200",
    operatorOrgId: "org-1",
    status: "STORED",
    entryIntoServiceDate: "2018-05-30",
    registrationHistory: [{ id: "reg-8a", registrationMark: "VT-JKL", effectiveFrom: "2018-05-30", effectiveTo: null }],
  },
  {
    id: "ac-9",
    msn: "35770",
    aircraftVariantId: "variant-738",
    operatorOrgId: "org-2",
    status: "ACTIVE",
    entryIntoServiceDate: "2022-01-12",
    registrationHistory: [{ id: "reg-9a", registrationMark: "N305ML", effectiveFrom: "2022-01-12", effectiveTo: null }],
  },
  {
    id: "ac-10",
    msn: "5344",
    aircraftVariantId: "variant-a320-200",
    operatorOrgId: "org-2",
    status: "ACTIVE",
    entryIntoServiceDate: "2020-08-08",
    registrationHistory: [{ id: "reg-10a", registrationMark: "N221ML", effectiveFrom: "2020-08-08", effectiveTo: null }],
  },
];

export function getAircraftById(id: string): Aircraft | undefined {
  return aircraft.find((a) => a.id === id);
}

export function getAircraftVariant(variantId: string): AircraftVariant | undefined {
  return aircraftVariants.find((v) => v.id === variantId);
}

export function getAircraftType(typeId: string): AircraftType | undefined {
  return aircraftTypes.find((t) => t.id === typeId);
}

export function currentRegistration(a: Aircraft): string {
  return a.registrationHistory.find((r) => r.effectiveTo === null)?.registrationMark ?? a.registrationHistory[a.registrationHistory.length - 1].registrationMark;
}

export function registrationAsOf(a: Aircraft, isoDate: string): string | null {
  const entry = a.registrationHistory.find((r) => r.effectiveFrom <= isoDate && (r.effectiveTo === null || r.effectiveTo > isoDate));
  return entry?.registrationMark ?? null;
}

export function getAircraftByRegistration(mark: string): Aircraft | undefined {
  return aircraft.find((a) => a.registrationHistory.some((r) => r.registrationMark === mark));
}

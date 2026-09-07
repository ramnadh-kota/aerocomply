import type { Engine, EngineInstallation, EngineType } from "./types";
import { aircraft } from "./aircraft";

// MOCK DATA. See docs/ontology/ADR-008 — Engine is modeled as a first-class
// assessable asset, installed via the same interval-table pattern as a
// Component, but never itself a Component.

export const engineTypes: EngineType[] = [
  { id: "etype-cfm56-7b", manufacturer: "CFM International", modelDesignation: "CFM56-7B" },
  { id: "etype-cfm56-5b", manufacturer: "CFM International", modelDesignation: "CFM56-5B" },
];

function engineTypeForVariant(variantId: string): string {
  return variantId === "variant-738" ? "etype-cfm56-7b" : "etype-cfm56-5b";
}

// Hand-authored history for VT-ABC (ac-1) — the walkthrough's hero aircraft.
// Position 1 has been through three physical engines; Position 2 has not changed.
const heroEngines: Engine[] = [
  { id: "eng-100010", serialNumber: "SN 100010", engineTypeId: "etype-cfm56-7b" },
  { id: "eng-100234", serialNumber: "SN 100234", engineTypeId: "etype-cfm56-7b" },
  { id: "eng-100781", serialNumber: "SN 100781", engineTypeId: "etype-cfm56-7b" },
  { id: "eng-100532", serialNumber: "SN 100532", engineTypeId: "etype-cfm56-7b" },
];

const heroInstallations: EngineInstallation[] = [
  { id: "einst-1", aircraftId: "ac-1", engineId: "eng-100010", position: "ENGINE_1", installedAt: "2024-01-01", removedAt: "2025-06-15" },
  { id: "einst-2", aircraftId: "ac-1", engineId: "eng-100234", position: "ENGINE_1", installedAt: "2025-06-15", removedAt: "2026-02-10" },
  { id: "einst-3", aircraftId: "ac-1", engineId: "eng-100781", position: "ENGINE_1", installedAt: "2026-02-11", removedAt: null },
  { id: "einst-4", aircraftId: "ac-1", engineId: "eng-100532", position: "ENGINE_2", installedAt: "2024-01-01", removedAt: null },
];

// Every other aircraft: two engines, installed since entry into service, no swaps.
const otherAircraftEngines: Engine[] = [];
const otherAircraftInstallations: EngineInstallation[] = [];
let engineCounter = 200000;

for (const a of aircraft) {
  if (a.id === "ac-1") continue;
  const engineTypeId = engineTypeForVariant(a.aircraftVariantId);
  for (const position of ["ENGINE_1", "ENGINE_2"] as const) {
    const id = `eng-${engineCounter}`;
    const serialNumber = `SN ${engineCounter}`;
    otherAircraftEngines.push({ id, serialNumber, engineTypeId });
    otherAircraftInstallations.push({
      id: `einst-${id}`,
      aircraftId: a.id,
      engineId: id,
      position,
      installedAt: a.entryIntoServiceDate,
      removedAt: null,
    });
    engineCounter += 1;
  }
}

export const engines: Engine[] = [...heroEngines, ...otherAircraftEngines];
export const engineInstallations: EngineInstallation[] = [...heroInstallations, ...otherAircraftInstallations];

export function getEngineById(id: string): Engine | undefined {
  return engines.find((e) => e.id === id);
}

export function getEngineType(id: string): EngineType | undefined {
  return engineTypes.find((t) => t.id === id);
}

export function installationsForEngine(engineId: string): EngineInstallation[] {
  return engineInstallations.filter((i) => i.engineId === engineId);
}

export function installationsForAircraft(aircraftId: string): EngineInstallation[] {
  return engineInstallations
    .filter((i) => i.aircraftId === aircraftId)
    .sort((a, b) => a.installedAt.localeCompare(b.installedAt));
}

/** Engine occupying a position on an aircraft as-of a given ISO date (or now if omitted). */
export function engineAsOf(aircraftId: string, position: string, isoDate: string): EngineInstallation | undefined {
  return engineInstallations.find(
    (i) => i.aircraftId === aircraftId && i.position === position && i.installedAt <= isoDate && (i.removedAt === null || i.removedAt > isoDate)
  );
}

export function currentEnginesForAircraft(aircraftId: string): EngineInstallation[] {
  return engineInstallations.filter((i) => i.aircraftId === aircraftId && i.removedAt === null);
}

export function currentAircraftForEngine(engineId: string): string | undefined {
  return engineInstallations.find((i) => i.engineId === engineId && i.removedAt === null)?.aircraftId;
}

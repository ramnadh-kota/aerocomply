import type { MaintenanceProgram, MaintenanceRequirement } from "./types";

// M15 — Maintenance Program foundation. EVERYTHING in this file is
// explicitly DEMO DATA — a clearly-labeled prototype program used to
// exercise the architecture (intervals, applicability, forecasting), NOT a
// real approved aircraft maintenance program. Never remove or soften the
// "DEMO DATA" labeling on these records; never let a UI or Lisa response
// present them as an authoritative maintenance program.

export const maintenancePrograms: MaintenanceProgram[] = [
  {
    id: "mp-demo-1",
    name: "KOTA Demo Maintenance Program (Prototype)",
    revision: "DEMO-REV-1",
    effectiveDate: "2026-01-01",
    source: "DEMO DATA — prototype program for architecture testing, not an approved maintenance program",
    status: "ACTIVE",
  },
];

export const maintenanceRequirements: MaintenanceRequirement[] = [
  {
    id: "mreq-1042",
    programId: "mp-demo-1",
    description: "Engine fan disk borescope inspection (demo interval)",
    ataChapter: "72",
    intervalType: "FH",
    fhInterval: 500,
    fcInterval: null,
    calendarIntervalDays: null,
    taskReference: "DEMO-TC-72-00-00",
  },
  {
    id: "mreq-1045",
    programId: "mp-demo-1",
    description: "Wing spar fatigue inspection (demo interval)",
    ataChapter: "57",
    intervalType: "CALENDAR",
    fhInterval: null,
    fcInterval: null,
    calendarIntervalDays: 30,
    taskReference: "DEMO-TC-57-00-00",
  },
];

export function getMaintenanceProgramById(id: string): MaintenanceProgram | undefined {
  return maintenancePrograms.find((p) => p.id === id);
}

export function getMaintenanceRequirementById(id: string): MaintenanceRequirement | undefined {
  return maintenanceRequirements.find((r) => r.id === id);
}

export function requirementsForProgram(programId: string): MaintenanceRequirement[] {
  return maintenanceRequirements.filter((r) => r.programId === programId);
}

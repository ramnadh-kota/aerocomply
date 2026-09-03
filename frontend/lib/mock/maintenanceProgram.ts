import type { MaintenanceProgram, MaintenanceRequirement } from "./types";

// M15/M17 — Maintenance Program foundation. EVERYTHING in this file is
// explicitly DEMO DATA — a clearly-labeled prototype program used to
// exercise the due-engine architecture (intervals, applicability,
// forecasting), NOT a real approved aircraft maintenance program. Never
// remove or soften the "DEMO DATA" labeling on these records; never let a
// UI or Lisa response present them as an authoritative maintenance program.
//
// applicableAircraftIds is deliberately explicit per requirement — this
// dataset has no real fleet-applicability source (e.g. "all 737-800"), so
// applicability is listed by aircraft id rather than inferred from
// aircraft type. mreq-demo-unknown below has an EMPTY list on purpose —
// see Scenario H (M17 master prompt): applicability itself is UNKNOWN for
// that requirement, not "applies to zero aircraft" as a real fact.

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
    // ac-1 has a real accomplishment record (Scenario D — calculable).
    // ac-3 has FH data but no accomplishment record (Scenario F — UNKNOWN).
    // ac-5 has both an accomplishment record AND stale utilization data
    // (Scenario G — computed but flagged with an explicit CAUTION note).
    applicableAircraftIds: ["ac-1", "ac-3", "ac-5"],
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
    // ac-1 = CURRENT, ac-5 = DUE_SOON, ac-3 = OVERDUE — see
    // lib/mock/maintenanceAccomplishments.ts for the accomplishment dates
    // that produce each status (Scenarios A/B/C).
    applicableAircraftIds: ["ac-1", "ac-5", "ac-3"],
  },
  {
    id: "mreq-fc-1",
    programId: "mp-demo-1",
    description: "Landing gear retraction cycle check (demo interval)",
    ataChapter: "32",
    intervalType: "FC",
    fhInterval: null,
    fcInterval: 1000,
    calendarIntervalDays: null,
    taskReference: "DEMO-TC-32-00-00",
    // Scenario E — FC-based, calculable.
    applicableAircraftIds: ["ac-1"],
  },
  {
    id: "mreq-demo-unknown",
    programId: "mp-demo-1",
    description: "Cabin pressurization system overhaul (applicability not yet determined)",
    ataChapter: "21",
    intervalType: "CALENDAR",
    fhInterval: null,
    fcInterval: null,
    calendarIntervalDays: 365,
    taskReference: null,
    // Scenario H — deliberately empty: applicability itself is UNKNOWN for
    // this requirement, not a fact that it applies to no aircraft.
    applicableAircraftIds: [],
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

import type { MaintenanceProject, WorkPackage } from "./types";

// MOCK DATA. Projects are always anchored to a real aircraft already in
// lib/mock/aircraft.ts — MRO is connected to compliance, never a standalone
// module (see AeroComply Loop: Aircraft -> Configuration -> Maintenance ->
// Evidence -> Regulatory Requirement -> Assessment -> Human Review -> Audit).

export const workPackages: WorkPackage[] = [
  { id: "wp-1", projectId: "proj-1", title: "Engine Systems", description: "Engine, fan, and powerplant-related inspection tasks for this check." },
  { id: "wp-2", projectId: "proj-1", title: "Airframe Systems", description: "Hydraulics, structures, and airframe-related inspection tasks." },
  { id: "wp-3", projectId: "proj-2", title: "Wing Structure", description: "Wing spar and structural fatigue inspection tasks." },
  { id: "wp-4", projectId: "proj-3", title: "Cargo Systems", description: "Cargo door and latch mechanism inspection tasks." },
  { id: "wp-5", projectId: "proj-4", title: "Avionics & Flight Controls", description: "Avionics software and flight control system tasks." },
];

export const maintenanceProjects: MaintenanceProject[] = [
  {
    id: "proj-1",
    title: "VT-ABC — C-Check",
    aircraftId: "ac-1",
    projectType: "C_CHECK",
    status: "IN_PROGRESS",
    projectManager: "Ananya Rao",
    startDate: "2026-03-01",
    targetCompletionDate: "2026-03-20",
    progressPercent: 68,
    workPackageIds: ["wp-1", "wp-2"],
  },
  {
    id: "proj-2",
    title: "N412MX — A-Check",
    aircraftId: "ac-3",
    projectType: "A_CHECK",
    status: "IN_PROGRESS",
    projectManager: "Marcus Webb",
    startDate: "2026-03-10",
    targetCompletionDate: "2026-03-22",
    progressPercent: 40,
    workPackageIds: ["wp-3"],
  },
  {
    id: "proj-3",
    title: "VT-GHI — Unscheduled: Cargo Door Latch",
    aircraftId: "ac-7",
    projectType: "UNSCHEDULED",
    status: "PLANNED",
    projectManager: "Ananya Rao",
    startDate: "2026-03-18",
    targetCompletionDate: "2026-03-24",
    progressPercent: 0,
    workPackageIds: ["wp-4"],
  },
  {
    id: "proj-4",
    title: "VT-DEF — Avionics Software Modification",
    aircraftId: "ac-5",
    projectType: "MODIFICATION",
    status: "COMPLETED",
    projectManager: "Marcus Webb",
    startDate: "2026-01-20",
    targetCompletionDate: "2026-01-26",
    progressPercent: 100,
    workPackageIds: ["wp-5"],
  },
];

export function getProjectById(id: string): MaintenanceProject | undefined {
  return maintenanceProjects.find((p) => p.id === id);
}

export function projectsForAircraft(aircraftId: string): MaintenanceProject[] {
  return maintenanceProjects.filter((p) => p.aircraftId === aircraftId);
}

export function workPackagesForProject(projectId: string): WorkPackage[] {
  return workPackages.filter((wp) => wp.projectId === projectId);
}

export function getWorkPackageById(id: string): WorkPackage | undefined {
  return workPackages.find((wp) => wp.id === id);
}

export function activeProjects(): MaintenanceProject[] {
  return maintenanceProjects.filter((p) => p.status === "IN_PROGRESS" || p.status === "PLANNED");
}

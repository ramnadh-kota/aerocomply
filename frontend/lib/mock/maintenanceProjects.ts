import type { MaintenanceProject, WorkPackage } from "./types";

// MOCK DATA. Projects are always anchored to a real aircraft already in
// lib/mock/aircraft.ts — MRO is connected to compliance, never a standalone
// module (see AeroComply Loop: Aircraft -> Configuration -> Maintenance ->
// Evidence -> Regulatory Requirement -> Assessment -> Human Review -> Audit).

export const workPackages: WorkPackage[] = [
  {
    id: "wp-1", projectId: "proj-1", aircraftId: "ac-1", title: "Engine Systems",
    description: "Engine, fan, and powerplant-related inspection tasks for this check.",
    ataChapter: "72", status: "READY_FOR_INSPECTION", completionPercent: 85, dueDate: "2026-03-17",
    assignedTechnicianId: "tech-1", inspectorId: "tech-3",
    requiredPartIds: ["part-2"], requiredTools: ["Borescope", "Torque Wrench"],
    complianceReference: "AD-2026-001",
  },
  {
    id: "wp-2", projectId: "proj-1", aircraftId: "ac-1", title: "Airframe Systems",
    description: "Hydraulics, structures, and airframe-related inspection tasks.",
    ataChapter: "29", status: "COMPLETED", completionPercent: 100, dueDate: "2026-03-08",
    assignedTechnicianId: "tech-4", inspectorId: "tech-5",
    requiredPartIds: ["part-1"], requiredTools: ["Seal Puller"],
    complianceReference: "SB-2025-114",
  },
  {
    id: "wp-3", projectId: "proj-2", aircraftId: "ac-3", title: "Wing Structure",
    description: "Wing spar and structural fatigue inspection tasks.",
    ataChapter: "57", status: "IN_PROGRESS", completionPercent: 45, dueDate: "2026-03-19",
    assignedTechnicianId: "tech-3", inspectorId: "tech-5",
    requiredPartIds: [], requiredTools: ["NDT Kit"],
    complianceReference: "AD-2026-004",
  },
  {
    id: "wp-4", projectId: "proj-3", aircraftId: "ac-7", title: "Cargo Systems",
    description: "Cargo door and latch mechanism inspection tasks.",
    ataChapter: "52", status: "NOT_STARTED", completionPercent: 0, dueDate: "2026-03-24",
    assignedTechnicianId: "tech-6", inspectorId: null,
    requiredPartIds: ["part-6"], requiredTools: [],
    complianceReference: "AD-2026-005",
  },
  {
    id: "wp-5", projectId: "proj-4", aircraftId: "ac-5", title: "Avionics & Flight Controls",
    description: "Avionics software and flight control system tasks.",
    ataChapter: "22", status: "COMPLETED", completionPercent: 100, dueDate: "2026-01-25",
    assignedTechnicianId: "tech-2", inspectorId: "tech-5",
    requiredPartIds: [], requiredTools: [],
    complianceReference: "AD-2026-003",
  },
];

export const maintenanceProjects: MaintenanceProject[] = [
  {
    id: "proj-1",
    projectNumber: "PRJ-2026-001",
    title: "VT-ABC — C-Check",
    aircraftId: "ac-1",
    projectType: "C_CHECK",
    status: "IN_PROGRESS",
    priority: "HIGH",
    projectManager: "Ananya Rao",
    leadTechnicianId: "tech-1",
    startDate: "2026-03-01",
    targetCompletionDate: "2026-03-20",
    actualStartDate: "2026-03-01",
    actualCompletionDate: null,
    progressPercent: 68,
    workPackageIds: ["wp-1", "wp-2"],
    riskNotes: ["Engine 1 borescope follow-up (WO-1044) is overdue.", "Hydraulic pump seal condition check (WO-1050) is awaiting parts."],
  },
  {
    id: "proj-2",
    projectNumber: "PRJ-2026-002",
    title: "N412MX — A-Check",
    aircraftId: "ac-3",
    projectType: "A_CHECK",
    status: "IN_PROGRESS",
    priority: "CRITICAL",
    projectManager: "Marcus Webb",
    leadTechnicianId: "tech-3",
    startDate: "2026-03-10",
    targetCompletionDate: "2026-03-22",
    actualStartDate: "2026-03-10",
    actualCompletionDate: null,
    progressPercent: 40,
    workPackageIds: ["wp-3"],
    riskNotes: ["Wing spar fatigue inspection (WO-1045) is CRITICAL priority — pending NDT confirmation of a hairline indication."],
  },
  {
    id: "proj-3",
    projectNumber: "PRJ-2026-003",
    title: "VT-GHI — Unscheduled: Cargo Door Latch",
    aircraftId: "ac-7",
    projectType: "UNSCHEDULED",
    status: "PLANNED",
    priority: "HIGH",
    projectManager: "Ananya Rao",
    leadTechnicianId: "tech-6",
    startDate: "2026-03-18",
    targetCompletionDate: "2026-03-24",
    actualStartDate: null,
    actualCompletionDate: null,
    progressPercent: 0,
    workPackageIds: ["wp-4"],
    riskNotes: ["Replacement latch mechanism (part-6) is awaiting receipt — may delay start."],
  },
  {
    id: "proj-4",
    projectNumber: "PRJ-2026-004",
    title: "VT-DEF — Avionics Software Modification",
    aircraftId: "ac-5",
    projectType: "MODIFICATION",
    status: "COMPLETED",
    priority: "MEDIUM",
    projectManager: "Marcus Webb",
    leadTechnicianId: "tech-2",
    startDate: "2026-01-20",
    targetCompletionDate: "2026-01-26",
    actualStartDate: "2026-01-20",
    actualCompletionDate: "2026-01-25",
    progressPercent: 100,
    workPackageIds: ["wp-5"],
    riskNotes: [],
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

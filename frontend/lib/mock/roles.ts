// MOCK DATA — Role & Access Management prototype.
// This is a UI demonstration of how AeroComply *could* control access. It is
// NOT a real authorization system: no server-side enforcement exists, no
// session is actually scoped by these roles, and nothing here should be
// treated as a security boundary. See PermissionMatrix rendering in
// app/(app)/organization/roles for how this is displayed.

export type PermissionLevel = "NONE" | "VIEW" | "EDIT" | "APPROVE";

export const PERMISSION_MODULES = [
  "Aircraft",
  "Compliance",
  "MRO Operations",
  "Inspection",
  "Evidence",
  "Audit",
  "AI",
  "Administration",
] as const;

export type PermissionModule = (typeof PERMISSION_MODULES)[number];

export interface ModulePermission {
  module: PermissionModule;
  level: PermissionLevel;
  notes?: string;
}

export interface Role {
  id: string;
  name: string;
  description: string;
  scope: string; // e.g. "Fleet-wide", "Assigned aircraft only"
  permissions: ModulePermission[];
  aiAccess: { ask: boolean; analytics: boolean; reports: boolean };
  status: "ACTIVE" | "INACTIVE";
  lastUpdated: string;
}

export interface UserAccount {
  id: string;
  name: string;
  roleId: string;
  department: string;
  assignedAircraftIds: string[];
  assignedProjectIds: string[];
  status: "ACTIVE" | "INACTIVE";
  lastActivity: string;
}

function perm(permModule: PermissionModule, level: PermissionLevel, notes?: string): ModulePermission {
  return { module: permModule, level, notes };
}

export const roles: Role[] = [
  {
    id: "role-org-admin",
    name: "Organization Admin",
    description: "Full administrative control over the organization's AeroComply tenant, including user and role management.",
    scope: "Organization-wide",
    permissions: [
      perm("Aircraft", "EDIT"),
      perm("Compliance", "APPROVE"),
      perm("MRO Operations", "APPROVE"),
      perm("Inspection", "APPROVE"),
      perm("Evidence", "EDIT"),
      perm("Audit", "APPROVE", "View and export"),
      perm("AI", "APPROVE", "Ask, analytics, and reports"),
      perm("Administration", "APPROVE", "Manage users, roles, organization"),
    ],
    aiAccess: { ask: true, analytics: true, reports: true },
    status: "ACTIVE",
    lastUpdated: "2026-02-10",
  },
  {
    id: "role-compliance-manager",
    name: "Compliance Manager",
    description: "Owns applicability assessments and regulatory compliance decisions across the fleet.",
    scope: "Fleet-wide",
    permissions: [
      perm("Aircraft", "VIEW"),
      perm("Compliance", "APPROVE"),
      perm("MRO Operations", "VIEW"),
      perm("Inspection", "VIEW"),
      perm("Evidence", "EDIT"),
      perm("Audit", "VIEW"),
      perm("AI", "APPROVE"),
      perm("Administration", "NONE"),
    ],
    aiAccess: { ask: true, analytics: true, reports: true },
    status: "ACTIVE",
    lastUpdated: "2026-02-14",
  },
  {
    id: "role-maintenance-manager",
    name: "Maintenance Manager",
    description: "Oversees MRO projects, work packages, and technician assignment across the hangar floor.",
    scope: "Fleet-wide",
    permissions: [
      perm("Aircraft", "VIEW"),
      perm("Compliance", "VIEW"),
      perm("MRO Operations", "APPROVE"),
      perm("Inspection", "VIEW"),
      perm("Evidence", "VIEW"),
      perm("Audit", "VIEW"),
      perm("AI", "APPROVE"),
      perm("Administration", "NONE"),
    ],
    aiAccess: { ask: true, analytics: true, reports: true },
    status: "ACTIVE",
    lastUpdated: "2026-03-01",
  },
  {
    id: "role-maintenance-planner",
    name: "Maintenance Planner",
    description: "Plans work orders and work packages and assigns technicians to tasks.",
    scope: "Assigned projects",
    permissions: [
      perm("Aircraft", "VIEW"),
      perm("Compliance", "VIEW"),
      perm("MRO Operations", "EDIT", "Create work orders, assign technicians"),
      perm("Inspection", "VIEW"),
      perm("Evidence", "VIEW"),
      perm("Audit", "VIEW"),
      perm("AI", "VIEW"),
      perm("Administration", "NONE"),
    ],
    aiAccess: { ask: true, analytics: true, reports: false },
    status: "ACTIVE",
    lastUpdated: "2026-03-05",
  },
  {
    id: "role-technician",
    name: "Technician",
    description: "Executes assigned work orders and checklists, and signs off completed tasks.",
    scope: "Assigned work orders only",
    permissions: [
      perm("Aircraft", "VIEW"),
      perm("Compliance", "NONE"),
      perm("MRO Operations", "EDIT", "Execute checklist, submit for inspection"),
      perm("Inspection", "NONE"),
      perm("Evidence", "EDIT", "Upload"),
      perm("Audit", "NONE"),
      perm("AI", "VIEW"),
      perm("Administration", "NONE"),
    ],
    aiAccess: { ask: true, analytics: false, reports: false },
    status: "ACTIVE",
    lastUpdated: "2026-03-10",
  },
  {
    id: "role-inspector",
    name: "Inspector",
    description: "Reviews completed technician work and issues the pass/fail/return decision that closes the trust loop.",
    scope: "Assigned inspection queue",
    permissions: [
      perm("Aircraft", "VIEW"),
      perm("Compliance", "VIEW"),
      perm("MRO Operations", "VIEW"),
      perm("Inspection", "APPROVE", "Review, approve, reject, return"),
      perm("Evidence", "VIEW"),
      perm("Audit", "VIEW"),
      perm("AI", "VIEW"),
      perm("Administration", "NONE"),
    ],
    aiAccess: { ask: true, analytics: true, reports: false },
    status: "ACTIVE",
    lastUpdated: "2026-03-12",
  },
  {
    id: "role-reliability-engineer",
    name: "Reliability Engineer",
    description: "Analyzes defect and maintenance trends to identify fleet-wide reliability and compliance risk.",
    scope: "Fleet-wide, read-only",
    permissions: [
      perm("Aircraft", "VIEW"),
      perm("Compliance", "VIEW"),
      perm("MRO Operations", "VIEW"),
      perm("Inspection", "VIEW"),
      perm("Evidence", "VIEW"),
      perm("Audit", "VIEW"),
      perm("AI", "APPROVE", "Ask, analytics, and reports"),
      perm("Administration", "NONE"),
    ],
    aiAccess: { ask: true, analytics: true, reports: true },
    status: "ACTIVE",
    lastUpdated: "2026-02-20",
  },
  {
    id: "role-auditor",
    name: "Auditor",
    description: "Independent read-only access to the full audit trail and underlying records for compliance review.",
    scope: "Organization-wide, read-only",
    permissions: [
      perm("Aircraft", "VIEW"),
      perm("Compliance", "VIEW"),
      perm("MRO Operations", "VIEW"),
      perm("Inspection", "VIEW"),
      perm("Evidence", "VIEW"),
      perm("Audit", "APPROVE", "View and export"),
      perm("AI", "VIEW"),
      perm("Administration", "NONE"),
    ],
    aiAccess: { ask: true, analytics: false, reports: true },
    status: "ACTIVE",
    lastUpdated: "2026-01-30",
  },
  {
    id: "role-executive",
    name: "Executive / Management",
    description: "Fleet-wide read-only visibility into compliance exposure, maintenance risk, and operations reporting.",
    scope: "Organization-wide, read-only",
    permissions: [
      perm("Aircraft", "VIEW"),
      perm("Compliance", "VIEW"),
      perm("MRO Operations", "VIEW"),
      perm("Inspection", "VIEW"),
      perm("Evidence", "NONE"),
      perm("Audit", "VIEW"),
      perm("AI", "APPROVE"),
      perm("Administration", "NONE"),
    ],
    aiAccess: { ask: true, analytics: true, reports: true },
    status: "ACTIVE",
    lastUpdated: "2026-03-15",
  },
  {
    id: "role-read-only",
    name: "Read Only",
    description: "Minimal view-only access for stakeholders who need visibility without any edit capability.",
    scope: "Organization-wide, read-only",
    permissions: [
      perm("Aircraft", "VIEW"),
      perm("Compliance", "VIEW"),
      perm("MRO Operations", "VIEW"),
      perm("Inspection", "VIEW"),
      perm("Evidence", "VIEW"),
      perm("Audit", "VIEW"),
      perm("AI", "VIEW"),
      perm("Administration", "NONE"),
    ],
    aiAccess: { ask: true, analytics: false, reports: false },
    status: "ACTIVE",
    lastUpdated: "2026-03-17",
  },
];

export const users: UserAccount[] = [
  { id: "user-1", name: "Priya Nair", roleId: "role-org-admin", department: "IT & Systems", assignedAircraftIds: [], assignedProjectIds: [], status: "ACTIVE", lastActivity: "2026-03-17T08:10:00Z" },
  { id: "user-2", name: "Elena Petrov", roleId: "role-compliance-manager", department: "Compliance", assignedAircraftIds: ["ac-1", "ac-3", "ac-5", "ac-7"], assignedProjectIds: [], status: "ACTIVE", lastActivity: "2026-03-17T07:40:00Z" },
  { id: "user-3", name: "Marcus Webb", roleId: "role-maintenance-manager", department: "Maintenance", assignedAircraftIds: ["ac-1", "ac-3", "ac-5", "ac-7"], assignedProjectIds: ["proj-1", "proj-2", "proj-3", "proj-4"], status: "ACTIVE", lastActivity: "2026-03-17T09:05:00Z" },
  { id: "user-4", name: "Ananya Rao", roleId: "role-maintenance-planner", department: "Maintenance Planning", assignedAircraftIds: ["ac-1", "ac-7"], assignedProjectIds: ["proj-1", "proj-3"], status: "ACTIVE", lastActivity: "2026-03-16T18:22:00Z" },
  { id: "user-5", name: "Rahul Menon", roleId: "role-technician", department: "Line Maintenance", assignedAircraftIds: ["ac-1"], assignedProjectIds: ["proj-1"], status: "ACTIVE", lastActivity: "2026-03-17T06:55:00Z" },
  { id: "user-6", name: "Diego Alvarez", roleId: "role-inspector", department: "Quality / Inspection", assignedAircraftIds: ["ac-1", "ac-3"], assignedProjectIds: ["proj-1", "proj-2"], status: "ACTIVE", lastActivity: "2026-03-17T09:30:00Z" },
  { id: "user-7", name: "Sara Kavanagh", roleId: "role-inspector", department: "Quality / Inspection", assignedAircraftIds: ["ac-3", "ac-5"], assignedProjectIds: ["proj-2", "proj-4"], status: "ACTIVE", lastActivity: "2026-03-17T05:15:00Z" },
  { id: "user-8", name: "Wei Zhang", roleId: "role-reliability-engineer", department: "Engineering", assignedAircraftIds: ["ac-1", "ac-3", "ac-5", "ac-7"], assignedProjectIds: [], status: "ACTIVE", lastActivity: "2026-03-16T14:00:00Z" },
  { id: "user-9", name: "Fatima Al-Sayed", roleId: "role-auditor", department: "Internal Audit", assignedAircraftIds: [], assignedProjectIds: [], status: "ACTIVE", lastActivity: "2026-03-15T11:12:00Z" },
  { id: "user-10", name: "James Okafor", roleId: "role-executive", department: "Executive", assignedAircraftIds: [], assignedProjectIds: [], status: "ACTIVE", lastActivity: "2026-03-14T09:00:00Z" },
  { id: "user-11", name: "Guest Viewer", roleId: "role-read-only", department: "External Stakeholder", assignedAircraftIds: [], assignedProjectIds: [], status: "ACTIVE", lastActivity: "2026-03-12T10:00:00Z" },
];

export function getRoleById(id: string): Role | undefined {
  return roles.find((r) => r.id === id);
}

export function getUserById(id: string): UserAccount | undefined {
  return users.find((u) => u.id === id);
}

export function usersForRole(roleId: string): UserAccount[] {
  return users.filter((u) => u.roleId === roleId);
}

/**
 * Plain-language "what this role can access" summary, grouped by access
 * level, for the role/user detail pages. Prototype simulation — permissions
 * are not enforced; this only formats the existing permission matrix above.
 */
export function roleAccessSummary(role: Role): { approve: string[]; edit: string[]; view: string[]; none: string[] } {
  return {
    approve: role.permissions.filter((p) => p.level === "APPROVE").map((p) => p.module),
    edit: role.permissions.filter((p) => p.level === "EDIT").map((p) => p.module),
    view: role.permissions.filter((p) => p.level === "VIEW").map((p) => p.module),
    none: role.permissions.filter((p) => p.level === "NONE").map((p) => p.module),
  };
}

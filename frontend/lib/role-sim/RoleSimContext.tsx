"use client";

// Prototype "View as Role" simulation. This is a purely visual/UI simulation
// of what the existing role permission matrix (lib/mock/roles.ts) would
// change about the interface — it does NOT enforce anything, does not gate
// any data fetch, and is not a real authorization system. Session-only
// (React state, mounted in app/(app)/layout.tsx), resets on reload.

import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import { getRoleById, roles, type PermissionLevel, type PermissionModule } from "@/lib/mock/roles";

export const SIMULATABLE_ROLE_IDS = [
  "role-org-admin",
  "role-compliance-manager",
  "role-maintenance-manager",
  "role-inspector",
  "role-technician",
  "role-auditor",
  "role-executive",
  "role-read-only",
] as const;

const DEFAULT_ROLE_ID = "role-org-admin";

interface RoleSimContextValue {
  roleId: string;
  setRoleId: (id: string) => void;
  reset: () => void;
  accessFor: (permModule: PermissionModule) => PermissionLevel;
}

const RoleSimContext = createContext<RoleSimContextValue | null>(null);

export function RoleSimProvider({ children }: { children: ReactNode }) {
  const [roleId, setRoleId] = useState(DEFAULT_ROLE_ID);

  const value = useMemo<RoleSimContextValue>(() => {
    const role = getRoleById(roleId);
    return {
      roleId,
      setRoleId,
      reset: () => setRoleId(DEFAULT_ROLE_ID),
      accessFor: (permModule: PermissionModule) => role?.permissions.find((p) => p.module === permModule)?.level ?? "NONE",
    };
  }, [roleId]);

  return <RoleSimContext.Provider value={value}>{children}</RoleSimContext.Provider>;
}

export function useRoleSim(): RoleSimContextValue {
  const ctx = useContext(RoleSimContext);
  if (!ctx) throw new Error("useRoleSim must be used within RoleSimProvider");
  return ctx;
}

export function simulatableRoles() {
  return roles.filter((r) => (SIMULATABLE_ROLE_IDS as readonly string[]).includes(r.id));
}

// Maps sidebar nav hrefs to the permission module that governs them, for the
// "hide/disable unauthorized prototype actions" requirement. Not exhaustive —
// only routes with a clear module mapping are dimmed; the rest remain
// visible, since this is a UI demonstration, not a security boundary.
export const NAV_MODULE_MAP: Record<string, PermissionModule> = {
  "/compliance": "Compliance",
  "/regulations": "Compliance",
  "/assessments": "Compliance",
  "/evidence": "Evidence",
  "/maintenance/control-tower": "MRO Operations",
  "/maintenance/discrepancies": "MRO Operations",
  "/maintenance/operations": "MRO Operations",
  "/maintenance/hangar": "MRO Operations",
  "/maintenance/planning": "MRO Operations",
  "/maintenance/projects": "MRO Operations",
  "/maintenance/work-orders": "MRO Operations",
  "/maintenance/technicians": "MRO Operations",
  "/maintenance/tasks": "MRO Operations",
  "/maintenance/defects": "MRO Operations",
  "/maintenance/parts": "MRO Operations",
  "/maintenance/records": "MRO Operations",
  "/maintenance/inspections": "Inspection",
  "/audit": "Audit",
  "/ai": "AI",
  "/reports": "AI",
  "/organization/users": "Administration",
  "/organization/roles": "Administration",
};

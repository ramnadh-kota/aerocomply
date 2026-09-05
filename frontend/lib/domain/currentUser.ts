// M8.3 — Current-user abstraction.
//
// There is no real authentication in this prototype. Rather than letting
// that absence leak into domain logic (pages/components reaching directly
// into a "demo user" constant scattered around the codebase), every caller
// that needs to know "who is doing this" goes through getCurrentUser()
// here. Swapping in real auth later means changing only this function's
// body — nothing that calls getCurrentUser() needs to change.
//
// This is deliberately NOT the same thing as RoleSimProvider
// (lib/role-sim/RoleSimContext.tsx), which lets a signed-in user preview
// the UI "as" a different role for demos — that remains a pure UI
// simulation with no bearing on identity. getCurrentUser() answers "who is
// really signed in" (today: a fixed demo identity); RoleSim answers "what
// should the UI look like if I were role X".

import { getUserById, getRoleById, type UserAccount, type Role } from "../mock/roles";
import { membershipForUser } from "./organization";
import { getOrganizationById } from "../mock/organizations";
import type { Organization } from "../mock/types";

export interface CurrentUser {
  user: UserAccount;
  role: Role | undefined;
  organization: Organization | undefined;
}

// Clearly isolated development/demo identity — see file header. Never
// treat this as a real authenticated session; it exists only so the rest
// of the app has one place to ask "who is this".
const DEV_DEMO_USER_ID = "user-3"; // Marcus Webb, Maintenance Manager — matches the RoleSim default persona's operational scope

export function getCurrentUser(): CurrentUser | undefined {
  const user = getUserById(DEV_DEMO_USER_ID);
  if (!user) return undefined;
  const membership = membershipForUser(user.id);
  return {
    user,
    role: getRoleById(user.roleId),
    organization: membership ? getOrganizationById(membership.organizationId) : undefined,
  };
}

/** Coarse allow/deny check reusing the existing Role.permissions matrix —
 * no second permission system. Returns "UNKNOWN" (never a silent allow)
 * when the module isn't found on the role. */
export function currentUserAccessFor(permModule: Role["permissions"][number]["module"]): "APPROVE" | "EDIT" | "VIEW" | "NONE" | "UNKNOWN" {
  const current = getCurrentUser();
  if (!current?.role) return "UNKNOWN";
  const entry = current.role.permissions.find((p) => p.module === permModule);
  return entry ? entry.level : "UNKNOWN";
}

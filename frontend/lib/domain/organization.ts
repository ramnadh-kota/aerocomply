// M8.2 — Organization / tenant domain model.
//
// The current mock dataset only models Organization -> Aircraft (via
// Aircraft.operatorOrgId — see app/(app)/organization/page.tsx). Site and
// Hangar/Base do not exist as real records anywhere in the dataset. Rather
// than fabricating fake site/hangar data to make this look populated, this
// file defines the TYPED SHAPE that a future Site/Hangar layer would need,
// and an honest "not yet modeled" resolver so callers can render
// "Insufficient source data." instead of guessing.
//
// This does not replace lib/mock/organizations.ts or lib/role-sim — it
// documents the next layer down and gives OrganizationMembership/Permission
// a home ahead of real multi-tenant auth (see currentUser.ts).

import { users } from "../mock/roles";
import { organizations } from "../mock/organizations";

export interface Site {
  id: string;
  organizationId: string;
  name: string;
  country: string;
}

export interface HangarBase {
  id: string;
  siteId: string;
  name: string;
}

// No Site/HangarBase records exist in the current dataset — see file header.
export const sites: Site[] = [];
export const hangarBases: HangarBase[] = [];

export function siteForOrganization(_organizationId: string): Site[] {
  return sites.filter((s) => s.organizationId === _organizationId);
}

export function hangarBasesForSite(_siteId: string): HangarBase[] {
  return hangarBases.filter((h) => h.siteId === _siteId);
}

// --- Organization -> Users -> Roles -> Permissions -----------------------
// Reuses lib/mock/roles.ts (Role, ModulePermission) as the single source of
// role/permission data — this is a membership join, not a second role
// system.

export interface OrganizationMembership {
  userId: string;
  organizationId: string;
  roleId: string;
}

// Every seeded user in lib/mock/roles.ts currently belongs to the single
// seeded organization — see lib/mock/organizations.ts. Modeled explicitly
// here (rather than assumed) so a future multi-org dataset only needs to
// populate this array, not change any consumer.
export const organizationMemberships: OrganizationMembership[] = organizations[0]
  ? users.map((u) => ({ userId: u.id, organizationId: organizations[0].id, roleId: u.roleId }))
  : [];

export function membershipsForOrganization(organizationId: string): OrganizationMembership[] {
  return organizationMemberships.filter((m) => m.organizationId === organizationId);
}

export function membershipForUser(userId: string): OrganizationMembership | undefined {
  return organizationMemberships.find((m) => m.userId === userId);
}

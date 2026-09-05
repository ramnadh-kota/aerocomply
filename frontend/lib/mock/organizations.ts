import type { Organization } from "./types";

// MOCK DATA — see frontend/lib/mock/README.md for provenance/disclaimer.
export const organizations: Organization[] = [
  { id: "org-1", name: "Aero India", orgType: "OPERATOR" },
  { id: "org-2", name: "Meridian Airlines", orgType: "OPERATOR" },
  { id: "org-3", name: "Continental CAMO Services", orgType: "CAMO" },
  { id: "org-4", name: "Falcon MRO Group", orgType: "MRO" },
  { id: "org-5", name: "Skyline Capital Leasing", orgType: "LESSOR" },
];

export function getOrganizationById(id: string): Organization | undefined {
  return organizations.find((o) => o.id === id);
}

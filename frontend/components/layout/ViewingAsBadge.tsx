"use client";

import { useRoleSim } from "@/lib/role-sim/RoleSimContext";
import { getRoleById } from "@/lib/mock/roles";

/** Small dashboard indicator for the prototype role simulation (see Topbar). */
export function ViewingAsBadge() {
  const { roleId } = useRoleSim();
  const role = getRoleById(roleId);
  if (!role) return null;
  return (
    <span className="ac-badge ac-badge-unknown" title="Prototype role simulation — permissions are not enforced">
      Viewing as: {role.name}
    </span>
  );
}

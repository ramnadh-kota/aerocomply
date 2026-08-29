"use client";

import { useRouter } from "next/navigation";
import { useRoleSim, SIMULATABLE_ROLE_IDS } from "@/lib/role-sim/RoleSimContext";
import { useMroState } from "@/lib/mro-state/MroStateContext";
import { getRoleById } from "@/lib/mock/roles";

/** Reuses the existing RoleSimContext (Topbar's "Viewing as" selector) — no new state system. */
export function SimulateRoleButton({ roleId }: { roleId: string }) {
  const { roleId: currentRoleId, setRoleId } = useRoleSim();
  const { addAuditEvent } = useMroState();
  const router = useRouter();
  const simulatable = (SIMULATABLE_ROLE_IDS as readonly string[]).includes(roleId);
  if (!simulatable) return null;

  return (
    <button
      className="ac-btn"
      onClick={() => {
        const target = getRoleById(roleId);
        const current = getRoleById(currentRoleId);
        setRoleId(roleId);
        addAuditEvent({
          actor: "Prototype User",
          actorRole: "Role Simulation",
          action: "role_simulation.changed",
          objectType: "RoleSimulation",
          objectLabel: target?.name ?? roleId,
          previousState: current?.name ?? null,
          newState: target?.name ?? roleId,
        });
        router.push("/dashboard");
      }}
      title="Prototype simulation — permissions are not enforced"
    >
      Simulate This Role
    </button>
  );
}

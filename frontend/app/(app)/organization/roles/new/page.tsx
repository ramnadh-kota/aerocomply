"use client";

import { useRouter } from "next/navigation";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { RoleForm } from "@/components/organization/RoleForm";
import { createRole } from "@/lib/mock/roles";
import { useMroState } from "@/lib/mro-state/MroStateContext";

export default function NewRolePage() {
  const router = useRouter();
  const { addAuditEvent } = useMroState();

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Dashboard", href: "/dashboard" },
          { label: "Organization", href: "/organization" },
          { label: "Roles", href: "/organization/roles" },
          { label: "Add Role" },
        ]}
      />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Add Role</h1>
          <p className="ac-subtitle">Define a new role and its module access. Session-only prototype data — see note below.</p>
        </div>
      </div>
      <RoleForm
        submitLabel="Create Role"
        onCancel={() => router.push("/organization/roles")}
        onSubmit={(value) => {
          const role = createRole(value);
          addAuditEvent({
            actor: "Prototype User",
            actorRole: "Organization Admin",
            action: "role.created",
            objectType: "Role",
            objectLabel: role.name,
            previousState: null,
            newState: role.name,
          });
          router.push(`/organization/roles/${role.id}`);
        }}
      />
    </div>
  );
}
